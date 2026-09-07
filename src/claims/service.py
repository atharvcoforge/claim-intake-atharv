"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. It does not know where notifications are
stored either. It knows the rules.

`evaluate_policy_exists` ships written. It is the pattern every other rule
follows: take the notification and whatever it needs, decide, and return a
`RuleFailure | None`. Nothing prints, nothing raises for an ordinary refusal, and
nothing reaches for a status code, because a status code is a fact about HTTP and
this module does not know about HTTP.

Day 3 assignment. Build the remaining rules test-first against
`docs/api-contract.md` section 4.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from claims.models import (
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository

PolicyRule = Callable[[NotificationRequest, Policy], RuleFailure | None]


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of submitting a notification after every rule has run.

    `accepted` is the only thing a caller has to branch on. When it is true,
    `claim_reference` is the reference just issued. When it is false, `failure`
    names the rule that decided it. Invalid combinations are refused at
    construction so a polite caller cannot record a refusal or invent a reference.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    accepted: bool
    claim_reference: str | None = None
    failure: RuleFailure | None = None

    def __post_init__(self) -> None:
        if self.accepted:
            if self.failure is not None or self.claim_reference is None:
                raise ValueError(
                    "accepted outcome must carry a claim_reference and no failure"
                )
        elif self.failure is None or self.claim_reference is not None:
            raise ValueError(
                "refused outcome must carry a failure and no claim_reference"
            )


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> RuleFailure | None:
    """V-1. The policy must exist in the policy master.

    This rule is different from the others in one way that matters: it is the only
    one that reaches outside the service, so it is the only one that can fail for
    a reason that is not the caller's fault. `PolicyNotFound` is caught here and
    turned into an ordinary refusal, because a policy that does not exist is a
    fact about the caller's data. `PolicyLookupFailed` is deliberately not caught,
    because the caller did nothing wrong and the HTTP layer has to be able to tell
    the two apart. Contract section 6 fixes what each becomes.

    V-1 short circuits. Every other rule compares against a field on a policy, and
    if there is no policy there is nothing to compare against. Reporting
    LOSS_BEFORE_INCEPTION for a policy number that does not exist is not merely
    unhelpful, it is a false statement about the client's data (WI-0142, AC-4).

    `submit_notification` does not call this function: it inlines a single
    `get_policy` so the master is not looked up twice.
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return RuleFailure(
            rule=RuleId.V1,
            code=ErrorCode.POLICY_NOT_FOUND,
            detail={"policy_number": notification.policy_number},
        )
    return None


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date < policy.effective_date:
        return RuleFailure(
            rule=RuleId.V2,
            code=ErrorCode.LOSS_BEFORE_INCEPTION,
            detail={
                "policy_number": notification.policy_number,
                "loss_date": notification.loss_date,
                "effective_date": policy.effective_date,
            },
        )
    return None


def evaluate_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-7. Cover ends at the start of the cancellation date when one is set.

    Contract section 4.2 and WI-0158 AC-2: a loss on the cancellation date is not
    covered. AC-3: a null cancellation_date means this rule does not apply.
    """
    if (
        policy.cancellation_date is not None
        and notification.loss_date >= policy.cancellation_date
    ):
        return RuleFailure(
            rule=RuleId.V7,
            code=ErrorCode.POLICY_CANCELLED,
            detail={
                "policy_number": notification.policy_number,
                "loss_date": notification.loss_date,
                "cancellation_date": policy.cancellation_date,
            },
        )
    return None


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-3. The loss must not fall after the policy expiry date.

    Contract section 4.2: loss_date <= expiry_date. A loss on the final day of
    the term is covered.
    """
    if notification.loss_date > policy.expiry_date:
        return RuleFailure(
            rule=RuleId.V3,
            code=ErrorCode.LOSS_AFTER_EXPIRY,
            detail={
                "policy_number": notification.policy_number,
                "loss_date": notification.loss_date,
                "expiry_date": policy.expiry_date,
            },
        )
    return None


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount > policy.limit:
        return RuleFailure(
            rule=RuleId.V4,
            code=ErrorCode.AMOUNT_EXCEEDS_LIMIT,
            detail={
                "policy_number": notification.policy_number,
                "estimated_amount": notification.estimated_amount,
                "limit": policy.limit,
            },
        )
    return None


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-5. The claim type must be permitted on the policy's product."""
    if notification.claim_type not in policy.permitted_claim_types:
        return RuleFailure(
            rule=RuleId.V5,
            code=ErrorCode.TYPE_NOT_COVERED,
            detail={
                "policy_number": notification.policy_number,
                "claim_type": notification.claim_type,
                "permitted_claim_types": list(policy.permitted_claim_types),
            },
        )
    return None


# V-1 is the policy lookup in submit_notification (PolicyNotFound → POLICY_NOT_FOUND).
# V-6 is repository.find_matching in submit_notification after this list.
# Putting the repository inside POLICY_RULES would mix deciding with doing and would
# duplicate-check notifications that already failed a policy rule (WI-0151 AC-3).
# Order still matches contract section 4.1: V-1 → V-2 → V-7 → V-3 → V-4 → V-5 → V-6.
POLICY_RULES: Sequence[PolicyRule] = (
    evaluate_loss_after_inception,  # V-2
    evaluate_not_cancelled,  # V-7
    evaluate_loss_before_expiry,  # V-3
    evaluate_amount_within_limit,  # V-4
    evaluate_claim_type_covered,  # V-5
)


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate the policy-field rules and return the first failure, or None.

    A notification can violate several rules at once and the caller sees one
    reason, so the order this function evaluates in is a caller-visible behavior.
    It is fixed by contract section 4.1 and by nothing else. If you find yourself
    choosing an order here, the contract is incomplete and the fix belongs there.

    V-1 and V-6 are not in this function: V-1 is the policy lookup in
    `submit_notification`, and V-6 is the repository duplicate check there.
    """
    for rule in POLICY_RULES:
        failure = rule(notification, policy)
        if failure is not None:
            return failure
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Validate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.

    Stub returns a fake acceptance so failing tests die on assertion values, not
    on NotImplementedError naming a missing function.
    """
    return ValidationOutcome(accepted=True, claim_reference="CLM-2026-000001")

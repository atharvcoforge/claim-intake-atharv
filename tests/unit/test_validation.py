"""Unit tests for the Day 3 rule engine.

Written from docs/api-contract.md section 4 and docs/requirements-brief.md.
Each parametrized case names the break it catches. Tests assert literals from
the contract; they do not recompute with the code under test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimType, ErrorCode, NotificationRequest, Policy, RuleId
from claims.service import evaluate_notification


def _notification(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: Decimal = Decimal("4200.00"),
    description: str | None = "Rear ended at a junction.",
) -> NotificationRequest:
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
        description=description,
    )


def _policy(
    *,
    policy_number: str = "MOT-4471",
    product: str = "personal_auto_standard",
    effective_date: date = date(2026, 3, 1),
    expiry_date: date = date(2027, 2, 28),
    cancellation_date: date | None = None,
    limit: Decimal = Decimal("50000.00"),
    permitted_claim_types: tuple[ClaimType, ...] = (
        "collision",
        "theft",
        "glass",
        "liability",
        "weather",
    ),
) -> Policy:
    return Policy.model_validate(
        {
            "policy_number": policy_number,
            "product": product,
            "effective_date": effective_date,
            "expiry_date": expiry_date,
            "cancellation_date": cancellation_date,
            "limit": limit,
            "permitted_claim_types": permitted_claim_types,
        }
    )


@pytest.mark.parametrize(
    "loss_date,expect_failure",
    [
        pytest.param(
            date(2026, 2, 28),
            True,
            id="loss-day-before-inception",
        ),
        pytest.param(
            date(2026, 3, 1),
            False,
            id="wi0142-ac3-loss-on-inception-is-covered",
        ),
        pytest.param(
            date(2026, 3, 2),
            False,
            id="loss-day-after-inception",
        ),
    ],
)
def test_v2_loss_against_inception_boundary(
    loss_date: date, expect_failure: bool
) -> None:
    policy = _policy(effective_date=date(2026, 3, 1))
    notification = _notification(loss_date=loss_date)

    failure = evaluate_notification(notification, policy)

    if expect_failure:
        assert failure is not None
        assert failure.rule is RuleId.V2
        assert failure.code is ErrorCode.LOSS_BEFORE_INCEPTION
        assert failure.detail == {
            "policy_number": "MOT-4471",
            "loss_date": date(2026, 2, 28),
            "effective_date": date(2026, 3, 1),
        }
    else:
        assert failure is None


@pytest.mark.parametrize(
    "cancellation_date,loss_date,expect_failure",
    [
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 15),
            True,
            id="wi0158-ac2-loss-on-cancellation-date-not-covered",
        ),
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 16),
            True,
            id="loss-after-cancellation",
        ),
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 14),
            False,
            id="loss-day-before-cancellation",
        ),
        pytest.param(
            None,
            date(2026, 4, 2),
            False,
            id="wi0158-ac3-absent-cancellation-date",
        ),
    ],
)
def test_v7_cancellation_boundary(
    cancellation_date: date | None,
    loss_date: date,
    expect_failure: bool,
) -> None:
    policy = _policy(
        policy_number="MOT-4497",
        effective_date=date(2025, 6, 1),
        expiry_date=date(2026, 5, 31),
        cancellation_date=cancellation_date,
    )
    notification = _notification(
        policy_number="MOT-4497",
        loss_date=loss_date,
        claim_type="glass",
        estimated_amount=Decimal("480.00"),
    )

    failure = evaluate_notification(notification, policy)

    if expect_failure:
        assert failure is not None
        assert failure.rule is RuleId.V7
        assert failure.code is ErrorCode.POLICY_CANCELLED
        assert failure.detail == {
            "policy_number": "MOT-4497",
            "loss_date": loss_date,
            "cancellation_date": cancellation_date,
        }
    else:
        assert failure is None


@pytest.mark.parametrize(
    "loss_date,expect_failure",
    [
        pytest.param(
            date(2027, 3, 1),
            True,
            id="loss-day-after-expiry",
        ),
        pytest.param(
            date(2027, 2, 28),
            False,
            id="loss-on-expiry",
        ),
        pytest.param(
            date(2027, 2, 27),
            False,
            id="loss-day-before-expiry",
        ),
    ],
)
def test_v3_loss_against_expiry_boundary(
    loss_date: date, expect_failure: bool
) -> None:
    policy = _policy(expiry_date=date(2027, 2, 28))
    notification = _notification(loss_date=loss_date)

    failure = evaluate_notification(notification, policy)

    if expect_failure:
        assert failure is not None
        assert failure.rule is RuleId.V3
        assert failure.code is ErrorCode.LOSS_AFTER_EXPIRY
        assert failure.detail == {
            "policy_number": "MOT-4471",
            "loss_date": date(2027, 3, 1),
            "expiry_date": date(2027, 2, 28),
        }
    else:
        assert failure is None


@pytest.mark.parametrize(
    "estimated_amount,expect_failure",
    [
        pytest.param(
            Decimal("50000.01"),
            True,
            id="amount-one-cent-over-limit",
        ),
        pytest.param(
            Decimal("50000.00"),
            False,
            id="amount-equal-to-limit",
        ),
        pytest.param(
            Decimal("49999.99"),
            False,
            id="amount-one-cent-under-limit",
        ),
    ],
)
def test_v4_amount_against_limit_boundary(
    estimated_amount: Decimal, expect_failure: bool
) -> None:
    policy = _policy(limit=Decimal("50000.00"))
    notification = _notification(estimated_amount=estimated_amount)

    failure = evaluate_notification(notification, policy)

    if expect_failure:
        assert failure is not None
        assert failure.rule is RuleId.V4
        assert failure.code is ErrorCode.AMOUNT_EXCEEDS_LIMIT
        assert failure.detail == {
            "policy_number": "MOT-4471",
            "estimated_amount": Decimal("50000.01"),
            "limit": Decimal("50000.00"),
        }
    else:
        assert failure is None


@pytest.mark.parametrize(
    "claim_type,permitted,expect_failure",
    [
        pytest.param(
            "collision",
            ("theft", "glass", "weather", "liability"),
            True,
            id="collision-not-on-named-perils",
        ),
        pytest.param(
            "theft",
            ("theft", "glass", "weather", "liability"),
            False,
            id="permitted-type-on-named-perils",
        ),
    ],
)
def test_v5_claim_type_against_permitted_set(
    claim_type: ClaimType,
    permitted: tuple[ClaimType, ...],
    expect_failure: bool,
) -> None:
    policy = _policy(
        policy_number="MOT-4481",
        product="personal_auto_named_perils",
        effective_date=date(2026, 2, 15),
        expiry_date=date(2027, 2, 14),
        limit=Decimal("30000.00"),
        permitted_claim_types=permitted,
    )
    notification = _notification(
        policy_number="MOT-4481",
        loss_date=date(2026, 3, 27),
        claim_type=claim_type,
        estimated_amount=Decimal("4800.00"),
    )

    failure = evaluate_notification(notification, policy)

    if expect_failure:
        assert failure is not None
        assert failure.rule is RuleId.V5
        assert failure.code is ErrorCode.TYPE_NOT_COVERED
        assert failure.detail == {
            "policy_number": "MOT-4481",
            "claim_type": "collision",
            "permitted_claim_types": list(permitted),
        }
    else:
        assert failure is None


def test_v2_precedes_v4_when_both_would_fail() -> None:
    """Contract 4.1 / EDGE-05: first failure in order is V-2, not V-4."""
    policy = _policy(
        policy_number="MOT-4493",
        effective_date=date(2026, 4, 15),
        expiry_date=date(2027, 4, 14),
        limit=Decimal("50000.00"),
    )
    notification = _notification(
        policy_number="MOT-4493",
        loss_date=date(2026, 3, 2),
        estimated_amount=Decimal("72000.00"),
    )

    failure = evaluate_notification(notification, policy)

    assert failure is not None
    assert failure.rule is RuleId.V2
    assert failure.code is ErrorCode.LOSS_BEFORE_INCEPTION


def test_wi0158_ac4_v7_precedes_v3_when_both_would_fail() -> None:
    """Cancelled and after original expiry reports POLICY_CANCELLED, not expiry."""
    policy = _policy(
        policy_number="MOT-4500",
        effective_date=date(2025, 1, 1),
        expiry_date=date(2025, 12, 31),
        cancellation_date=date(2025, 10, 1),
        limit=Decimal("45000.00"),
    )
    notification = _notification(
        policy_number="MOT-4500",
        loss_date=date(2026, 1, 8),
        estimated_amount=Decimal("6000.00"),
    )

    failure = evaluate_notification(notification, policy)

    assert failure is not None
    assert failure.rule is RuleId.V7
    assert failure.code is ErrorCode.POLICY_CANCELLED

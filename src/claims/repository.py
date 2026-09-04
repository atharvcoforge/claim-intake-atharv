"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import AcceptedNotification, ClaimRecord, ClaimType


class NotificationRepository:
    """Stores recorded notifications and issues claim references.

    The only write path is `record(AcceptedNotification)`. A refusal is a
    `RuleFailure`, which this type does not accept, so WI-0151 AC-3 holds
    without callers having to remember to skip the store.
    """

    def __init__(self) -> None:
        self._records: list[ClaimRecord] = []
        self._next_sequence: int = 1

    def record(self, accepted: AcceptedNotification) -> ClaimRecord:
        """Write an accepted notification and return it with its claim reference.

        The reference format is fixed by contract section 3. References are unique
        and are never reissued.
        """
        notification = accepted.notification
        year = datetime.now(tz=UTC).date().year
        claim_reference = f"CLM-{year}-{self._next_sequence:06d}"
        self._next_sequence += 1
        recorded = ClaimRecord(
            claim_reference=claim_reference,
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
        self._records.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: ClaimType,
    ) -> ClaimRecord | None:
        """Return an existing recorded notification matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. AC-3 follows from
        the write surface: only `AcceptedNotification` can enter `_records`, so a
        refused submission is never a match candidate.
        """
        for recorded in self._records:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None

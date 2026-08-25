"""Unit tests for the notification repository.

Pins claim-reference issuance and the WI-0151 duplicate query. The store only
sees notifications that were recorded; refused submissions never reach it.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from claims.models import ClaimType, NotificationRequest
from claims.repository import NotificationRepository

CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")


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


def test_wi0151_ac1_matching_triple_returns_the_recorded_notification(
    repository: NotificationRepository,
) -> None:
    recorded = repository.record(_notification())

    found = repository.find_matching(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
    )

    assert found is not None
    assert found.claim_reference == recorded.claim_reference
    assert found.policy_number == "MOT-4471"
    assert found.loss_date == date(2026, 4, 2)
    assert found.claim_type == "collision"


def test_wi0151_ac3_rejected_notification_is_not_a_duplicate(
    repository: NotificationRepository,
) -> None:
    # A refusal never calls record(). Resubmitting the same triple finds nothing
    # to match, so V-6 cannot treat the earlier refusal as a duplicate.
    rejected = _notification()

    assert (
        repository.find_matching(
            policy_number=rejected.policy_number,
            loss_date=rejected.loss_date,
            claim_type=rejected.claim_type,
        )
        is None
    )


@pytest.mark.parametrize(
    "claim_type",
    [
        pytest.param("collision", id="first-reference"),
        pytest.param("theft", id="second-reference"),
    ],
)
def test_issued_references_match_contract_pattern(
    repository: NotificationRepository,
    claim_type: ClaimType,
) -> None:
    recorded = repository.record(_notification(claim_type=claim_type))

    assert CLAIM_REFERENCE_PATTERN.match(recorded.claim_reference)


def test_issued_references_are_unique(repository: NotificationRepository) -> None:
    first = repository.record(_notification(claim_type="collision"))
    second = repository.record(_notification(claim_type="theft"))

    assert first.claim_reference != second.claim_reference


def test_reference_year_is_recording_year_not_loss_year(
    repository: NotificationRepository,
) -> None:
    recorded = repository.record(_notification(loss_date=date(2025, 6, 15)))

    year = datetime.now(tz=UTC).date().year
    assert recorded.claim_reference.startswith(f"CLM-{year}-")


@pytest.mark.parametrize(
    "policy_number,loss_date,claim_type",
    [
        pytest.param("MOT-9999", date(2026, 4, 2), "collision", id="wrong-policy"),
        pytest.param("MOT-4471", date(2026, 4, 3), "collision", id="wrong-date"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="wrong-type"),
    ],
)
def test_partial_triple_is_not_a_duplicate(
    repository: NotificationRepository,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    repository.record(_notification(claim_type="collision"))

    found = repository.find_matching(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
    )

    assert found is None

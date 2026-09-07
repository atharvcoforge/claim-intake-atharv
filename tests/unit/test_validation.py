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

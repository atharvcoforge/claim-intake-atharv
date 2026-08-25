"""Unit tests for boundary models.

These pin the shape of a well-formed request and of a policy as the service
works with it. Business rules are not evaluated here.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from claims.models import NotificationRequest, Policy
from claims.policy_client import StubPolicyClient

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _payload(file_name: str, payload_id: str) -> dict[str, object]:
    records = json.loads((DATA_DIR / file_name).read_text())
    for record in records:
        if record["id"] == payload_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            return payload
    raise KeyError(payload_id)


def test_parses_valid_01_with_typed_fields() -> None:
    request = NotificationRequest.model_validate(_payload("fnol_valid.json", "VALID-01"))

    assert request.policy_number == "MOT-4471"
    assert request.loss_date == date(2026, 4, 2)
    assert isinstance(request.loss_date, date)
    assert request.claim_type == "collision"
    assert request.estimated_amount == Decimal("4200.00")
    assert isinstance(request.estimated_amount, Decimal)
    assert not isinstance(request.estimated_amount, float)
    assert request.description == "Rear ended at a junction."


def test_absent_description_is_none() -> None:
    payload = _payload("fnol_valid.json", "VALID-06")
    assert "description" not in payload

    request = NotificationRequest.model_validate(payload)

    assert request.description is None


def test_null_description_is_none() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["description"] = None

    request = NotificationRequest.model_validate(payload)

    assert request.description is None


def test_omitted_required_field_raises() -> None:
    payload = dict(_payload("fnol_edge.json", "EDGE-08"))
    assert "estimated_amount" not in payload

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_extra_field_raises() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["unexpected"] = "value"

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_empty_policy_number_raises() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["policy_number"] = ""

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_edge_11_unknown_claim_type_raises() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_payload("fnol_edge.json", "EDGE-11"))


def test_edge_12_three_decimal_places_raises() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_payload("fnol_edge.json", "EDGE-12"))


def test_integer_estimated_amount_raises() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["estimated_amount"] = 4200

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_float_estimated_amount_raises() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["estimated_amount"] = 4200.0

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_claim_type_wrong_case_raises() -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    payload["claim_type"] = "Collision"

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


def test_policy_from_record_null_cancellation(
    policy_client: StubPolicyClient,
) -> None:
    policy = Policy.from_record(policy_client.get_policy("MOT-4471"))

    assert policy.cancellation_date is None
    assert policy.policy_number == "MOT-4471"
    assert policy.effective_date == date(2026, 3, 1)
    assert policy.limit == Decimal("50000.00")


def test_policy_from_record_with_cancellation(
    policy_client: StubPolicyClient,
) -> None:
    policy = Policy.from_record(policy_client.get_policy("MOT-4497"))

    assert policy.cancellation_date == date(2026, 1, 15)


def test_policy_requires_cancellation_date_field() -> None:
    with pytest.raises(ValidationError):
        Policy(  # type: ignore[call-arg]
            policy_number="MOT-4471",
            product="personal_auto_standard",
            effective_date=date(2026, 3, 1),
            expiry_date=date(2027, 2, 28),
            limit=Decimal("50000.00"),
            permitted_claim_types=("collision",),
        )

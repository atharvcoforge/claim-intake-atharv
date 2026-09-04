"""Unit tests for boundary models.

These pin the shape of a well-formed request and of a policy as the service
works with it. Business rules are not evaluated here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from claims.models import (
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import StubPolicyClient

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _payload(file_name: str, payload_id: str) -> dict[str, object]:
    records = json.loads((DATA_DIR / file_name).read_text())
    for record in records:
        if record["id"] == payload_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            return payload
    raise KeyError(payload_id)


@pytest.mark.parametrize(
    "file_name,payload_id",
    [
        pytest.param("fnol_valid.json", "VALID-01", id="VALID-01"),
        pytest.param("fnol_valid.json", "VALID-02", id="VALID-02"),
        pytest.param("fnol_valid.json", "VALID-03", id="VALID-03"),
        pytest.param("fnol_valid.json", "VALID-04", id="VALID-04"),
        pytest.param("fnol_valid.json", "VALID-05", id="VALID-05"),
        pytest.param("fnol_valid.json", "VALID-06", id="VALID-06"),
        pytest.param("fnol_valid.json", "VALID-07", id="VALID-07"),
        pytest.param("fnol_valid.json", "VALID-08", id="VALID-08"),
        pytest.param("fnol_invalid.json", "INVALID-01", id="INVALID-01"),
        pytest.param("fnol_invalid.json", "INVALID-02", id="INVALID-02"),
        pytest.param("fnol_invalid.json", "INVALID-03", id="INVALID-03"),
        pytest.param("fnol_invalid.json", "INVALID-04", id="INVALID-04"),
        pytest.param("fnol_invalid.json", "INVALID-05", id="INVALID-05"),
        pytest.param("fnol_invalid.json", "INVALID-06", id="INVALID-06"),
        pytest.param("fnol_invalid.json", "INVALID-07", id="INVALID-07"),
        pytest.param("fnol_edge.json", "EDGE-01", id="EDGE-01"),
        pytest.param("fnol_edge.json", "EDGE-02", id="EDGE-02"),
        pytest.param("fnol_edge.json", "EDGE-03", id="EDGE-03"),
        pytest.param("fnol_edge.json", "EDGE-04", id="EDGE-04"),
        pytest.param("fnol_edge.json", "EDGE-05", id="EDGE-05"),
        pytest.param("fnol_edge.json", "EDGE-06", id="EDGE-06"),
        pytest.param("fnol_edge.json", "EDGE-07", id="EDGE-07"),
        pytest.param("fnol_edge.json", "EDGE-09", id="EDGE-09"),
        pytest.param("fnol_edge.json", "EDGE-10", id="EDGE-10"),
    ],
)
def test_well_formed_payloads_survive_to_rules(file_name: str, payload_id: str) -> None:
    request = NotificationRequest.model_validate(_payload(file_name, payload_id))

    assert isinstance(request.loss_date, date)
    assert isinstance(request.estimated_amount, Decimal)
    assert not isinstance(request.estimated_amount, float)


@pytest.mark.parametrize(
    "file_name,payload_id",
    [
        pytest.param("fnol_edge.json", "EDGE-08", id="EDGE-08-missing-amount"),
        pytest.param("fnol_edge.json", "EDGE-11", id="EDGE-11-unknown-claim-type"),
        pytest.param("fnol_edge.json", "EDGE-12", id="EDGE-12-three-decimal-places"),
    ],
)
def test_edge_payloads_refused_at_model(file_name: str, payload_id: str) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_payload(file_name, payload_id))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("policy_number"), id="missing-policy-number"),
        pytest.param(lambda p: p.pop("loss_date"), id="missing-loss-date"),
        pytest.param(lambda p: p.pop("claim_type"), id="missing-claim-type"),
        pytest.param(lambda p: p.pop("estimated_amount"), id="missing-estimated-amount"),
        pytest.param(
            lambda p: p.__setitem__("policy_number", ""),
            id="empty-policy-number",
        ),
        pytest.param(
            lambda p: p.__setitem__("unexpected", "value"),
            id="extra-field",
        ),
        pytest.param(
            lambda p: p.__setitem__("estimated_amount", 4200),
            id="amount-as-int",
        ),
        pytest.param(
            lambda p: p.__setitem__("estimated_amount", 4200.0),
            id="amount-as-float",
        ),
        pytest.param(
            lambda p: p.__setitem__("estimated_amount", "0.00"),
            id="amount-zero",
        ),
        pytest.param(
            lambda p: p.__setitem__("estimated_amount", "-1.00"),
            id="amount-negative",
        ),
        pytest.param(
            lambda p: p.__setitem__("estimated_amount", "4200.0"),
            id="amount-one-decimal",
        ),
        pytest.param(
            lambda p: p.__setitem__("loss_date", "2026-04-02T00:00:00"),
            id="loss-date-with-time",
        ),
        pytest.param(
            lambda p: p.__setitem__(
                "loss_date", datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)
            ),
            id="loss-date-as-datetime",
        ),
        pytest.param(
            lambda p: p.__setitem__("loss_date", "02-04-2026"),
            id="loss-date-wrong-format",
        ),
        pytest.param(
            lambda p: p.__setitem__("claim_type", "Collision"),
            id="claim-type-wrong-case",
        ),
        pytest.param(
            lambda p: p.__setitem__("claim_type", "flood"),
            id="claim-type-outside-vocabulary",
        ),
    ],
)
def test_field_constraint_violations(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    payload = dict(_payload("fnol_valid.json", "VALID-01"))
    mutate(payload)

    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload_id,set_null",
    [
        pytest.param("VALID-01", True, id="description-null"),
        pytest.param("VALID-06", False, id="description-absent"),
    ],
)
def test_description_absent_or_null_is_none(payload_id: str, set_null: bool) -> None:
    payload = dict(_payload("fnol_valid.json", payload_id))
    if set_null:
        payload["description"] = None
    else:
        assert "description" not in payload

    request = NotificationRequest.model_validate(payload)

    assert request.description is None


def test_policy_from_record_null_cancellation(policy_client: StubPolicyClient) -> None:
    policy = Policy.from_record(policy_client.get_policy("MOT-4471"))

    assert policy.cancellation_date is None
    assert policy.policy_number == "MOT-4471"
    assert policy.effective_date == date(2026, 3, 1)
    assert policy.limit == Decimal("50000.00")
    assert "collision" in policy.permitted_claim_types


def test_policy_from_record_with_cancellation(policy_client: StubPolicyClient) -> None:
    policy = Policy.from_record(policy_client.get_policy("MOT-4497"))

    assert policy.cancellation_date == date(2026, 1, 15)


def _valid_policy(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ("collision",),
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision",),
            },
            id="missing-cancellation-date",
        ),
        pytest.param(_valid_policy(extra="nope"), id="extra-field"),
        pytest.param(_valid_policy(policy_number=""), id="empty-policy-number"),
        pytest.param(_valid_policy(product=""), id="empty-product"),
        pytest.param(_valid_policy(limit=50000.0), id="limit-as-float"),
        pytest.param(_valid_policy(limit=50000), id="limit-as-int"),
        pytest.param(_valid_policy(limit="0.00"), id="limit-zero"),
        pytest.param(_valid_policy(limit="-1.00"), id="limit-negative"),
        pytest.param(_valid_policy(limit="50000.0"), id="limit-one-decimal"),
        pytest.param(
            _valid_policy(limit="50000.000"),
            id="limit-three-decimals",
        ),
        pytest.param(
            _valid_policy(permitted_claim_types=()),
            id="empty-permitted-claim-types",
        ),
        pytest.param(
            _valid_policy(permitted_claim_types=("flood",)),
            id="permitted-type-outside-vocabulary",
        ),
        pytest.param(
            _valid_policy(permitted_claim_types=("Collision",)),
            id="permitted-type-wrong-case",
        ),
    ],
)
def test_policy_constraint_violations(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate(payload)


def _valid_claim_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "claim_reference": "CLM-2026-000001",
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            _valid_claim_record(claim_reference="CLM-26-000001"),
            id="claim-reference-wrong-format",
        ),
        pytest.param(_valid_claim_record(extra="nope"), id="extra-field"),
        pytest.param(
            _valid_claim_record(policy_number=""),
            id="empty-policy-number",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount=4200.0),
            id="amount-as-float",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount=4200),
            id="amount-as-int",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount="0.00"),
            id="amount-zero",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount="-1.00"),
            id="amount-negative",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount="4200.0"),
            id="amount-one-decimal",
        ),
        pytest.param(
            _valid_claim_record(estimated_amount="4200.000"),
            id="amount-three-decimals",
        ),
        pytest.param(
            _valid_claim_record(claim_type="flood"),
            id="claim-type-outside-vocabulary",
        ),
    ],
)
def test_claim_record_constraint_violations(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)


def test_rule_failure_is_frozen_with_distinct_types() -> None:
    failure = RuleFailure(rule=RuleId.V1, code=ErrorCode.POLICY_NOT_FOUND)

    assert failure.rule is RuleId.V1
    assert failure.code is ErrorCode.POLICY_NOT_FOUND
    assert isinstance(failure.rule, RuleId)
    assert isinstance(failure.code, ErrorCode)
    with pytest.raises(FrozenInstanceError):
        failure.__setattr__("rule", RuleId.V2)

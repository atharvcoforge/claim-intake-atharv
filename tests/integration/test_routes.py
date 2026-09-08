"""HTTP integration tests for POST /notifications.

These exercise the service through the HTTP surface. Expected status, code, and
detail keys come from docs/api-contract.md sections 5 and 6. A fixture that
shared a repository across tests would make the suite order-dependent; every
test gets a fresh client, stub, and store.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.models import ErrorCode
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")
SECTION_6_5 = set(ErrorCode)


def _payload(file_name: str, payload_id: str) -> dict[str, Any]:
    records = json.loads((DATA_DIR / file_name).read_text())
    for record in records:
        if record["id"] == payload_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            return dict(payload)
    raise KeyError(payload_id)


@pytest.fixture
def client() -> Iterator[TestClient]:
    repository = NotificationRepository()
    policy_client = StubPolicyClient()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_policy_client] = lambda: policy_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def failing_client() -> Iterator[tuple[TestClient, StubPolicyClient]]:
    repository = NotificationRepository()
    policy_client = StubPolicyClient()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_policy_client] = lambda: policy_client
    with TestClient(app) as test_client:
        yield test_client, policy_client
    app.dependency_overrides.clear()


def _assert_error_envelope(body: dict[str, Any], code: str) -> None:
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == code
    assert code in SECTION_6_5
    assert isinstance(body["message"], str)
    assert isinstance(body["detail"], dict)


def test_valid_notification_returns_201_with_claim_reference(
    client: TestClient,
) -> None:
    response = client.post("/notifications", json=_payload("fnol_valid.json", "VALID-01"))

    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"])
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("EDGE-01", id="loss-on-inception"),
        pytest.param("EDGE-02", id="amount-equals-limit"),
        pytest.param("EDGE-03", id="loss-on-final-day"),
    ],
)
def test_boundary_acceptance_returns_201(client: TestClient, payload_id: str) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", payload_id))

    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"])
    assert body["status"] == "recorded"


def test_description_absent_is_accepted(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_valid.json", "VALID-06"))

    assert response.status_code == 201


def test_description_null_is_accepted(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["description"] = None

    response = client.post("/notifications", json=payload)

    assert response.status_code == 201


def test_v1_policy_not_found_returns_422(client: TestClient) -> None:
    response = client.post(
        "/notifications", json=_payload("fnol_invalid.json", "INVALID-01")
    )

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "POLICY_NOT_FOUND")
    assert body["detail"] == {"policy_number": "MOT-9999"}


def test_v1_case_sensitive_policy_number_returns_422(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-07"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "POLICY_NOT_FOUND")
    assert body["detail"] == {"policy_number": "mot-4471"}


def test_v2_loss_before_inception_returns_422(client: TestClient) -> None:
    response = client.post(
        "/notifications", json=_payload("fnol_invalid.json", "INVALID-02")
    )

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "LOSS_BEFORE_INCEPTION")
    assert body["detail"]["policy_number"] == "MOT-4479"
    assert body["detail"]["loss_date"] == "2026-02-20"
    assert body["detail"]["effective_date"] == "2026-03-15"


def test_v3_loss_after_expiry_returns_422(client: TestClient) -> None:
    response = client.post(
        "/notifications", json=_payload("fnol_invalid.json", "INVALID-03")
    )

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "LOSS_AFTER_EXPIRY")
    assert body["detail"]["policy_number"] == "MOT-4489"
    assert body["detail"]["loss_date"] == "2026-03-20"
    assert body["detail"]["expiry_date"] == "2026-02-28"


def test_v4_amount_exceeds_limit_returns_422(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-06"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "AMOUNT_EXCEEDS_LIMIT")
    assert body["detail"]["policy_number"] == "MOT-4502"
    assert body["detail"]["estimated_amount"] == "26000.00"
    assert body["detail"]["limit"] == "10000.00"


def test_v5_type_not_covered_returns_422(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-09"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "TYPE_NOT_COVERED")
    assert body["detail"]["policy_number"] == "MOT-4481"
    assert body["detail"]["claim_type"] == "collision"
    assert body["detail"]["permitted_claim_types"] == [
        "theft",
        "glass",
        "weather",
        "liability",
    ]


def test_v6_duplicate_notification_returns_409(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    first = client.post("/notifications", json=payload)
    assert first.status_code == 201
    first_reference = first.json()["claim_reference"]

    response = client.post("/notifications", json=payload)

    assert response.status_code == 409
    body = response.json()
    _assert_error_envelope(body, "DUPLICATE_NOTIFICATION")
    assert body["detail"] == {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "claim_reference": first_reference,
    }


def test_v7_policy_cancelled_returns_422(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-04"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "POLICY_CANCELLED")
    assert body["detail"] == {
        "policy_number": "MOT-4497",
        "cancellation_date": "2026-01-15",
        "loss_date": "2026-01-15",
    }


def test_edge05_reports_v2_not_v4_when_both_would_fail(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-05"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "LOSS_BEFORE_INCEPTION")
    assert body["code"] != "AMOUNT_EXCEEDS_LIMIT"


def test_edge10_reports_v7_not_v3_when_both_would_fail(client: TestClient) -> None:
    # WI-0158 AC-4: cancelled and past original term → POLICY_CANCELLED.
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-10"))

    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "POLICY_CANCELLED")
    assert body["code"] != "LOSS_AFTER_EXPIRY"


def test_malformed_json_returns_400(client: TestClient) -> None:
    response = client.post(
        "/notifications",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "MALFORMED_JSON")


def test_json_array_body_returns_malformed_json(client: TestClient) -> None:
    response = client.post("/notifications", json=[])

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "MALFORMED_JSON")


def test_missing_required_field_returns_400(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-08"))

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "MISSING_REQUIRED_FIELD")
    assert body["detail"] == {"field": "estimated_amount"}


def test_unknown_field_returns_400(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["extra_field"] = "should-not-be-accepted"

    response = client.post("/notifications", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "UNKNOWN_FIELD")
    assert body["detail"] == {"field": "extra_field"}


def test_claim_type_outside_vocabulary_returns_400(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-11"))

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "claim_type"
    assert "reason" in body["detail"]


def test_amount_three_decimals_returns_400(client: TestClient) -> None:
    response = client.post("/notifications", json=_payload("fnol_edge.json", "EDGE-12"))

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "estimated_amount"
    assert "reason" in body["detail"]


def test_amount_as_json_number_returns_400(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["estimated_amount"] = 4200.00

    response = client.post("/notifications", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "estimated_amount"


@pytest.mark.parametrize(
    "amount",
    [
        pytest.param("0.00", id="zero"),
        pytest.param("-1.00", id="negative"),
    ],
)
def test_amount_not_greater_than_zero_returns_400(
    client: TestClient, amount: str
) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["estimated_amount"] = amount

    response = client.post("/notifications", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "estimated_amount"


def test_loss_date_with_time_component_returns_400(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["loss_date"] = "2026-04-02T12:00:00"

    response = client.post("/notifications", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "loss_date"


def test_empty_policy_number_returns_400(client: TestClient) -> None:
    payload = _payload("fnol_valid.json", "VALID-01")
    payload["policy_number"] = ""

    response = client.post("/notifications", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body, "INVALID_FIELD_VALUE")
    assert body["detail"]["field"] == "policy_number"


@pytest.mark.parametrize(
    "reason,status,code",
    [
        pytest.param("timeout", 504, "POLICY_MASTER_TIMEOUT", id="timeout"),
        pytest.param("unreachable", 503, "POLICY_MASTER_UNREACHABLE", id="unreachable"),
        pytest.param(
            "unparsable", 502, "POLICY_MASTER_INVALID_RESPONSE", id="unparsable"
        ),
    ],
)
def test_policy_lookup_failed_returns_distinct_5xx(
    failing_client: tuple[TestClient, StubPolicyClient],
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    client, policy_client = failing_client
    policy_client.fail_with = reason

    response = client.post("/notifications", json=_payload("fnol_valid.json", "VALID-01"))

    assert response.status_code == status
    assert response.status_code >= 500
    body = response.json()
    _assert_error_envelope(body, code)
    assert body["detail"] == {"dependency": "policy_master"}
    assert "policy_number" not in body["detail"]


def test_refusal_does_not_write_so_resubmit_succeeds(client: TestClient) -> None:
    # WI-0151 AC-3: a prior rejected submission is not a duplicate.
    rejected = client.post(
        "/notifications", json=_payload("fnol_invalid.json", "INVALID-01")
    )
    assert rejected.status_code == 422

    payload = _payload("fnol_valid.json", "VALID-01")
    response = client.post("/notifications", json=payload)

    assert response.status_code == 201

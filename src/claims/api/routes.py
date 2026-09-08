"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from claims.models import ErrorCode, NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import submit_notification

app = FastAPI(title="Claims Intake Service")

_default_policy_client = StubPolicyClient()
_default_repository = NotificationRepository()


def get_policy_client() -> PolicyClient:
    return _default_policy_client


def get_repository() -> NotificationRepository:
    return _default_repository


class ErrorEnvelope(BaseModel):
    """Section 5 envelope. One shape for every refusal this surface returns."""

    code: ErrorCode
    message: str
    detail: dict[str, Any]


# Transcribed from contract section 6. Status is a fact about HTTP; the service
# layer never sees these numbers.
_STATUS: dict[ErrorCode, int] = {
    ErrorCode.MALFORMED_JSON: 400,
    ErrorCode.MISSING_REQUIRED_FIELD: 400,
    ErrorCode.INVALID_FIELD_VALUE: 400,
    ErrorCode.UNKNOWN_FIELD: 400,
    ErrorCode.POLICY_NOT_FOUND: 422,
    ErrorCode.LOSS_BEFORE_INCEPTION: 422,
    ErrorCode.POLICY_CANCELLED: 422,
    ErrorCode.LOSS_AFTER_EXPIRY: 422,
    ErrorCode.AMOUNT_EXCEEDS_LIMIT: 422,
    ErrorCode.TYPE_NOT_COVERED: 422,
    ErrorCode.DUPLICATE_NOTIFICATION: 409,
    ErrorCode.POLICY_MASTER_TIMEOUT: 504,
    ErrorCode.POLICY_MASTER_UNREACHABLE: 503,
    ErrorCode.POLICY_MASTER_INVALID_RESPONSE: 502,
}

_DEPENDENCY: dict[LookupFailureReason, ErrorCode] = {
    "timeout": ErrorCode.POLICY_MASTER_TIMEOUT,
    "unreachable": ErrorCode.POLICY_MASTER_UNREACHABLE,
    "unparsable": ErrorCode.POLICY_MASTER_INVALID_RESPONSE,
}

_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.MALFORMED_JSON: "Request body is not valid JSON.",
    ErrorCode.MISSING_REQUIRED_FIELD: "A required field is absent.",
    ErrorCode.INVALID_FIELD_VALUE: "A field value is not the required type.",
    ErrorCode.UNKNOWN_FIELD: "A field is present that the contract does not define.",
    ErrorCode.POLICY_NOT_FOUND: "No policy matches the supplied policy number.",
    ErrorCode.LOSS_BEFORE_INCEPTION: "The loss date is earlier than policy inception.",
    ErrorCode.POLICY_CANCELLED: "Cover ended when the policy was cancelled.",
    ErrorCode.LOSS_AFTER_EXPIRY: "The loss date is later than policy expiry.",
    ErrorCode.AMOUNT_EXCEEDS_LIMIT: "The estimated amount exceeds the policy limit.",
    ErrorCode.TYPE_NOT_COVERED: "The claim type is not permitted on this product.",
    ErrorCode.DUPLICATE_NOTIFICATION: "A matching notification is already recorded.",
    ErrorCode.POLICY_MASTER_TIMEOUT: (
        "The policy master did not respond within the allowed time."
    ),
    ErrorCode.POLICY_MASTER_UNREACHABLE: "The policy master could not be reached.",
    ErrorCode.POLICY_MASTER_INVALID_RESPONSE: (
        "The policy master returned a response the service could not parse."
    ),
}


def _error_response(code: ErrorCode, detail: dict[str, Any]) -> JSONResponse:
    message = _MESSAGES[code]
    if code is ErrorCode.MISSING_REQUIRED_FIELD and "field" in detail:
        message = f"Required field {detail['field']} is absent."
    envelope = ErrorEnvelope(code=code, message=message, detail=detail)
    return JSONResponse(
        status_code=_STATUS[code],
        content=envelope.model_dump(mode="json"),
    )


def _field_name(error: Any) -> str | None:
    loc = error.get("loc", ())
    if not loc:
        return None
    return str(loc[0])


def _map_validation_error(exc: ValidationError) -> JSONResponse:
    """Map a pydantic ValidationError to the first section 6.1 code.

    Precedence follows the section 6.1 table order, not pydantic's error order:
    MISSING_REQUIRED_FIELD, then INVALID_FIELD_VALUE, then UNKNOWN_FIELD.
    """
    errors = exc.errors()
    missing = [e for e in errors if e["type"] == "missing"]
    if missing:
        field = _field_name(missing[0]) or "unknown"
        return _error_response(
            ErrorCode.MISSING_REQUIRED_FIELD,
            {"field": field},
        )

    unknown = [e for e in errors if e["type"] == "extra_forbidden"]
    invalid = [e for e in errors if e["type"] not in {"missing", "extra_forbidden"}]
    if invalid:
        error = invalid[0]
        field = _field_name(error) or "unknown"
        return _error_response(
            ErrorCode.INVALID_FIELD_VALUE,
            {"field": field, "reason": error.get("msg", "invalid value")},
        )
    if unknown:
        field = _field_name(unknown[0]) or "unknown"
        return _error_response(ErrorCode.UNKNOWN_FIELD, {"field": field})

    return _error_response(
        ErrorCode.INVALID_FIELD_VALUE,
        {"field": "unknown", "reason": "request could not be interpreted"},
    )


@app.post("/notifications")
async def create_notification(
    request: Request,
    policy_client: Annotated[PolicyClient, Depends(get_policy_client)],
    repository: Annotated[NotificationRepository, Depends(get_repository)],
) -> Response:
    raw = await request.body()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return _error_response(ErrorCode.MALFORMED_JSON, {})

    if not isinstance(body, dict):
        # Section 5.2: INVALID_FIELD_VALUE guarantees a field key. A non-object
        # body has no field to name, so it is MALFORMED_JSON.
        return _error_response(ErrorCode.MALFORMED_JSON, {})

    try:
        notification = NotificationRequest.model_validate(body)
    except ValidationError as exc:
        return _map_validation_error(exc)

    try:
        outcome = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        code = _DEPENDENCY[exc.reason]
        # Section 5.2: dependency failures carry only dependency=policy_master.
        return _error_response(code, {"dependency": "policy_master"})

    if outcome.accepted:
        return JSONResponse(
            status_code=201,
            content={
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )

    assert outcome.failure is not None
    detail = to_jsonable_python(outcome.failure.detail)
    assert isinstance(detail, dict)
    return _error_response(outcome.failure.code, detail)

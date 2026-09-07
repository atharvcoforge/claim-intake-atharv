"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from claims.policy_client import PolicyRecord

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

_TWO_PLACE_DECIMAL = re.compile(r"^[0-9]+\.[0-9]{2}$")
_CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


def _parse_money_amount(value: object) -> Decimal:
    """Contract money: written two decimal places, greater than zero, never a float.

    Shared across request, policy limit, and recorded claim so V-4 comparisons
    cannot see a scale the caller did not send. JSON numbers have no written
    scale to preserve, so they are refused here rather than coerced.
    """
    if isinstance(value, Decimal):
        if value <= 0 or value.as_tuple().exponent != -2:
            raise ValueError(
                "money amount must be greater than zero with exactly two decimal places"
            )
        return value
    if isinstance(value, str):
        if not _TWO_PLACE_DECIMAL.fullmatch(value):
            raise ValueError(
                "money amount must be a string with exactly two decimal places"
            )
        amount = Decimal(value)
        if amount <= 0:
            raise ValueError("money amount must be greater than zero")
        return amount
    raise ValueError(
        "money amount must arrive as a string with exactly two decimal places"
    )


# Annotated alias so every money field carries the same constraint
# (https://docs.pydantic.dev/latest/concepts/fields/).
MoneyAmount = Annotated[Decimal, BeforeValidator(_parse_money_amount)]


class RuleId(StrEnum):
    """Identifiers for the rules in contract section 4.2."""

    V1 = "V-1"
    V2 = "V-2"
    V3 = "V-3"
    V4 = "V-4"
    V5 = "V-5"
    V6 = "V-6"
    V7 = "V-7"


class ErrorCode(StrEnum):
    """Stable refusal codes produced by the rules in section 4.2."""

    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    LOSS_BEFORE_INCEPTION = "LOSS_BEFORE_INCEPTION"
    LOSS_AFTER_EXPIRY = "LOSS_AFTER_EXPIRY"
    AMOUNT_EXCEEDS_LIMIT = "AMOUNT_EXCEEDS_LIMIT"
    TYPE_NOT_COVERED = "TYPE_NOT_COVERED"
    DUPLICATE_NOTIFICATION = "DUPLICATE_NOTIFICATION"
    POLICY_CANCELLED = "POLICY_CANCELLED"


@dataclass(frozen=True)
class RuleFailure:
    """A failed rule decision.

    `rule` and `code` are distinct types so a rule identifier cannot be passed
    where an error code is expected. `detail` carries the section 5.2 keys for
    the code; callers may rely only on those keys.
    """

    rule: RuleId
    code: ErrorCode
    detail: dict[str, object] = field(default_factory=dict)


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: MoneyAmount
    description: str | None = None

    @field_validator("loss_date", mode="before")
    @classmethod
    def loss_date_must_be_calendar_date(cls, value: object) -> object:
        # datetime is a date subclass; reject it so comparisons stay calendar-day only.
        if type(value) is datetime:
            raise ValueError("loss_date must be a calendar date, not a datetime")
        if isinstance(value, str) and "T" in value:
            raise ValueError("loss_date must be YYYY-MM-DD")
        return value


@dataclass(frozen=True)
class AcceptedNotification:
    """A notification that cleared every rule and may be written.

    Day 3 constructs this after the rule table passes. The repository only
    accepts this type, so a refusal has no write path: WI-0151 AC-3 is a
    property of the API surface, not a convention callers must remember.
    """

    notification: NotificationRequest


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    product: str = Field(min_length=1)
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: MoneyAmount
    permitted_claim_types: tuple[ClaimType, ...] = Field(min_length=1)

    @classmethod
    def from_record(cls, record: PolicyRecord) -> Policy:
        # model_validate narrows PolicyRecord's loose tuple[str, ...] against
        # ClaimType; constructing Policy(...) directly fails mypy on that field.
        return cls.model_validate(
            {
                "policy_number": record.policy_number,
                "product": record.product,
                "effective_date": record.effective_date,
                "expiry_date": record.expiry_date,
                "cancellation_date": record.cancellation_date,
                "limit": record.limit,
                "permitted_claim_types": record.permitted_claim_types,
            }
        )


class ClaimRecord(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format. Money constraints match the request
    so a recorded amount cannot drift from what the portal sent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: str
    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: MoneyAmount
    description: str | None = None

    @model_validator(mode="after")
    def claim_reference_matches_contract(self) -> ClaimRecord:
        if not _CLAIM_REFERENCE.fullmatch(self.claim_reference):
            raise ValueError("claim_reference must match CLM-YYYY-NNNNNN")
        return self

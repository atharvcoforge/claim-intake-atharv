"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from claims.policy_client import PolicyRecord

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

_TWO_PLACE_DECIMAL = re.compile(r"^[0-9]+\.[0-9]{2}$")
_CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


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
    estimated_amount: Decimal
    description: str | None = None

    @field_validator("loss_date", mode="before")
    @classmethod
    def loss_date_must_be_calendar_date(cls, value: object) -> object:
        if isinstance(value, datetime):
            raise ValueError("loss_date must be a calendar date, not a datetime")  # noqa: TRY004
        if isinstance(value, str) and "T" in value:
            raise ValueError("loss_date must be YYYY-MM-DD")
        return value

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def estimated_amount_from_written_form(cls, value: object) -> object:
        if isinstance(value, Decimal):
            if value <= 0 or value.as_tuple().exponent != -2:
                raise ValueError(
                    "estimated_amount must be greater than zero with exactly two decimal places"
                )
            return value
        if isinstance(value, (int, float)):
            # int includes bool; both are wrong JSON types for this field.
            raise ValueError(  # noqa: TRY004
                "estimated_amount must arrive as a string with exactly two decimal places"
            )
        if isinstance(value, str):
            if not _TWO_PLACE_DECIMAL.fullmatch(value):
                raise ValueError(
                    "estimated_amount must be a string with exactly two decimal places"
                )
            amount = Decimal(value)
            if amount <= 0:
                raise ValueError("estimated_amount must be greater than zero")
            return amount
        raise ValueError("estimated_amount must be a two-place decimal string")


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal
    permitted_claim_types: tuple[str, ...]

    @classmethod
    def from_record(cls, record: PolicyRecord) -> Policy:
        return cls(
            policy_number=record.policy_number,
            product=record.product,
            effective_date=record.effective_date,
            expiry_date=record.expiry_date,
            cancellation_date=record.cancellation_date,
            limit=record.limit,
            permitted_claim_types=record.permitted_claim_types,
        )


class RecordedNotification(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: str
    policy_number: str
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None

    @model_validator(mode="after")
    def claim_reference_matches_contract(self) -> RecordedNotification:
        if not _CLAIM_REFERENCE.fullmatch(self.claim_reference):
            raise ValueError(
                "claim_reference must match CLM-YYYY-NNNNNN"
            )
        return self

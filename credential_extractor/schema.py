"""Output contract: the 8 fields every extraction must return, plus the optional summary (bonus)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ExpirationStatus = Literal["expired", "expiring_soon", "valid", "no_expiration"]


class Credential(BaseModel):
    """The JSON contract defined in the brief. Field order matters for output."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    is_credential: bool
    holder_name: str | None = None
    credential_type: str | None = None
    license_number: str | None = None
    issuing_authority: str | None = None
    issue_date: str | None = None
    expiration_date: str | None = None
    expiration_status: ExpirationStatus | None = None
    # Bonus: one- or two-sentence description of the document. Not part of the
    # field-accuracy eval; scored separately by judge.py (LLM-as-judge).
    summary: str | None = None

    @field_validator("holder_name", "credential_type", "license_number", "issuing_authority",
                     "issue_date", "expiration_date", "summary", mode="before")
    @classmethod
    def empty_string_is_null(cls, value):
        """Models sometimes return "" or "null" for missing values; treat both as null."""
        if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "n/a"}:
            return None
        return value


FIELDS = [f for f in Credential.model_fields if f != "summary"]  # the 8 scored fields


def json_schema() -> dict:
    """JSON schema of the contract, for structured outputs (Phase 5)."""
    return Credential.model_json_schema()

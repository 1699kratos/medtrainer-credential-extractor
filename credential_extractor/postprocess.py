"""Deterministic logic applied after the model answers.

Phase 3: expiration_status and null enforcement. Date and name normalization
are added in Phase 4.
"""

from __future__ import annotations

from datetime import date, timedelta

from .schema import Credential

DEFAULT_WINDOW_DAYS = 60


def compute_expiration_status(
    is_credential: bool,
    expiration_date: str | None,
    reference_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> str | None:
    """Status of a credential on `reference_date`.

    Rules, in order:
      not a credential            -> None
      no expiration date          -> "no_expiration"
      exp < ref                   -> "expired"
      ref <= exp <= ref + window  -> "expiring_soon"   (both ends inclusive)
      otherwise                   -> "valid"

    On the expiration day itself the credential is still valid (it counts as
    expiring_soon, not expired).
    """
    if not is_credential:
        return None
    if expiration_date is None:
        return "no_expiration"
    try:
        exp = date.fromisoformat(expiration_date)
    except ValueError:
        # Not an ISO date: the status cannot be computed. Never fail the whole
        # document over one field; the eval will count the field as wrong.
        return None
    if exp < reference_date:
        return "expired"
    if exp <= reference_date + timedelta(days=window_days):
        return "expiring_soon"
    return "valid"


def finalize(cred: Credential, reference_date: date, window_days: int = DEFAULT_WINDOW_DAYS) -> Credential:
    """Apply the deterministic rules and return a new Credential."""
    data = cred.model_dump()

    if not data["is_credential"]:
        # Not a credential: every other field must be null, whatever the model said.
        return Credential(is_credential=False)

    data["expiration_status"] = compute_expiration_status(
        True, data["expiration_date"], reference_date, window_days
    )
    return Credential(**data)

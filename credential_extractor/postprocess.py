"""Deterministic logic applied after the model answers.

The model copies values as printed; this module normalizes them:
  - dates          -> ISO 8601 (YYYY-MM-DD), None if unparseable
  - holder_name    -> degree suffixes removed, whitespace collapsed
  - expiration_status computed against the reference date
  - every field nulled when the document is not a credential
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .schema import Credential

DEFAULT_WINDOW_DAYS = 60

# Dates --------------------------------------------------------------------

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_US = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$")          # MM/DD/YYYY, MM/DD/YY
_MONTH_FIRST = re.compile(r"^([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{2}|\d{4})$")  # March 15, 2024
_DAY_FIRST = re.compile(r"^(\d{1,2})[\s\-]+([a-z]+)\.?[\s\-,]+(\d{2}|\d{4})$")  # 15 March 2024, 15-MAR-24


def _year(text: str) -> int:
    """Two-digit years are read as 20YY: credentials are not from the 1900s."""
    return int(text) if len(text) == 4 else 2000 + int(text)


def _build(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None  # 02/30/2024, month 13, etc.


def normalize_date(text: str | None) -> str | None:
    """Return the date as YYYY-MM-DD, or None if it cannot be parsed.

    Numeric dates are assumed month-first (US), since the documents come from
    US licensing boards. Unparseable or impossible dates return None rather
    than a guess.
    """
    if text is None:
        return None
    s = re.sub(r"\s+", " ", text).strip().lower()
    if not s:
        return None

    if m := _ISO.match(s):
        return _build(int(m[1]), int(m[2]), int(m[3]))
    if m := _US.match(s):
        return _build(_year(m[3]), int(m[1]), int(m[2]))
    if (m := _MONTH_FIRST.match(s)) and m[1] in MONTHS:
        return _build(_year(m[3]), MONTHS[m[1]], int(m[2]))
    if (m := _DAY_FIRST.match(s)) and m[2] in MONTHS:
        return _build(_year(m[3]), MONTHS[m[2]], int(m[1]))
    return None


# Names --------------------------------------------------------------------

DEGREE_SUFFIXES = {
    "md", "do", "rn", "lpn", "lvn", "np", "pa", "pa-c", "crna", "aprn",
    "dds", "dmd", "phd", "pharmd", "dnp", "bsn", "msn", "mph", "rph",
    "fnp", "fnp-c", "cnm", "facs", "faap", "dpm", "od", "dc", "pt", "dpt",
}


def strip_degree_suffix(name: str | None) -> str | None:
    """Remove trailing academic/professional suffixes; keep Jr., Sr., II, III.

    "Jane Doe, RN"        -> "Jane Doe"
    "John Smith MD PhD"   -> "John Smith"
    "Robert Lee Jr., DDS" -> "Robert Lee Jr."
    """
    if name is None:
        return None
    s = re.sub(r"\s+", " ", name).strip()
    tokens = re.split(r"[,\s]+", s)
    while tokens and tokens[-1].lower().replace(".", "") in DEGREE_SUFFIXES:
        tokens.pop()
    s = " ".join(tokens).strip(" ,")
    return s or None


# Status -------------------------------------------------------------------

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

    data["holder_name"] = strip_degree_suffix(data["holder_name"])
    data["issue_date"] = normalize_date(data["issue_date"])
    data["expiration_date"] = normalize_date(data["expiration_date"])
    data["expiration_status"] = compute_expiration_status(
        True, data["expiration_date"], reference_date, window_days
    )
    return Credential(**data)

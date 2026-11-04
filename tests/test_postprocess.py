from datetime import date

import pytest

from credential_extractor.postprocess import (
    compute_expiration_status,
    finalize,
    normalize_date,
    strip_degree_suffix,
)
from credential_extractor.schema import Credential

REF = date(2026, 11, 1)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("03/15/2024", "2024-03-15"),
        ("3/5/24", "2024-03-05"),
        ("12-31-2027", "2027-12-31"),
        ("2024-03-15", "2024-03-15"),
        ("March 15, 2024", "2024-03-15"),
        ("Mar 15 2024", "2024-03-15"),
        ("15 March 2024", "2024-03-15"),
        ("15-MAR-24", "2024-03-15"),
        ("  March   15,  2024 ", "2024-03-15"),
        ("Sept 1, 2025", "2025-09-01"),
        (None, None),
        ("", None),
        ("02/30/2024", None),      # impossible day
        ("13/01/2024", None),      # impossible month (month-first assumption)
        ("Fecha 2024", None),      # unrecognized text
    ],
)
def test_normalize_date(text, expected):
    assert normalize_date(text) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Jane Doe, RN", "Jane Doe"),
        ("John Smith MD PhD", "John Smith"),
        ("John Smith, M.D.", "John Smith"),
        ("Robert Lee Jr., DDS", "Robert Lee Jr."),
        ("Mary Ann  Jones III", "Mary Ann Jones III"),
        ("Plain Name", "Plain Name"),
        (None, None),
        ("RN", None),  # nothing left after stripping
    ],
)
def test_strip_degree_suffix(name, expected):
    assert strip_degree_suffix(name) == expected


@pytest.mark.parametrize(
    "is_cred, exp, expected",
    [
        (False, "2030-01-01", None),
        (True, None, "no_expiration"),
        (True, "2026-10-31", "expired"),
        (True, "2026-11-01", "expiring_soon"),   # reference day itself
        (True, "2026-12-31", "expiring_soon"),   # day 60, inclusive
        (True, "2027-01-01", "valid"),           # day 61
        (True, "12/31/2027", None),              # not ISO
    ],
)
def test_compute_expiration_status(is_cred, exp, expected):
    assert compute_expiration_status(is_cred, exp, REF) == expected


def test_finalize_normalizes_then_computes_status():
    cred = Credential(
        is_credential=True,
        holder_name="Jane Doe, RN",
        issue_date="3/5/24",
        expiration_date="12/31/2027",
    )
    out = finalize(cred, REF)
    assert out.holder_name == "Jane Doe"
    assert out.issue_date == "2024-03-05"
    assert out.expiration_date == "2027-12-31"
    assert out.expiration_status == "valid"


def test_finalize_nulls_everything_when_not_credential():
    cred = Credential(is_credential=False, holder_name="X", expiration_date="01/01/2030", summary="A renewal notice.")
    out = finalize(cred, REF)
    assert out.model_dump() == Credential(is_credential=False, summary="A renewal notice.").model_dump()
    assert out.holder_name is None and out.expiration_date is None

"""Web UI for the credential extractor (Streamlit, deployed on Streamlit Community Cloud).

Upload a license or certification (PDF or image), optionally set the reference
date, and get the extracted JSON. Uploaded files are written to a temporary
file for the duration of the request and deleted afterwards; nothing is stored.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from credential_extractor.pipeline import extract
from credential_extractor.postprocess import DEFAULT_WINDOW_DAYS

WINDOW_DAYS = int(os.environ.get("EXPIRING_WINDOW_DAYS") or DEFAULT_WINDOW_DAYS)
EVAL_REFERENCE_DATE = date(2026, 11, 1)
ACCEPTED = ["pdf", "png", "jpg", "jpeg", "webp"]

STATUS_TEXT = {
    "expired": "expired",
    "expiring_soon": f"expiring within {WINDOW_DAYS} days",
    "valid": "valid",
    "no_expiration": "no expiration date on the document",
}


def summary(result: dict) -> str:
    """One plain-language line so eight nulls do not read as a failure."""
    if not result["is_credential"]:
        return "Not a credential (renewal notice, receipt, form or similar). All fields are null by design."
    status = STATUS_TEXT.get(result["expiration_status"], "status unknown")
    return f"Credential found. Status: {status}."


def run_extraction(upload, reference_date: date) -> dict:
    """Write the upload to a temp file, extract, delete the file."""
    suffix = Path(upload.name).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(upload.getbuffer())
        tmp_path = Path(tmp.name)
    try:
        return extract(tmp_path, reference_date, window_days=WINDOW_DAYS)
    finally:
        tmp_path.unlink(missing_ok=True)


st.set_page_config(page_title="Credential Extractor", page_icon="🩺", layout="wide")
st.title("Credential Extractor")
st.write(
    "Upload a medical license or certification (PDF, PNG, JPG, WEBP). The extractor returns the "
    "8 contract fields as JSON and flags whether the credential is expired or expiring within "
    f"{WINDOW_DAYS} days of the reference date. Uploaded documents are not stored."
)

left, right = st.columns(2)
with left:
    upload = st.file_uploader("Document", type=ACCEPTED)
    reference_date = st.date_input(
        "Reference date",
        value=date.today(),
        help=f"Date the expiration status is computed against. Use {EVAL_REFERENCE_DATE} to reproduce the eval.",
    )
    go = st.button("Extract", type="primary", disabled=upload is None)

with right:
    if go and upload is not None:
        with st.spinner("Reading the document..."):
            out = run_extraction(upload, reference_date)
        result, meta = out["result"], out["meta"]
        if "error" in result:
            st.error(f"Extraction failed: {meta.get('error', result['error'])}")
        else:
            st.success(summary(result))
            st.subheader("Extracted fields")
            st.json(result)
            cost = meta.get("cost_usd")
            st.caption(
                f"Model: {meta.get('model')} via {meta.get('provider')} · "
                f"Pages sent: {meta.get('pages_sent')} · "
                f"Latency: {meta.get('latency_s')} s · "
                + (f"Cost: ${cost:.5f} · " if cost is not None else "Cost: not reported · ")
                + f"Reference date: {reference_date.isoformat()} (window: {WINDOW_DAYS} days)"
            )
    else:
        st.info("Upload a document and press Extract.")

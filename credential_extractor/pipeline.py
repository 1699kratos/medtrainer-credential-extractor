"""End-to-end extraction: document -> images -> model -> validated JSON.

`extract` is the single entry point used by the CLI, the eval and the web app.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from . import prompt
from .client import ProviderError, chat
from .loader import load_pages
from .postprocess import DEFAULT_WINDOW_DAYS, finalize
from .schema import Credential


def parse_json(text: str) -> dict:
    """Parse the model's answer. Tolerates ``` fences and text around the JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise
        return json.loads(text[start : end + 1])


def extract(
    path: Path,
    reference_date: date,
    model: str | None = None,
    dpi: int = 100,
    max_pages: int = 1,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    """Extract the 8 contract fields from one document.

    Returns {"result": {...8 fields...}, "meta": {...}}.
    On failure, "result" is {"error": <message>} and "meta" has what is known,
    so the eval counts the document as wrong without crashing the batch.
    """
    meta: dict = {"file": path.name, "reference_date": reference_date.isoformat()}
    try:
        images = load_pages(path, dpi=dpi, max_pages=max_pages)
        meta["pages_sent"] = len(images)

        answer = chat(prompt.SYSTEM, prompt.USER, images, model=model)
        meta.update(answer["meta"])
        meta["raw"] = answer["text"]

        cred = Credential(**parse_json(answer["text"]))
        cred = finalize(cred, reference_date, window_days)
        return {"result": cred.model_dump(), "meta": meta}

    except (ValueError, ProviderError, ValidationError, json.JSONDecodeError, KeyError) as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return {"result": {"error": str(exc)}, "meta": meta}

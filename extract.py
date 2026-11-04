"""Credential extractor CLI.

Sends a license or certification document (PDF or image) to a vision model
and prints the extracted fields as JSON. Same interface as the original
script, plus --reference-date, --dpi and --max-pages.

Usage:
    python extract.py docs/tx_01.pdf
    python extract.py docs/ --out-dir outputs/ --reference-date 2026-11-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from credential_extractor.client import default_model
from credential_extractor.loader import SUPPORTED_EXTENSIONS
from credential_extractor.pipeline import extract
from credential_extractor.postprocess import DEFAULT_WINDOW_DAYS


def resolve_reference_date(value: str | None) -> date:
    """--reference-date > REFERENCE_DATE env > today."""
    value = value or os.environ.get("REFERENCE_DATE") or ""
    return date.fromisoformat(value) if value.strip() else date.today()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract credential fields from a document.")
    parser.add_argument("path", type=Path, help="A document or a folder of documents")
    parser.add_argument("--out-dir", type=Path, help="Write one <document>.json per input here")
    parser.add_argument("--model", default=None, help=f"Model id (default: {default_model()})")
    parser.add_argument("--reference-date", help="YYYY-MM-DD used for expiration_status (default: REFERENCE_DATE env or today)")
    parser.add_argument("--window-days", type=int, default=int(os.environ.get("EXPIRING_WINDOW_DAYS") or DEFAULT_WINDOW_DAYS))
    parser.add_argument("--dpi", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--meta-log", type=Path, help="Append one JSON line of metadata per document here")
    args = parser.parse_args()

    reference_date = resolve_reference_date(args.reference_date)

    if args.path.is_dir():
        files = sorted(p for p in args.path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    else:
        files = [args.path]
    if not files:
        sys.exit(f"no supported documents in {args.path}")

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        out = extract(
            file,
            reference_date,
            model=args.model,
            dpi=args.dpi,
            max_pages=args.max_pages,
            window_days=args.window_days,
        )
        result, meta = out["result"], out["meta"]
        text = json.dumps(result, indent=2, ensure_ascii=False)

        if args.out_dir:
            target = args.out_dir / f"{file.stem}.json"
            target.write_text(text + "\n")
            status = f"ERROR: {meta['error']}" if "error" in meta else f"{meta.get('latency_s')}s"
            print(f"{file.name} -> {target}  [{status}]")
        else:
            print(f"# {file.name}\n{text}")

        if args.meta_log:
            with args.meta_log.open("a") as fh:
                fh.write(json.dumps(meta, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

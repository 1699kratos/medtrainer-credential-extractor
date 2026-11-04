"""Field-level eval for the credential extractor.

Compares one output JSON per document (as written by `extract.py --out-dir`)
with the expected JSON in `expected/` and reports accuracy per field, per
document and overall.

Usage:
    python eval.py outputs/baseline                    # print the report
    python eval.py outputs/baseline --label baseline   # also save results/baseline.json

Comparison rules (deliberately simple and documented, so the number is honest):
  * Strings: trimmed, internal whitespace collapsed, case-insensitive.
    "MD.41872" == "md.41872", but "MD 41872" != "MD.41872".
  * Dates: exact ISO string (YYYY-MM-DD). "12/15/2026" != "2026-12-15".
  * null only matches null.
  * A missing field, a missing output file or an {"error": ...} payload
    counts as wrong for every field of that document.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FIELDS = [
    "is_credential",
    "holder_name",
    "credential_type",
    "license_number",
    "issuing_authority",
    "issue_date",
    "expiration_date",
    "expiration_status",
]


def normalize(value):
    """Normalize a value for comparison. Only strings are touched."""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().casefold()
    return value


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def evaluate(outputs_dir: Path, expected_dir: Path) -> dict:
    expected_files = sorted(p for p in expected_dir.glob("*.json") if not p.name.startswith("_"))
    docs = []
    for exp_path in expected_files:
        expected = load_json(exp_path)
        actual = load_json(outputs_dir / exp_path.name)
        usable = isinstance(actual, dict) and "error" not in actual

        fields = {}
        for field in FIELDS:
            got = actual.get(field, "<missing>") if usable else "<missing>"
            ok = usable and normalize(got) == normalize(expected.get(field))
            fields[field] = {"expected": expected.get(field), "actual": got, "ok": ok}

        docs.append({
            "doc": exp_path.stem,
            "fields": fields,
            "correct": sum(f["ok"] for f in fields.values()),
        })

    n_docs = len(docs)
    per_field = {
        field: (sum(d["fields"][field]["ok"] for d in docs) / n_docs if n_docs else 0.0)
        for field in FIELDS
    }
    total_cells = n_docs * len(FIELDS)
    overall = sum(d["correct"] for d in docs) / total_cells if total_cells else 0.0

    return {
        "outputs_dir": str(outputs_dir),
        "n_docs": n_docs,
        "overall_accuracy": overall,
        "perfect_docs": sum(d["correct"] == len(FIELDS) for d in docs),
        "per_field": per_field,
        "docs": docs,
    }


def pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def print_report(result: dict) -> None:
    print(f"\n== Eval: {result['outputs_dir']}  ({result['n_docs']} docs) ==\n")
    print(f"{'field':<20} {'accuracy':>9}")
    print("-" * 30)
    for field, acc in result["per_field"].items():
        print(f"{field:<20} {pct(acc):>9}")
    print("-" * 30)
    print(f"{'OVERALL':<20} {pct(result['overall_accuracy']):>9}")
    print(f"perfect documents: {result['perfect_docs']}/{result['n_docs']}\n")

    print(f"{'doc':<8} {'ok':>5}   mismatches")
    print("-" * 60)
    for d in result["docs"]:
        bad = [f for f, v in d["fields"].items() if not v["ok"]]
        print(f"{d['doc']:<8} {d['correct']:>2}/{len(FIELDS)}   {', '.join(bad) if bad else '-'}")

    mismatches = [(d["doc"], f, v) for d in result["docs"] for f, v in d["fields"].items() if not v["ok"]]
    if mismatches:
        print("\nDetails:")
        for doc, field, v in mismatches:
            print(f"  {doc}.{field}: expected {v['expected']!r}, got {v['actual']!r}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate extractor outputs against the expected JSON.")
    parser.add_argument("outputs", type=Path, help="Folder with one <doc>.json per document")
    parser.add_argument("--expected", type=Path, default=Path("expected"), help="Folder with expected JSON")
    parser.add_argument("--label", help="Save the full result as results/<label>.json")
    args = parser.parse_args()

    result = evaluate(args.outputs, args.expected)
    print_report(result)

    if args.label:
        out = Path("results") / f"{args.label}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(f"saved {out}")


if __name__ == "__main__":
    main()

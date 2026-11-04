"""LLM-as-judge for the bonus `summary` field.

A summary has no single correct string, so it cannot be compared with ==.
Instead a judge model scores each summary against the *expected* fields of
its document (not the document image) on three pass/fail criteria:

  faithful  nothing in the summary contradicts the expected fields (judge)
  complete  it names the holder, the credential type and the expiration,
            or says the document is not a credential (judge)
  concise   at most two sentences and at most 60 words (computed in code:
            a first version asked the judge, and it failed two-sentence
            summaries for being "longer than necessary")

The judge is a different model from the extractor on purpose (a model grading
its own output tends to be lenient). Usage:

  python judge.py results/outputs/<run> [--expected expected] [--label NAME] [--model MODEL]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from credential_extractor.client import ProviderError, chat, resolve_provider
from credential_extractor.pipeline import parse_json

JUDGED = ["faithful", "complete"]
CRITERIA = JUDGED + ["concise"]
MAX_SENTENCES, MAX_WORDS = 2, 60

# gpt-4.1-mini as judge failed a correct summary of the non-credential (al_03); gpt-4.1 did not.
JUDGE_MODELS = {"openrouter": "openai/gpt-4.1", "openai": "gpt-4.1"}

SYSTEM = """You are a strict reviewer of document summaries for a healthcare credentialing team.
You answer only with JSON."""

USER = """Below are the verified fields of a document and a summary written by another system.
Judge the summary on two criteria. Answer true only when the criterion is clearly met.

faithful: the summary states nothing that contradicts the verified fields (name, credential
  type, issuer, dates, whether it is a credential). Extra printed details are fine; wrong
  values are not. The same value in another form is not a contradiction: a name with or
  without degree suffixes, a date in any format, an issuer written in a longer or shorter
  form. A remark that the document is a sample, test or synthetic document is a printed
  detail, not a contradiction. If is_credential is false, every other verified field is null
  by design: then faithful means only that the summary describes the document as something
  other than a credential, whatever details it adds.
complete: a reviewer reading only the summary learns who the credential belongs to, what
  credential it is, and when it expires (or that it has no expiration). If is_credential is
  false, complete means the summary says what the document is instead.

Verified fields:
{expected}

Summary:
{summary}

Return exactly:
{{"faithful": true|false, "complete": true|false,
  "reasons": {{"faithful": "...", "complete": "..."}}}}"""


_SENTENCE_END = re.compile(r"[.!?]+(?=\s+[A-Z\"'(])")


def count_sentences(text: str) -> int:
    """Sentence ends are '.', '!' or '?' followed by whitespace and a capital letter.

    'Jr. by', 'No. 123' and '03/31/2028.' at the end do not split; good enough
    for one- or two-sentence summaries.
    """
    text = text.strip()
    if not text:
        return 0
    return len(_SENTENCE_END.findall(text)) + 1


def check_concise(summary: str) -> tuple[bool, str]:
    sentences, words = count_sentences(summary), len(summary.split())
    ok = sentences <= MAX_SENTENCES and words <= MAX_WORDS
    return ok, f"{sentences} sentence(s), {words} words (limits: {MAX_SENTENCES}, {MAX_WORDS})"


def judge_one(summary: str | None, expected: dict, model: str) -> dict:
    if not summary:
        return {c: False for c in CRITERIA} | {"reasons": {c: "no summary produced" for c in CRITERIA}}
    concise, concise_reason = check_concise(summary)
    expected_fields = {k: v for k, v in expected.items() if k != "expiration_status"}
    user = USER.format(expected=json.dumps(expected_fields, indent=2), summary=summary)
    try:
        answer = chat(SYSTEM, user, images=[], model=model)
        verdict = parse_json(answer["text"])
    except (ProviderError, json.JSONDecodeError, KeyError) as exc:
        verdict, cost = {"reasons": {c: f"judge failed: {exc}" for c in JUDGED}}, None
    else:
        cost = answer["meta"].get("cost_usd")
    return {c: bool(verdict.get(c)) for c in JUDGED} | {
        "concise": concise,
        "reasons": verdict.get("reasons", {}) | {"concise": concise_reason},
        "judge_cost_usd": cost,
    }


def run(outputs_dir: Path, expected_dir: Path, model: str) -> dict:
    docs = []
    for exp_path in sorted(expected_dir.glob("*.json")):
        if exp_path.name.startswith("_"):
            continue
        out_path = outputs_dir / exp_path.name
        summary = json.loads(out_path.read_text()).get("summary") if out_path.exists() else None
        verdict = judge_one(summary, json.loads(exp_path.read_text()), model)
        docs.append({"doc": exp_path.stem, "summary": summary, **verdict})
    n = len(docs)
    return {
        "judge_model": model,
        "per_criterion": {c: sum(d[c] for d in docs) / n for c in CRITERIA},
        "all_pass": sum(all(d[c] for c in CRITERIA) for d in docs),
        "docs": docs,
    }


def print_report(report: dict, outputs_dir: Path) -> None:
    n = len(report["docs"])
    print(f"\n== Summary judge: {outputs_dir}  ({n} docs, judge: {report['judge_model']}) ==\n")
    for c in CRITERIA:
        print(f"{c:<10} {report['per_criterion'][c]:>6.1%}")
    print(f"all three pass: {report['all_pass']}/{n}\n")
    for d in report["docs"]:
        failed = [c for c in CRITERIA if not d[c]]
        print(f"{d['doc']:<8} {'PASS' if not failed else 'FAIL: ' + ', '.join(failed)}")
        for c in failed:
            print(f"           {c}: {d['reasons'].get(c, '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("outputs", type=Path)
    parser.add_argument("--expected", type=Path, default=Path("expected"))
    parser.add_argument("--label", help="save results/judge_<label>.json")
    parser.add_argument("--model", default=os.environ.get("JUDGE_MODEL") or JUDGE_MODELS[resolve_provider()["name"]])
    args = parser.parse_args()

    report = run(args.outputs, args.expected, args.model)
    print_report(report, args.outputs)
    if args.label:
        path = Path("results") / f"judge_{args.label}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"\nsaved {path}")


if __name__ == "__main__":
    main()

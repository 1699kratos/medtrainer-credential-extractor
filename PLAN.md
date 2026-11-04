# Implementation Plan – Credential Extractor (MedTrainer AI Engineer Challenge)

Start date: 2026-11-03. Due: repository + deployed URL by 2026-11-10. Then a 30-minute interview about process and decisions.

Source of truth: the repo's `README.md` as received (now `CHALLENGE.md`). It is newer and more precise than the PDF; see section 0.3.

---

## Table of contents

0. Context and prior findings
1. Phase 1 – Repository and environment
2. Phase 2 – Build the eval and measure the baseline
3. Phase 3 – Architecture of the new extractor
4. Phase 4 – Iteration 1: prompt + post-processing
5. Phase 5 – Iteration 2: input quality + structured outputs
6. Phase 6 – Iteration 3: model comparison and cost
7. Phase 7 – Expiration flag (configurable reference date)
8. Phase 8 – Optional bonus: summary + LLM-as-judge
9. Phase 9 – Deployment with an upload interface
10. Phase 10 – Final documentation
11. Phase 11 – Delivery checklist and interview prep
12. API key budget
13. Risks and mitigations
14. Decision log (filled in as work progresses)

---

## 0. Context and prior findings

### 0.1 What they ask for (summary of the brief)

| # | Step | Concrete deliverable |
|---|------|----------------------|
| 1 | Build the eval first | A script that compares output vs `expected/` and reports accuracy per field. Run it on the base `extract.py` = baseline. |
| 2 | Improve the system | At least 2 iterations with before/after numbers for each. |
| 3 | Flag expirations | `expiration_status` computed against a configurable reference date. For the eval: `2026-11-01`, 60-day window (`expected/_reference.json`). |
| 4 | Deploy it | A public URL with an interface to upload a document and see the JSON. |
| 5 | Write a document | What failed, what changed and how much it improved; model chosen and why; approximate cost per document; production plan with PHI (security, cost, monitoring). |
| Bonus | Summary + LLM-as-judge | A free-text summary field, evaluated by a judge model. |

Evaluation criteria: end to end, extraction quality and an honest eval, hard cases, production judgment, communication with numbers, working deployment. They will test with documents we have not seen: **avoid overfitting to the 8 samples**.

### 0.2 The 8 documents and their traps

All are scanned (synthetic) PDFs with a noisy embedded OCR text layer (seals get mixed into the text). None is a standalone image, but the brief says "image or PDF" and the deployment must accept both.

| Doc | Pages | Main trap | Relevant expected values |
|-----|-------|-----------|--------------------------|
| `al_01` | 1 | Two copies of the same certificate (large + detachable card). Name printed as "Tamsin Rae Holloway MD". Has issue date `03/14/2012`. | `credential_type: "Certificate of Registration"`, name without "MD" |
| `al_02` | 1 | **No expiration date.** Issue date already in ISO (`2009-07-15`). Name with ", MD". | `expiration_date: null`, `expiration_status: "no_expiration"` |
| `al_03` | 1 | **Not a credential.** A renewal notice that explicitly says "It is not a license, permit or certificate". It has a name, a license number and dates: a naive model extracts it fully. | `is_credential: false` and **every** other field `null`, including `expiration_status` |
| `ny_01` | 1 | Letter on top, certificate below. Name in "LASTNAME FIRSTNAME INITIAL" format. There is a "Certificate Number" that is not the license number. No issue date. | `holder_name: "HALVORSEN INGRID S"`, `license_number: "301455-01"`, `issue_date: null` |
| `ny_02` | 1 | **Two-digit year**: "through 12/15/26". | `expiration_date: "2026-12-15"`, `expiring_soon` |
| `tx_01` | 2 | **Page rotated 90°.** Page 2 is the wallet card, also rotated. Name with an accent ("LUCÍA") and ", MD". | `credential_type: "Physician License"`, `holder_name: "ADRIANA LUCÍA FERRER"` |
| `tx_02` | 2 | Rotated. Different issuer than `tx_01` (Physician Assistant Licensing Board). Expired on `02/28/2026`. | `expiration_status: "expired"` |
| `tx_03` | 2 | Rotated 90° **in the opposite direction** to tx_01/tx_02. Name "ROBERT ALAN MITCHELL JR., DO". Expires `11/30/2026`. | `holder_name: "ROBERT ALAN MITCHELL JR."` (degree dropped, "JR." kept), `expiring_soon` |

General rules derived from the expected files (and reasonable for new documents, not just these):

- `holder_name`: as printed (same order and casing), **without** degree/title suffixes (MD, DO, PA, RN...), **with** generational suffixes (Jr., III).
- `credential_type`: the type/title the document states (e.g. "Physician License", "Certificate of Registration"), not an invented category.
- `license_number`: as printed, without extra spaces. Do not confuse with receipt #, certificate #, notice #, board action #.
- `issuing_authority`: name of the issuing body, including the state, without address or PO box.
- `issue_date` / `expiration_date`: only if printed; never infer. Two-digit years are read as 20YY.
- `expiration_status`: **computed in code, never decided by the model.**
- If `is_credential` is `false`, everything else is `null`.

### 0.3 Differences between the PDF and the README (verified)

- README: `expiration_status` is `string or null`, `null` when `is_credential=false`. PDF: just `string`. README wins (matches `expected/al_03.json`).
- README fixes the reference date (`2026-11-01`, 60 days) and lists it as provided material. PDF only says "the date included in the materials".
- The PDF contradicts itself: "7 days" and "within 3 days". README and email say 7 days.
- The email (not the README nor the PDF) asks **not to use the key with AI coding tools**. The key is consumed only by the extractor (CLI, eval and deployment).

### 0.4 The base script (`extract.py`)

- Renders **only the first page** of the PDF at **100 dpi** and sends it as PNG.
- Single-instruction prompt, no format rules, no JSON mode. Asks the model to compute `expiration_status` without giving it a reference date.
- Fragile JSON parsing (only strips the ```` ``` ```` fence).
- No retries, no validation, no fixed temperature.
- Default model: `deepseek/deepseek-v4.1-flash` via OpenRouter.

Expected baseline failures: `al_03` extracted as a credential, dates in non-ISO formats, `expiration_status` invented or inconsistent, names with "MD", rotated documents misread, possible JSON errors.

---

## 1. Phase 1 – Repository and environment

Goal: an own, clean repository with the untouched starter as the first commits, so the history tells the story.

1.1. Create a new GitHub repository (public, or private with access for the reviewers). Suggested name: `medtrainer-credential-extractor`. No fork: the history must be our own.
1.2. In the current clone, point `origin` at the new repository. Keep the 2 original starter commits as the base.
1.3. Environment: `python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`. Check that `python extract.py --help` runs.
1.4. Secrets: `cp .env.example .env` and fill in `OPENROUTER_API_KEY` (theirs) and, optionally, `OPENAI_API_KEY` + `OPENAI_MODEL` (own, development only). `LLM_PROVIDER` selects which one is used (`openrouter` by default). `.env` is already in `.gitignore`. Never print keys in logs or commits. Load with `set -a; source .env; set +a` or with `python-dotenv`.
1.5. Move the brief: `git mv README.md CHALLENGE.md` and create a new `README.md` (filled in during Phase 10, but with "how to run" from the start).
1.6. Target repository layout at the end:

```
.
├── CHALLENGE.md              # original brief (was README.md)
├── README.md                 # own documentation: how to run, results, decisions, PHI
├── PLAN.md                   # this file
├── extract_baseline.py       # the original script, untouched (reference for the baseline)
├── extract.py                # new CLI, same interface as the original
├── eval.py                   # per-field eval
├── judge.py                  # (bonus) LLM-as-judge for the summary
├── app.py                    # web interface (Gradio) for the deployment
├── credential_extractor/     # package with the logic, shared by CLI, eval and app
│   ├── __init__.py
│   ├── loader.py             # PDF/image -> list of PNG images (dpi, rotation, pages)
│   ├── prompt.py             # system prompt + per-field rules
│   ├── schema.py             # Pydantic model + JSON schema for structured outputs
│   ├── client.py             # LLM call: provider, retries, timeout, usage/cost
│   ├── postprocess.py        # date normalization, expiration_status, nulls
│   └── pipeline.py           # extract(path, model, reference_date) -> dict
├── tests/
│   └── test_postprocess.py   # dates, expiration windows, nulls
├── results/
│   ├── RESULTS.md            # before/after table per iteration
│   ├── 00_baseline.json      # eval.py output per iteration
│   ├── 01_prompt.json
│   ├── 02_input.json
│   └── outputs/<iteration>/  # raw JSON outputs of each run (for auditing)
├── docs/                     # samples (unchanged)
├── expected/                 # expected outputs (unchanged)
├── requirements.txt
├── .env.example
└── .gitignore
```

1.7. Commit: `chore: project scaffold` (structure and minimal README only).

Exit criterion: `python extract_baseline.py docs/tx_01.pdf` works with the key.

---

## 2. Phase 2 – Build the eval and measure the baseline

Goal: an honest, reproducible number before changing anything.

### 2.1 Design of `eval.py`

- Input: a folder with one `<doc>.json` per document (what `extract.py --out-dir` produces). `--expected` defaults to `expected/`. Files starting with `_` are ignored.
- Compares the **8 fields** of each document.
- Comparison rules (documented in the docstring and in the README, because "how it is measured" is part of what they evaluate):
  - Strings: trim, collapse internal whitespace, case-insensitive. Nothing else (no fuzzy matching in the main metric).
  - Dates: exact equality of the ISO string.
  - `null` only matches `null`. A missing field counts as an error.
  - Missing output file or a payload with `"error"`: all 8 fields count as errors (the doc is not excluded; excluding it would inflate the number).
- Output:
  - Accuracy table per field (8 rows), overall accuracy (correct cells / 64), perfect documents (n/8).
  - List of mismatches with `expected` vs `actual` per doc and field.
  - `--label <name>` saves `results/<name>.json` with the full detail, so the README can cite verifiable numbers.
- Optional secondary metric (informational only, never the main one): normalized similarity for `credential_type` and `issuing_authority`, the most subjective fields. Reported separately to show when an error is wording rather than reading.

### 2.2 Testing the eval without spending API credit

- Run `eval.py` against a copy of `expected/` used as output: must be 100%.
- Run against a deliberately broken set (missing file, `{"error": ...}`, false-positive credential): must report every mismatch.

### 2.3 Baseline

```
python extract_baseline.py docs/ --out-dir results/outputs/00_baseline/
python eval.py results/outputs/00_baseline/ --label 00_baseline
```

- Also record the cost of the run (see Phase 12). If the base script does not report `usage`, note the spend by reading the OpenRouter dashboard before/after.
- Run the baseline **twice** if budget allows, to see the variance of the model without a fixed temperature. Record both numbers; use the first as the official baseline.
- Record the `00_baseline` row in `results/RESULTS.md` and the list of what failed (this feeds the "what failed at first" part of the final document).

Commits: `feat: field-level eval script`, `results: baseline run`.

Exit criterion: a per-field accuracy table for the baseline and the concrete list of failures.

---

## 3. Phase 3 – Architecture of the new extractor

Goal: separate responsibilities so each iteration changes one thing and can be measured.

```
document (pdf/png/jpg)
   │
   ▼
loader.py ──► [PNG image(s), base64]        (dpi, rotation, pages, size limit)
   │
   ▼
client.py ──► chat/completions              (provider, model, temperature 0, json schema, retries, usage.cost)
   │
   ▼
schema.py ──► Pydantic validation of the raw JSON
   │
   ▼
postprocess.py ──► dates to ISO, nulls when not a credential, expiration_status(reference_date)
   │
   ▼
final dict (8 fields) + metadata (provider, model, cost, latency, raw)
```

Design decisions:

- `pipeline.extract(path, model, reference_date, ...)` is the single function used by the CLI, the eval and the app. It prevents drift between what is measured and what is deployed.
- The model **only reads**; it does not compute or decide status. Everything deterministic lives in Python (dates, window, nulls).
- The output separates `result` (the exact 8 fields of the contract) from `meta` (provider, model, cost, tokens, latency, pages sent, raw model output). The CLI writes only `result` to the eval JSONs; `meta` goes to a separate log or stderr.
- `extract.py` keeps the original interface (`python extract.py docs/ --out-dir outputs/`, `--model`, `OPENROUTER_MODEL`) and adds `--reference-date` and `--dpi`.
- **Configurable provider in `client.py`.** OpenAI and OpenRouter share the `chat/completions` format, so the client reads `LLM_PROVIDER` (`openrouter` default | `openai`) and resolves base URL, key and model from it (`OPENROUTER_*` or `OPENAI_*`). Usage rules: the own OpenAI key is for developing and debugging without spending the $5; **every reported number** (baseline, final run of each iteration, model comparison) and the deployment run on OpenRouter with their key. If the winning model is an OpenAI one, the deployment uses the same model via OpenRouter (`openai/<model>`), so development and production are comparable. Provider differences (`json_schema` support, the `usage.cost` field that only OpenRouter returns) are encapsulated in `client.py`; `meta` records provider and model for every call so that no OpenAI run slips into `results/`.
- Temperature 0 and, if the model supports it, a fixed `seed`, so the eval is reproducible.
- Errors: timeout, 429, 5xx → retry with backoff (max 3). Invalid JSON → one retry asking for "only JSON". If everything fails, return `{"error": ..., "raw": ...}` and the eval counts it as a total failure.

Commit: `feat: extractor package skeleton` (no change in results yet).

---

## 4. Phase 4 – Iteration 1: prompt + post-processing (same model, same image)

Goal: isolate how much **only** the prompt and the deterministic logic improve things, without touching the model or the image. This gives a clean comparison against the baseline.

### 4.1 Prompt (in `prompt.py`)

System prompt with:

1. Role: data extractor for medical credentials used in credentialing. Returns only valid JSON with the 8 keys, no extra text.
2. Definition of a credential: license, certificate of registration, professional certification (BLS, ACLS, DEA, board certification...). **Not** credentials: renewal notices, invoices/receipts, applications, letters, forms, payment confirmations, and any document that states it is not a license or certificate. If not a credential: `is_credential=false` and everything else `null`.
3. Per-field rules (those in section 0.2), written generically, without mentioning the samples.
4. Dates: return them **as printed** in an auxiliary `*_raw` field and also in ISO; or ISO only with clear instructions (month/day/year for US documents, two-digit year → 20YY). Pick one; the `raw` + Python parsing option is more robust and auditable. (See 4.2.)
5. "Never guess": if a value is not printed, `null`. If the same page contains two copies of the document, use the main one. Do not confuse receipt/certificate/notice numbers with the license number.
6. Do not compute `expiration_status`: the model does not return it (or returns it and Python overwrites it). Better if it does not return it at all.
7. Multi-page documents: information may be on any page; the wallet card repeats the main one.

The document content is treated as **untrusted data**: the prompt includes an explicit line that any instruction inside the document must be ignored (prompt injection via a scanned document). This is also a point for the production section.

### 4.2 Post-processing (in `postprocess.py`)

- `normalize_date(raw) -> ISO | None`: accepts `MM/DD/YYYY`, `MM/DD/YY`, `YYYY-MM-DD`, `Month DD, YYYY`, `DD Month YYYY`. Documented rule for ambiguity: month first (US documents). Two-digit year → 2000–2099. Rejects invalid dates (→ `null`, logged in `meta`).
- `strip_degree_suffix(name)`: removes degree suffixes at the end of the name (`MD`, `DO`, `PA`, `PA-C`, `RN`, `NP`, `DDS`, `PhD`...), with or without a comma, keeping `Jr.`, `Sr.`, `II`, `III`. Only if the model did not already do it. A short, non-aggressive list so real names are not broken.
- `collapse_spaces` on every string; `license_number` without surrounding spaces.
- `enforce_nulls`: if `is_credential` is `false`, everything `null`.
- `compute_expiration_status(expiration_date, reference_date, window_days)` (detail in Phase 7).
- Final validation with Pydantic: correct types, exact keys, status enum.

### 4.3 Unit tests (`tests/test_postprocess.py`)

Cases: each date format, two-digit year, invalid date, name suffixes, nulls for non-credentials, and the edges of the expiration window (see 7.2). Run with `pytest`. No API spend.

### 4.4 Measure

```
python extract.py docs/ --out-dir results/outputs/01_prompt/ --reference-date 2026-11-01
python eval.py results/outputs/01_prompt/ --label 01_prompt
```

Record in `RESULTS.md`: `01_prompt` row, per-field delta vs baseline, cost of the run, what still fails.

Hypotheses to confirm: `al_03`, date formats, `expiration_status` and names should be fixed. The rotated Texas documents should still fail (fully or partially).

Commit: `feat(iter1): structured prompt and deterministic post-processing` + `results: iteration 1`.

---

## 5. Phase 5 – Iteration 2: input quality + structured outputs

Goal: improve what the model **sees** and harden the output format.

### 5.1 Loader (`loader.py`)

- DPI: raise from 100 to 150–200. Measure the resulting PNG size (image tokens ≈ cost). Pick the lowest dpi that does not lose accuracy.
- **All pages**, with a cap (e.g. 3) to control cost. Each page goes as an image in the same message.
- **Orientation correction.** Options, cheapest first:
  1. Use the PDF text layer: `page.get_text("dict")` gives the direction (`dir`) of each line; if most are vertical, rotate 90° or 270° before rendering. Works on PDFs with embedded OCR (the samples have it). Free.
  2. For images without a text layer (photos, PNG): try lightweight local OCR (e.g. `pytesseract` with `--psm 0` for orientation detection) if available; otherwise send the image as-is and rely on the model. Document the limitation.
  3. Last resort: ask the model for the orientation in a first cheap call. Rejected for cost/latency unless needed.
- Input images (png/jpg/webp): resize if the longer side exceeds ~2000 px; convert to PNG or JPEG at reasonable quality. File size limit (e.g. 10 MB) for the deployment.
- Considered and rejected: sending the PDF directly to OpenRouter with its PDF parser (`file` + engine `pdf-text`/`mistral-ocr`/`native`). `pdf-text` would use the noisy OCR layer; `mistral-ocr` costs extra; `native` depends on the model. Rendering to an image is model-independent and lets us control rotation and dpi.

### 5.2 Structured outputs (`client.py` + `schema.py`)

- Define the schema with Pydantic and pass it as `response_format: {"type": "json_schema", "json_schema": {"name": ..., "strict": true, "schema": ...}}` in the request. Not every model supports it; detect the error and fall back to `{"type": "json_object"}` and, failing that, to prompt-only with robust parsing (extract the first balanced `{...}`).
- Pass `"usage": {"include": true}` so OpenRouter returns the real cost of each call in `usage.cost`. Store it in `meta`.
- Optional `HTTP-Referer` / `X-Title` headers to identify the app in the dashboard.

### 5.3 Measure

Same as 4.4 with label `02_input`. Record chosen dpi, pages sent, cost per document, per-field delta. If rotation fixed Texas, say so with the numbers.

Commit: `feat(iter2): page orientation, all pages, higher dpi, json schema output` + `results: iteration 2`.

---

## 6. Phase 6 – Iteration 3: model comparison and cost

Goal: choose the model with data, not intuition. "Your model choices and spend are part of the picture."

6.1. Candidates (3 at most to protect the budget): the default `deepseek/deepseek-v4.1-flash` (already measured in 00–02), a cheap "flash/mini" vision model from another family, and a model one step up as a quality ceiling. Pick the exact IDs from OpenRouter's model page on the day of the run and note price per M input/output/image tokens in `RESULTS.md`.
6.2. Run the **same pipeline** (iteration 2) with each model on the 8 docs. Labels `03_model_<name>`.
6.3. Comparison table: overall accuracy, per-field accuracy, perfect docs, total run cost, average cost per document (from `usage.cost`), average latency, `json_schema` support.
6.4. Selection criterion, in this order: (1) accuracy on the hard cases (`al_03`, rotated, dates), (2) cost per document, (3) latency and structured output support. If two tie on accuracy, the cheaper one wins.
6.5. Set the winner as the default in `extract.py` and in the deployment. Keep `--model` to try others.

Commit: `results: model comparison` + `feat: set default model to <winner>`.

---

## 7. Phase 7 – Expiration flag (configurable reference date)

Goal: satisfy step 3 of the brief deterministically and testably.

### 7.1 Configuration

- Priority: `--reference-date YYYY-MM-DD` argument > `REFERENCE_DATE` environment variable > today (UTC). Window: `--expiring-window-days` > `EXPIRING_WINDOW_DAYS` > 60.
- For the eval, `extract.py` reads `expected/_reference.json` when `--reference-file` is passed (or the eval documents the command with `--reference-date 2026-11-01`). That way the numbers do not change over time.
- In the deployment, the default is "today", and the interface shows which date was used and allows changing it (optional field).

### 7.2 Rules

With `exp` = expiration_date, `ref` = reference_date, `w` = window:

| Case | Result |
|------|--------|
| `is_credential == false` | `null` |
| `exp == null` | `"no_expiration"` |
| `exp < ref` | `"expired"` |
| `ref <= exp <= ref + w` | `"expiring_soon"` |
| `exp > ref + w` | `"valid"` |

Documented decision: on the expiration day the credential **is still valid** (counts as `expiring_soon`, not `expired`); the window is inclusive at both ends. Check against the samples with `ref = 2026-11-01`: `2026-02-28` → expired, `2026-11-30` → expiring_soon, `2026-12-15` → expiring_soon, `2027-08-31` → valid, `2027-12-31` → valid, `2028-03-31` → valid, `null` → no_expiration.

### 7.3 Tests

Edges: `exp == ref`, `exp == ref + w`, `exp == ref + w + 1 day`, `exp == ref - 1 day`, `null`, non-credential. Already covered in `tests/test_postprocess.py` (Phase 4.3); confirmed here.

---

## 8. Phase 8 – Optional bonus: summary + LLM-as-judge

Only if Phases 1–7 and 9–10 are closed and budget remains (> $1.5).

8.1. `summary` field (string, 1–2 sentences): what the document is, whose it is, who issued it, when it expires. Requested in the same prompt (single call, marginal cost). It lives **outside** the 8 contract fields so their eval is not broken: the CLI output keeps the 8 keys and `summary` is added as a ninth only with `--summary`. Confirm their eval ignores extra keys; if in doubt, keep it in `meta`.
8.2. `judge.py`: for each document, a cheap model different from the extractor receives (a) the image or the expected JSON as ground truth and (b) the summary, and returns a 1–5 score with a rubric: faithfulness (no invented data), coverage (holder, type, issuer, expiration or its absence), brevity, and an explicit "not a credential" when applicable. JSON output (`score`, `reasons`). Report mean and distribution in `results/judge_<iter>.json`.
8.3. Document the judge's limitations (bias toward its own style, variance) and that it is used as a signal, not a hard metric.

---

## 9. Phase 9 – Deployment with an upload interface

Goal: a URL they open, upload a PDF or image, and see the JSON. "Easy to try" matters more than pretty.

### 9.1 Platform

Recommendation: **Hugging Face Spaces with Gradio**. Reasons: free, does not sleep on inactivity like Render's free tier (which takes ~1 min to wake up and ruins the first impression), supports file uploads and environment secrets, and Gradio also exposes an API endpoint in case they want to test by script. Equally valid alternative: FastAPI + minimal HTML on Render/Railway (more control, more work). Streamlit Cloud also works.

### 9.2 `app.py`

- A `gr.File` (pdf/png/jpg/jpeg/webp, 10 MB cap) + optional reference date field (default today) + button. Output: `gr.JSON` with the 8 fields and, in an accordion, `meta` (model, cost, latency, pages). Optional: preview of the rendered image so they see what the model read.
- Uses `credential_extractor.pipeline.extract`, the same code as the eval.
- Secrets: `OPENROUTER_API_KEY` as a Space secret; `OPENROUTER_MODEL` and `REFERENCE_DATE` as variables. Never in the repo.
- Minimal PHI handling already in the demo: the uploaded file is processed in memory/tmp and deleted when done; no documents or results are stored; logs without document content (only model name, tokens, cost, latency, errors).
- Basic protection against burning the credit: size limit, page limit (3), one request at a time per session (`concurrency_limit`), and a cumulative spend cap read from `usage.cost` that disables the button when exceeded (e.g. $2 in the demo). Clear message if credit runs out.
- Readable error messages: unsupported file, model not responding, invalid JSON.

### 9.3 Steps

1. `requirements.txt` with pinned versions (`gradio`, `pymupdf`, `requests`, `pydantic`, `python-dotenv`).
2. Test locally: `python app.py`, upload the 8 docs and a phone photo of a printed document (generalization test outside the samples).
3. Create the Space (Gradio SDK), upload the code (the Space can sync from the GitHub repo or receive a push to the Space repo). Configure secrets.
4. Test the URL from another device/network. Measure end-to-end latency.
5. Note the URL and how to use it in `README.md`.

Commit: `feat: gradio app for upload-and-extract` + `docs: deployment`.

---

## 10. Phase 10 – Final documentation

Goal: cover step 5 of the brief "with numbers". Lives in `README.md` (or `README.md` + `docs/WRITEUP.md` if it grows too much). In English, because the brief, the repo and the reviewers are.

Structure:

1. **What this is** (2 lines) + deployment URL + screenshot.
2. **Quick start**: install, environment variables, one document, a folder, run the eval, run tests.
3. **Architecture**: the Phase 3 diagram and per-module responsibilities.
4. **Eval methodology**: what it compares, normalization rules, why a missing file counts as 8 errors, observed variance between runs.
5. **Results**: iteration × field table with accuracy, perfect docs, cost per run and per document. Same numbers as `results/*.json`.
6. **What failed and what changed** (one subsection per iteration): concrete failures (doc and field), change applied, delta. Honesty: what did not improve, too.
7. **Model choice**: the Phase 6 table and the selection criterion.
8. **Cost per document**: measured with `usage.cost`, approximate breakdown (image, prompt, output), projection to 1k/10k/100k documents per month.
9. **Handling hard cases**: non-credential, no expiration, date formats, rotation, multi-page, two-digit year, name suffixes. What is a general rule vs. a known limitation.
10. **Generalization and known limitations**: all samples are scanned PDFs from 3 states; photos, card-style certifications (BLS/ACLS), documents in other languages, native non-scanned PDFs, documents with several credentials. What would happen and what I would do.
11. **Taking this to production with PHI**:
    - *Security*: the document is PHI. Encryption in transit and at rest, no document persistence in the extraction layer, logs without PHI (metadata only), access control and audit trail, minimal retention and verifiable deletion, per-tenant isolation. Model provider with a **BAA** and zero data retention: OpenRouter does not sign BAAs, so in production the same pipeline would point at a provider that does (Azure OpenAI, AWS Bedrock, Google Vertex, Anthropic with a BAA). The abstraction in `client.py` exists for that. Treat document content as untrusted (prompt injection).
    - *Cost*: cheap model by default and escalation to a better one only when confidence is low (cascade); cache by document hash; minimum viable dpi; page limit; batch/async for volume; per-tenant budgets and alerts.
    - *Monitoring*: latency, error rate, cost per doc, distribution of `is_credential` and `expiration_status` (drift); sampling with human review and continuous eval against a golden set that grows with corrected cases; mandatory human-in-the-loop for low-confidence fields or conflicts (the model can return a per-field `confidence`); prompt and model versioning with regression eval before every change; alerts on accuracy drops on the golden set.
12. **How I used AI tools**: what the agent did, what I decided, what I reviewed by hand. They will ask in the interview.
13. **Development keys**: which model and own key were used for development, approximate cost, and the explicit statement that every reported number and the deployment use OpenRouter with the provided key.
14. **Time spent**: honest.

---

## 11. Phase 11 – Delivery checklist and interview prep

### 11.1 Before sending

- [ ] Clean `git clone` into another folder + `pip install -r requirements.txt` + `python extract.py docs/tx_01.pdf` works following only the README.
- [ ] `python eval.py results/outputs/<final>/` reproduces the README numbers.
- [ ] `pytest` green.
- [ ] The deployed URL works from another device; tested with the 8 samples and at least 2 external documents (a PNG/photo, a native PDF).
- [ ] No secrets in the repo (`git log -p | grep -i "sk-or"` empty; check `.env.example`).
- [ ] `results/` includes the JSON of every iteration and `RESULTS.md`.
- [ ] Total key spend noted; enough credit left (> $2) for them to test.
- [ ] README in English, with URL, numbers and the 4 questions of step 5 answered.
- [ ] Delivery email: repo link, URL, one sentence about the model and the cost per document, and how much credit remains.

### 11.2 For the interview (30 min)

Keep at hand, in a local `NOTES.md` (not necessarily in the repo):

- The story in 3 minutes: baseline → what failed → iteration 1 → iteration 2 → model → deploy. With the numbers.
- Why the eval is designed this way and what it does not measure.
- Why the expiration status lives in code and not in the model.
- What you would do differently with more time / more budget.
- Which part the agent did, which part you reviewed, where it got it wrong and how you caught it (the eval). Show judgment, not just speed.
- Questions for them: real volume, most common document types, how they handle errors today, which model provider they use with a BAA.

---

## 12. API key budget ($5 USD)

Rules:

- The key is used **only** by the extractor (CLI, eval, app). Never by the coding agent.
- Development and debugging run on the own OpenAI key (`LLM_PROVIDER=openai`). The OpenRouter key is reserved for: official baseline, one final run per iteration, model comparison and deployment. The README documents the model and approximate cost of the development runs, as the brief requires.
- Every call requests `usage: {include: true}` and accumulates `usage.cost` in `results/cost_log.jsonl` (date, model, doc, tokens, cost). Real spend is confirmed in the OpenRouter dashboard.
- Development cap: **$2.00**. Reserve **$3.00** for the deployment and its tests (they will upload documents). If development approaches the cap, model comparison runs stop and it is documented.

Rough estimate (to be confirmed with real runs, not with remembered prices): a 1–3 page document at 150–200 dpi with a "flash" model costs on the order of thousandths of a dollar; a full run of 8 documents, cents. The plan allows for ~8 full runs (baseline ×2, iter1, iter2 ×2 for dpi, 3 models) plus loose deployment tests, which should stay well below $2. If a model turns out to be expensive per image, it is dropped before running all 8.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| The default model does not support `json_schema` | Fall back to `json_object` and robust parsing; document which mode each model used. |
| Rotation not detectable on images without a text layer | Document it; `pytesseract` option if available; the chosen model must tolerate rotation reasonably (test it). |
| Overfitting to the 8 samples | Generic rules in the prompt, no concrete issuers/names; test with 2+ external documents before delivering. |
| Variance between runs | Temperature 0, seed if available, repeat the baseline and the final run twice and report both. |
| Runaway spend in the deployment | Size/page limits, concurrency 1, cumulative spend cap, clear message. |
| Cold start / deployment down the day they test | HF Spaces instead of a free tier that sleeps; test the URL on delivery day; leave instructions to run locally as plan B. |
| PHI leaks in the demo | No file or result persistence; logs without content. |
| The brief PDF and the README differ | Follow the README; mention it in the interview if it comes up. |

---

## 14. Decision log

Format: date, decision, alternatives considered, reason. Filled in as work progresses; feeds the README and the interview.

| Date | Decision | Alternatives | Reason |
|------|----------|--------------|--------|
| 2026-11-03 | README as source of truth over the PDF | PDF | Newer; fixes the reference date and `null` for `expiration_status`; matches `expected/`. |
| 2026-11-03 | `expiration_status` computed in Python | Ask the model | Deterministic, testable, configurable; the model does not know the reference date. |
| 2026-11-03 | Render PDF to image instead of OpenRouter's PDF parser | `file` + engine pdf-text / mistral-ocr | The samples' OCR layer is noisy; control over rotation and dpi; model-independent. |
| 2026-11-03 | Configurable provider: own OpenAI key for development, OpenRouter for reported numbers and deployment | OpenRouter only | The brief allows it if documented; preserves the $5 for baseline, comparison and the reviewers' tests; same API format, minimal change in `client.py`. |
| 2026-11-03 | New repo (not a fork) with the 2 starter commits pushed as-is; repo-local git identity with GitHub noreply email | Fork | Own history that starts exactly like theirs. |
| 2026-11-03 | `PLAN.md` kept in the repo, in English | Local-only working file | Everything in the repo is in English; the plan shows the reasoning to the reviewers and is useful for the interview. |
| 2026-11-03 | `extract_baseline.py` as an untouched copy of the original script in the root | `baseline/extract.py`; `git checkout` of the old commit | Baseline reproducible at any time and visible diff against the new `extract.py`. |
| 2026-11-04 | Dates requested from the model "as printed", converted to ISO in code | Ask the model for ISO | Copying is more reliable than converting; the conversion is deterministic and unit-tested. Iteration 1: 68.8% → 95.3%. |
| 2026-11-04 | Page orientation fixed from the PDF text layer, per page | Ask the model for the rotation; leave pages sideways | `tx_01` has its two pages rotated in opposite directions; the text layer gives the answer for free. Iteration 2: 95.3% → 96.9%. |
| 2026-11-04 | Leave the New York `issuing_authority` misses unfixed (96.9%, not 100%) | A general rule for hierarchical issuers | With two such documents the rule cannot be measured; the brief warns against fitting the samples. Documented as the first next step. |
| 2026-11-04 | Deployed model: `deepseek/deepseek-v4.1-flash` | `openai/gpt-4.1-mini` (tie at 96.9%), `google/gemini-2.5-flash` (81.2%, false negative on `al_01`) | Same accuracy as GPT-4.1 mini at a third of the cost; matched a prompt iterated against another model. |
| 2026-11-04 | Streamlit Community Cloud instead of Hugging Face Spaces + Gradio | HF Spaces (plan's recommendation), Render | HF now requires a paid plan for Gradio/Docker Spaces on new accounts (only static Spaces are free). Streamlit is free, sleeps only after 12 h idle (Render: 15 min), and the brief names it. UI rewritten from Gradio to Streamlit; pipeline unchanged. |

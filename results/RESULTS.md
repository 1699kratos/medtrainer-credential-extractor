# Results

Reference date for `expiration_status`: `2026-11-01`, 60-day window (`expected/_reference.json`).
Eval: `python eval.py results/outputs/<run>/ --label <run>`. Full detail per run in `results/<run>.json`;
raw extractor outputs in `results/outputs/<run>/`.

## Summary

| Run | Script | Provider / model | Overall | Perfect docs | Cost / doc |
|-----|--------|------------------|---------|--------------|------------|
| `00_baseline` | `extract_baseline.py` (original prompt, page 1 at 100 dpi) | OpenAI / `gpt-4.1-mini` | **65.6%** | 0/8 | ~$0.001 (~1.5k tokens) |
| `03_pipeline` | `extract.py` on the new package (same prompt and 100 dpi, status computed in code, nulls enforced) | OpenAI / `gpt-4.1-mini` | **68.8%** | 1/8 | ~$0.001 |
| `01_prompt` | Iteration 1: per-field prompt rules + date/name normalization in code (same model, same 100 dpi image) | OpenAI / `gpt-4.1-mini` | **95.3%** | 5/8 | ~$0.001 (~2.1k tokens) |
| `02_input` | Iteration 2: pages rotated upright from the text layer, 150 dpi, up to 3 pages (same prompt, same model) | OpenAI / `gpt-4.1-mini` | **96.9%** | 6/8 | ~$0.002 (~5.2k tokens) |
| `04_deepseek` | Phase 6 model comparison: same pipeline as `02_input` | OpenRouter / `deepseek/deepseek-v4.1-flash` | **96.9%** | 6/8 | $0.0005 (measured) |
| `05_gemini` | Phase 6 model comparison: same pipeline as `02_input` | OpenRouter / `google/gemini-2.5-flash` | **81.2%** | 4/8 | $0.0005 (measured) |
| `06_gpt41mini_or` | Phase 6 model comparison: same pipeline as `02_input` | OpenRouter / `openai/gpt-4.1-mini` | **96.9%** | 6/8 | $0.0017 (measured) |
| `07_final` | Final configuration, everything from `.env` (no CLI overrides): the setup that is deployed | OpenRouter / `deepseek/deepseek-v4.1-flash` | **96.9%** | 6/8 | $0.0005 (measured) |
| `08_summary` | Bonus: `summary` field added to the prompt and schema; the 8 scored fields unchanged | OpenRouter / `deepseek/deepseek-v4.1-flash` | **96.9%** | 6/8 | $0.0006 (measured) |

## 00_baseline

Run on 2026-11-03 with the original script, only change: provider switch (`LLM_PROVIDER=openai`) so it runs on a personal OpenAI key during development. Prompt, 100 dpi first-page render and parsing are the original.

| Field | Accuracy |
|-------|----------|
| `is_credential` | 100.0% |
| `holder_name` | 37.5% |
| `credential_type` | 87.5% |
| `license_number` | 87.5% |
| `issuing_authority` | 62.5% |
| `issue_date` | 87.5% |
| `expiration_date` | 12.5% |
| `expiration_status` | 50.0% |

What failed (22 of 64 cells):

- **Dates not in ISO** (7 docs, 8 cells): returned as printed, e.g. `03/14/2012` instead of `2012-03-14`.
- **`expiration_status` guessed** (4 docs): `valid` on credentials that are expired (`tx_02`) or expiring soon (`ny_02`, `tx_03`). The model has no reference date; the status is left to the prompt instead of being computed in code.
- **Degree suffix kept in `holder_name`** (5 docs): `Tamsin Rae Holloway MD`, `Robert Alan Mitchell Jr, DO`. Casing also changed on the Texas documents (`Adriana Lucía Ferrer, MD` vs printed `ADRIANA LUCÍA FERRER`).
- **Non-credential not nulled** (`al_03`, 6 cells): `is_credential` is correctly `false`, but the model still fills name, number, issuer and dates, and invents `credential_type: "MD (Medical Doctor)"`.
- **`issuing_authority` too verbose on NY** (2 docs): `The State of New York Department of Professional Registration Office of Licensed Professions` vs expected `New York State Department of Professional Registration`.

What worked: `is_credential` 8/8, `license_number` and `credential_type` 7/8, including the rotated Texas documents. Reading is mostly right; the errors are formatting and logic.

## 03_pipeline (Phase 3: architecture, no prompt change)

Same prompt and 100 dpi first-page render as the baseline. Only the plumbing changed: `credential_extractor/` package (loader, client with retries and temperature 0, Pydantic schema, post-processing, pipeline), `expiration_status` computed in code against `--reference-date`, and all fields nulled when `is_credential` is false.

| Field | Accuracy |
|-------|----------|
| `is_credential` | 100.0% |
| `holder_name` | 50.0% |
| `credential_type` | 100.0% |
| `license_number` | 87.5% |
| `issuing_authority` | 75.0% |
| `issue_date` | 87.5% |
| `expiration_date` | 25.0% |
| `expiration_status` | 25.0% |

Changes vs baseline:

- `al_03` 2/8 → 8/8: the non-credential is now fully nulled by post-processing.
- `expiration_status` 50% → 25%: the model's guesses are gone; the status is `null` whenever the date is not ISO, which is still every date the original prompt returns. This resolves once dates are normalized (Phase 4).
- `tx_03.license_number` read as `R8150` instead of `Q8150` (correct in the baseline run): a 100 dpi, rotated page. Motivates the dpi and orientation work of Phase 5.
- Everything else fails as before: dates as printed, degree suffixes in names, verbose NY issuer.

A first version of the post-processing raised on non-ISO dates and failed 6 of 8 documents entirely (23.4%). The eval caught it before anything else changed; the rule now degrades to `null` for the status and keeps the other fields.

## 01_prompt (Phase 4, iteration 1: prompt and post-processing)

Same model and same 100 dpi first-page image as `03_pipeline`. Two changes:

- **Prompt** (`credential_extractor/prompt.py`): one rule per field. What counts as a credential (renewal notices, receipts, forms are not), nulls instead of guesses, names without degree suffixes, license number vs receipt/control numbers, issuer without addresses, and dates copied **as printed** rather than converted. The model no longer returns `expiration_status`. Document content is declared untrusted.
- **Post-processing** (`credential_extractor/postprocess.py`): `normalize_date` converts printed dates to ISO (`MM/DD/YYYY`, `MM/DD/YY` as `20YY`, `Month DD, YYYY`, `DD Month YYYY`, `DD-MON-YY`; impossible dates become `null`); `strip_degree_suffix` removes trailing `MD`, `RN`, `DDS`, etc. while keeping `Jr.`/`III`. Both run before the status is computed. Covered by `tests/test_postprocess.py` (32 cases, `python -m pytest -q`).

| Field | 03_pipeline | 01_prompt |
|-------|-------------|-----------|
| `is_credential` | 100.0% | 100.0% |
| `holder_name` | 50.0% | 87.5% |
| `credential_type` | 100.0% | 100.0% |
| `license_number` | 87.5% | 100.0% |
| `issuing_authority` | 75.0% | 75.0% |
| `issue_date` | 87.5% | 100.0% |
| `expiration_date` | 25.0% | 100.0% |
| `expiration_status` | 25.0% | 100.0% |

Overall 68.8% → **95.3%**, perfect documents 1/8 → 5/8.

A first version of the `credential_type` rule said "the short name, not the document title", and the model answered `MD` for `al_01` (expected `Certificate of Registration`), a field that was already 100%: 93.8% on that run. The rule now says "what the document certifies, or its title when that is all it states; never the holder's degree". Rerun: 95.3%.

Remaining failures (3 of 64 cells):

- **`tx_01.holder_name`**: `Adriana Lucia Ferrer` without the accent in `LUCÍA`. The previous run read the accent from the same image, so this is reading noise on a rotated 100 dpi page, not a prompt issue. Addressed in Phase 5 (dpi, orientation).
- **`ny_01` / `ny_02` `issuing_authority`**: the document prints `The State of New York / Department of Professional Registration / Office of Licensed Professions`; the expected value is the condensed `New York State Department of Professional Registration`. A prompt rule that produces exactly that would be fitted to these two documents, so it is left as a known miss rather than tuned.

## 02_input (Phase 5, iteration 2: model input)

Same prompt and model as `01_prompt`. Only what the model sees changed (`credential_extractor/loader.py`, defaults in `extract.py`):

- **Orientation**: each PDF page is rotated upright before rendering, using the majority writing direction of its text layer. The Texas documents are scanned sideways, and `tx_01` has its two pages rotated in opposite directions, so the fix is per page. Pages without a text layer, and PNG/JPG uploads, are sent as they are.
- **Resolution**: 100 → 150 dpi.
- **Pages**: first page only → up to 3 pages. The Texas documents have a second page (a pocket card with the same name, number and expiration).

| Field | 01_prompt | 02_input |
|-------|-----------|----------|
| `is_credential` | 100.0% | 100.0% |
| `holder_name` | 87.5% | 100.0% |
| `credential_type` | 100.0% | 100.0% |
| `license_number` | 100.0% | 100.0% |
| `issuing_authority` | 75.0% | 75.0% |
| `issue_date` | 100.0% | 100.0% |
| `expiration_date` | 100.0% | 100.0% |
| `expiration_status` | 100.0% | 100.0% |

Overall 95.3% → **96.9%**, perfect documents 5/8 → 6/8. `tx_01.holder_name` now reads the accent in `LUCÍA`. Input tokens per document went from ~2.1k to ~5.2k (larger image, second page on Texas), cost from ~$0.001 to ~$0.002 per document, latency unchanged (~2 s).

Remaining failures (2 of 64 cells): `ny_01` and `ny_02` `issuing_authority`, as described under `01_prompt`. Left as a known miss on purpose.

## Model comparison (Phase 6)

The pipeline of `02_input` (same prompt, 150 dpi, up to 3 pages, rotation fix) run through OpenRouter with three vision models. Cost is the value OpenRouter returns per request, not an estimate. Total spend for the phase: ~$0.02.

| Model | Overall | Perfect docs | Cost / doc | Avg latency | Input tokens / doc |
|-------|---------|--------------|------------|-------------|--------------------|
| `deepseek/deepseek-v4.1-flash` | **96.9%** | 6/8 | $0.0005 | 2.2 s | ~2.0k |
| `google/gemini-2.5-flash` | 81.2% | 4/8 | $0.0005 | 1.8 s | ~1.0k |
| `openai/gpt-4.1-mini` | **96.9%** | 6/8 | $0.0017 | 2.8 s | ~3.9k |

- **Gemini 2.5 Flash** is out. It answered `is_credential: false` for `al_01` (a noisy scan of an Alabama registration certificate) and nulled every field: a false negative on a valid credential, the most expensive error for credentialing. It also returned the document title (`REGISTRATION CERTIFICATE`) as `credential_type` on `ny_02`.
- **DeepSeek V4.1 Flash and GPT-4.1 mini tie** at 96.9% with the same two misses (`issuing_authority` on the New York documents).

**Chosen model: `deepseek/deepseek-v4.1-flash`.** Same accuracy as GPT-4.1 mini at a third of the cost and slightly lower latency. The prompt was iterated entirely against GPT-4.1 mini (OpenAI, development key); DeepSeek matching it without any adjustment suggests the field rules are not tuned to one model. It is also the default the base script shipped with.

Caveat: with 8 documents, a tie is not a strong statistical result. The comparison is enough to exclude Gemini and to justify the cost choice between the other two; the unseen documents MedTrainer runs will be the real test.

## 07_final (Phase 7: confirmation run)

Same pipeline, run with the deployed configuration taken entirely from `.env` (`LLM_PROVIDER=openrouter`, `OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash`, defaults of 150 dpi and up to 3 pages), no command-line overrides. Reproduces `04_deepseek`: **96.9%**, 6/8 perfect documents, $0.0005 per document, ~2.3 s average latency. The two remaining misses are the New York `issuing_authority` cells.

This is the number the README reports as the final result.

## 08_summary (bonus: free-text summary, scored with LLM-as-judge)

The brief's optional bonus. A `summary` field (one or two sentences for a credentialing reviewer: who, what credential, which authority, expiration as printed; for a non-credential, what the document is instead) was added to the prompt and the schema. It is not one of the 8 scored fields: `eval.py` ignores it, and the accuracy run with the new prompt is unchanged at 96.9%. Extraction cost per document rose from $0.0005 to $0.0006.

A summary has no single correct string, so `judge.py` scores it against the **expected fields** of each document (not the image) with a judge model different from the extractor. Three criteria, pass/fail per document, one reason each: `faithful` (nothing contradicts the expected fields), `complete` (holder, credential, expiration, or "not a credential"), `concise`. Results saved in `results/judge_<label>.json`.

| Judge run | Judge model | faithful | complete | concise | all three |
|-----------|-------------|----------|----------|---------|-----------|
| First rubric | `gpt-4.1-mini` | 62.5% | 87.5% | 0.0% | 0/8 |
| Fixed rubric, concise in code | `gpt-4.1-mini` | 87.5% | 87.5% | 100% | 7/8 |
| Same, stronger judge | `gpt-4.1` | 100% | 100% | 100% | 8/8 |

What the first run taught:

- **The judge drifted from the rubric.** "Concise: at most two sentences" became "longer than necessary"; it failed every document, including one-sentence summaries. Conciseness is now counted in code (sentences and words), and the judge only decides what needs judgment: faithful and complete.
- **The rubric had holes.** For the non-credential, every expected field is `null` by design, and the judge read the summary's details as contradictions. Same for an issuer written in full vs the condensed expected value, and for the summary reporting the "synthetic test document" footer printed on the samples. The rubric now says explicitly that another form of the same value, a printed remark, and details on a non-credential are not contradictions.
- **Judge quality depends on the judge model.** With the fixed rubric, `gpt-4.1-mini` still failed `al_03` although the summary says the document "is not a license"; `gpt-4.1` passed it. The judge cost 5× more ($0.013 vs $0.003 for 8 documents), which is nothing for an eval that runs rarely, so `gpt-4.1` is the default.

An LLM judge is itself a model that needs evaluating. The three runs above are that evaluation on this set. For a larger suite (more criteria, score history, CI gates) the same judging would move to a framework such as DeepEval (`GEval` with the same criteria) or promptfoo, rather than a hand-written script; the criteria and the lessons stay.

## Future improvements (not done, on purpose)

- **Hierarchical issuers.** The two remaining misses are `issuing_authority` on the New York documents, which print the issuer as a three-line hierarchy (state / department / office) while the expected value is the condensed "state + department". A general rule ("when the issuer is a hierarchy, return the department or board prefixed by its state; drop 'The State of…' headers and sub-offices") would likely fix it and is not specific to New York, but with only two such documents there is no way to measure whether it generalizes or what it breaks elsewhere. It was left out to keep the 96.9% explainable rather than chase 100% on the samples. First thing to try with a larger labeled set.
- **Structured outputs.** `response_format` with the Pydantic JSON schema would make malformed answers impossible instead of caught. Not needed on the samples (0 parse failures across all runs), worth adding once the chosen model's support on OpenRouter is confirmed.
- **Image uploads without a text layer.** The rotation fix reads the PDF text layer; a sideways PNG/JPG is sent as-is. An orientation pass on the pixels (or asking the model for the rotation first) would cover that case.

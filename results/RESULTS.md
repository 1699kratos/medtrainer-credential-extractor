# Results

Reference date for `expiration_status`: `2026-11-01`, 60-day window (`expected/_reference.json`).
Eval: `python eval.py results/outputs/<run>/ --label <run>`. Full detail per run in `results/<run>.json`;
raw extractor outputs in `results/outputs/<run>/`.

## Summary

| Run | Script | Provider / model | Overall | Perfect docs | Cost / doc |
|-----|--------|------------------|---------|--------------|------------|
| `00_baseline` | `extract_baseline.py` (original prompt, page 1 at 100 dpi) | OpenAI / `gpt-4.1-mini` | **65.6%** | 0/8 | ~$0.001 (~1.5k tokens) |

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

# Credential Extractor

AI system that extracts structured data from medical licenses and certifications, flags expirations, and says clearly when a document is not a credential.

Built for the MedTrainer AI Engineer technical challenge. The original brief is in [CHALLENGE.md](CHALLENGE.md).

## Quick start

Requires Python 3.13.

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
```

Load the environment and run the extractor on one document or a folder:

```bash
set -a; source .env; set +a

python extract.py docs/tx_01.pdf
python extract.py docs/ --out-dir outputs/
```

## Configuration

All settings come from environment variables (see [.env.example](.env.example)):

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `openrouter` (default, used by the deployment) or `openai` (local development) |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Key and model for OpenRouter |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional key and model for development runs |
| `REFERENCE_DATE` | Date used to compute `expiration_status` (`YYYY-MM-DD`). Defaults to today |
| `EXPIRING_WINDOW_DAYS` | Window for `expiring_soon`. Defaults to 60 |

## Status

Work in progress. Eval, results, model choice, cost and deployment notes will be added as the work progresses.

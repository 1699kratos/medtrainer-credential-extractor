"""Baseline credential extractor.

Sends a license or certification document (PDF or image) to a vision model on
OpenRouter and prints the extracted fields as JSON.

This is a deliberately simple starting point. It is expected to score around
60% field accuracy on the sample documents.

Usage:
    python extract.py docs/tx_01.pdf
    python extract.py docs/ --out-dir outputs/
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import pymupdf
import requests

# Provider is selected with LLM_PROVIDER (default: openrouter). Only the
# endpoint, key and default model change; prompt and logic are the original.
PROVIDERS = {
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "default_model": "deepseek/deepseek-v4.1-flash",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4.1-mini",
    },
}
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

PROMPT = """Extract the following information from this medical license document
and return it as JSON:

- is_credential
- holder_name
- credential_type
- license_number
- issuing_authority
- issue_date
- expiration_date
- expiration_status (expired, expiring_soon, valid or no_expiration)
"""


def load_image(path: Path) -> tuple[str, str]:
    """Return (mime_type, base64_data) for the document. PDFs use the first page only."""
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as pdf:
            pixmap = pdf[0].get_pixmap(dpi=100)
            return "image/png", base64.b64encode(pixmap.tobytes("png")).decode()

    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else f"image/{path.suffix.lower()[1:]}"
    return mime, base64.b64encode(path.read_bytes()).decode()


def resolve_provider() -> dict:
    name = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if name not in PROVIDERS:
        sys.exit(f"LLM_PROVIDER must be one of {list(PROVIDERS)}, got {name!r}")
    return PROVIDERS[name]


def call_model(mime: str, image_b64: str, model: str) -> str:
    provider = resolve_provider()
    api_key = os.environ.get(provider["key_env"])
    if not api_key:
        sys.exit(f"{provider['key_env']} is not set")

    response = requests.post(
        provider["url"],
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ],
                }
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def extract(path: Path, model: str) -> dict:
    mime, image_b64 = load_image(path)
    raw = call_model(mime, image_b64, model)
    try:
        return parse_json(raw)
    except json.JSONDecodeError:
        return {"error": "invalid JSON from model", "raw": raw}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract credential fields from a document.")
    parser.add_argument("path", type=Path, help="A document or a folder of documents")
    parser.add_argument("--out-dir", type=Path, help="Write one <document>.json per input here")
    provider = resolve_provider()
    parser.add_argument("--model", default=os.environ.get(provider["model_env"]) or provider["default_model"])
    args = parser.parse_args()

    if args.path.is_dir():
        files = sorted(p for p in args.path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    else:
        files = [args.path]

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        result = extract(file, args.model)
        output = json.dumps(result, indent=2, ensure_ascii=False)
        if args.out_dir:
            (args.out_dir / f"{file.stem}.json").write_text(output + "\n")
            print(f"{file.name} -> {args.out_dir / (file.stem + '.json')}")
        else:
            print(f"# {file.name}\n{output}")


if __name__ == "__main__":
    main()

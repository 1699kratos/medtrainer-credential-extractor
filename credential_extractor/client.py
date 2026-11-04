"""Chat-completions client with a provider switch (OpenRouter or OpenAI).

Both providers share the OpenAI chat/completions format. LLM_PROVIDER selects
endpoint, key and default model; everything else is identical.
"""

from __future__ import annotations

import os
import time

import requests

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

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 120


class ProviderError(RuntimeError):
    """Configuration or API error that should surface to the caller."""


def resolve_provider() -> dict:
    name = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if name not in PROVIDERS:
        raise ProviderError(f"LLM_PROVIDER must be one of {list(PROVIDERS)}, got {name!r}")
    return {"name": name, **PROVIDERS[name]}


def default_model() -> str:
    provider = resolve_provider()
    return os.environ.get(provider["model_env"]) or provider["default_model"]


def chat(system: str, user: str, images: list[tuple[str, str]], model: str | None = None) -> dict:
    """Send one request with a system prompt, a user text and N images.

    Returns {"text": str, "meta": {...}} where meta has provider, model, tokens,
    cost (when the provider reports it; OpenRouter does, OpenAI does not),
    latency and the number of attempts.
    """
    provider = resolve_provider()
    api_key = os.environ.get(provider["key_env"])
    if not api_key:
        raise ProviderError(f"{provider['key_env']} is not set")
    model = model or default_model()

    content = [{"type": "text", "text": user}]
    for mime, b64 in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    if provider["name"] == "openrouter":
        payload["usage"] = {"include": True}  # ask OpenRouter for the real cost of the call

    started = time.monotonic()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                provider["url"],
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                raise ProviderError(f"request failed after {attempt} attempts: {exc}") from exc
            time.sleep(2 ** attempt)
            continue

        if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
            continue
        if not response.ok:
            raise ProviderError(f"{provider['name']} returned {response.status_code}: {response.text[:300]}")
        break

    body = response.json()
    usage = body.get("usage") or {}
    return {
        "text": body["choices"][0]["message"]["content"],
        "meta": {
            "provider": provider["name"],
            "model": body.get("model", model),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cost_usd": usage.get("cost"),
            "latency_s": round(time.monotonic() - started, 2),
            "attempts": attempt,
        },
    }

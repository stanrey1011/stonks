"""
OpenAI-compatible LLM client.

Works with any OpenAI-compatible server: llama.cpp's `llama-server`, Ollama's
`/v1` endpoint, vLLM, etc. This replaces the old direct dependency on Ollama's
native API (`/api/chat`, `/api/tags`) and the `ollama` Python package.

Configuration (env):
  LLM_BASE_URL  Full OpenAI-style base URL incl. /v1
                (e.g. http://10.11.87.91:8089/v1 for llama-server).
                If unset, derived from the legacy OLLAMA_HOST/OLLAMA_URL by
                appending "/v1" — so existing deployments keep working against
                Ollama's OpenAI-compatible endpoint until explicitly flipped.
  LLM_API_KEY   Bearer token. Local servers don't check it; default is a dummy.
  LLM_MODEL     Default model id when a caller doesn't specify one.
"""
import os
import json
import logging

import requests

logger = logging.getLogger(__name__)


def base_url() -> str:
    explicit = os.getenv("LLM_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    legacy = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL") or "http://localhost:11434"
    return legacy.rstrip("/") + "/v1"


def api_key() -> str:
    return os.getenv("LLM_API_KEY", "sk-no-key-required")


def default_model() -> str:
    return os.getenv("LLM_MODEL") or "qwen2.5:7b"


def _headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def list_models() -> list[str]:
    """Return available model ids from GET /v1/models (empty list on error)."""
    try:
        r = requests.get(f"{base_url()}/models", headers=_headers(), timeout=5)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except Exception:
        return []


def chat(messages: list[dict], model: str | None = None,
         json_mode: bool = False, timeout: int = 300) -> str:
    """Non-streaming chat completion. Returns the assistant message content."""
    payload = {
        "model": model or default_model(),
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(f"{base_url()}/chat/completions", headers=_headers(),
                      json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def chat_stream(messages: list[dict], model: str | None = None, timeout: int = 300):
    """Streaming chat completion. Yields content deltas (str)."""
    payload = {
        "model": model or default_model(),
        "messages": messages,
        "stream": True,
    }
    with requests.post(f"{base_url()}/chat/completions", headers=_headers(),
                       json=payload, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta", {})
            content = delta.get("content")
            if content:
                yield content

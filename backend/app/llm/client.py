import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

import httpx
import truststore

from app import db
from app.config import settings

# Use the OS certificate store so networks that re-sign TLS traffic still work.
truststore.inject_into_ssl()

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    providers: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "cached": self.cached,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "providers": sorted(self.providers),
        }


async def _groq(messages: list[dict], temperature: float, usage: Usage) -> str:
    for attempt in range(7):
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json={"model": settings.groq_model, "messages": messages, "temperature": temperature},
                )
        except httpx.TransportError as e:  # DNS hiccups, resets, timeouts: retry before falling back
            if attempt == 6:
                raise
            log.info("groq network error (%s), retrying", e)
            await asyncio.sleep(min(30, 3 * (attempt + 1)))
            continue
        if r.status_code == 429 and attempt < 6:
            # Free-tier limits are per minute: waiting beats degrading to the small local model.
            m = re.search(r"try again in ([\d.]+)s", r.text)
            wait = min(float(m.group(1)) + 1 if m else 15, 60)
            log.info("groq rate limited, waiting %.0fs", wait)
            await asyncio.sleep(wait)
            continue
        if r.status_code >= 500 and attempt < 6:
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise LLMError(f"groq {r.status_code}: {r.text[:300]}")
        data = r.json()
        u = data.get("usage") or {}
        usage.prompt_tokens += u.get("prompt_tokens", 0)
        usage.completion_tokens += u.get("completion_tokens", 0)
        return data["choices"][0]["message"]["content"] or ""
    raise LLMError("groq: retries exhausted")


async def _ollama(messages: list[dict], temperature: float, usage: Usage) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.ollama_chat_model, "messages": messages, "stream": False, "options": {"temperature": temperature}},
        )
    if r.status_code != 200:
        raise LLMError(f"ollama {r.status_code}: {r.text[:300]}")
    data = r.json()
    usage.prompt_tokens += data.get("prompt_eval_count", 0)
    usage.completion_tokens += data.get("eval_count", 0)
    return data["message"]["content"]


def _key(messages: list[dict], temperature: float, variant: int) -> str:
    raw = json.dumps([settings.groq_model, temperature, variant, messages], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


async def chat(messages: list[dict], usage: Usage | None = None, temperature: float = 0.2, variant: int = 0) -> str:
    """Groq first, Ollama as fallback. Identical requests are answered from the cache; `variant` distinguishes
    deliberate retries of the same prompt."""
    usage = usage or Usage()
    key = _key(messages, temperature + 0.1 * variant if variant else temperature, variant)
    if settings.llm_cache:
        hit = await asyncio.to_thread(db.cache_get, key)
        if hit is not None:
            usage.cached += 1
            usage.providers.add("cache")
            return hit
    usage.calls += 1
    text = None
    if settings.groq_api_key:
        try:
            text = await _groq(messages, min(1.0, temperature + 0.1 * variant), usage)
            usage.providers.add("groq")
        except (LLMError, httpx.HTTPError) as e:
            log.warning("groq failed, falling back to ollama: %s", e)
    if text is None:
        try:
            text = await _ollama(messages, temperature, usage)
            usage.providers.add("ollama")
        except httpx.HTTPError as e:
            raise LLMError(f"no LLM available: {e}") from e
    if settings.llm_cache and text.strip():
        await asyncio.to_thread(db.cache_put, key, text)
    return text

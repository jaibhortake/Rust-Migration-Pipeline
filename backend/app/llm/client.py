import asyncio
import logging
import re

import httpx
import truststore

from app.config import settings

# Use the OS certificate store so networks that re-sign TLS traffic still work.
truststore.inject_into_ssl()

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


async def _groq(messages: list[dict], temperature: float) -> str:
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={"model": settings.groq_model, "messages": messages, "temperature": temperature},
            )
        if r.status_code == 429 and attempt < 2:
            # Free-tier limits are per minute: waiting beats degrading to the small local model.
            m = re.search(r"try again in ([\d.]+)s", r.text)
            wait = min(float(m.group(1)) + 1 if m else 15, 60)
            log.info("groq rate limited, waiting %.0fs", wait)
            await asyncio.sleep(wait)
            continue
        if r.status_code != 200:
            raise LLMError(f"groq {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]
    raise LLMError("groq: retries exhausted")


async def _ollama(messages: list[dict], temperature: float) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
    if r.status_code != 200:
        raise LLMError(f"ollama {r.status_code}: {r.text[:300]}")
    return r.json()["message"]["content"]


async def chat(messages: list[dict], temperature: float = 0.2) -> tuple[str, str]:
    """Returns (text, provider). Tries Groq first, falls back to Ollama."""
    if settings.groq_api_key:
        try:
            return await _groq(messages, temperature), "groq"
        except (LLMError, httpx.HTTPError) as e:
            log.warning("groq failed, falling back to ollama: %s", e)
    try:
        return await _ollama(messages, temperature), "ollama"
    except httpx.HTTPError as e:
        raise LLMError(f"no LLM available: {e}") from e

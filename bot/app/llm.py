"""Один интерфейс, два протокола. Меняешь провайдера — код не трогаешь."""
from __future__ import annotations

import asyncio
import logging

from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)

Message = dict[str, Any]


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.9,
        retries: int = 2,
    ) -> str:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                if settings.llm_provider == "anthropic":
                    return await self._anthropic(system, messages, temperature)
                return await self._openai(system, messages, temperature)
            except (httpx.HTTPError, LLMError) as exc:
                last = exc
                log.warning("LLM попытка %s не удалась: %s", attempt + 1, exc)
                await asyncio.sleep(1.5 * (attempt + 1))
        raise LLMError(str(last))

    async def _anthropic(self, system: str, messages: list[Message], temp: float) -> str:
        # temp намеренно не передаём: новые модели Anthropic его не принимают
        r = await self._client.post(
            (settings.llm_base_url or "https://api.anthropic.com") + "/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": settings.llm_max_tokens,
                "system": system,
                "messages": messages,
            },
        )
        if r.status_code >= 400:
            raise LLMError(f"{r.status_code}: {r.text[:300]}")
        blocks = r.json().get("content", [])
        return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()

    async def _openai(self, system: str, messages: list[Message], temp: float) -> str:
        base = settings.llm_base_url or "https://api.openai.com/v1"
        r = await self._client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "max_tokens": settings.llm_max_tokens,
                "temperature": temp,
                "messages": [{"role": "system", "content": system}, *messages],
            },
        )
        if r.status_code >= 400:
            raise LLMError(f"{r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"].strip()


llm = LLM()

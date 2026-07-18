"""
OpenAI-compatible LLM provider.

Speaks to anything with an /v1/chat/completions endpoint: Groq's free tier
(Llama 3.3 70B) for Phase 0, or a self-hosted vLLM later. Which one is a base
URL, not a code change.

Groq's free tier is rate-limited; at scale you self-host or pay. Where that line
falls is open decision #4 in ARCHITECTURE.md §12.
"""

from __future__ import annotations

import json

import httpx
import structlog

from providers.base import Capabilities, License, ProviderError

logger = structlog.get_logger()


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        license: License = License.LLAMA,
        timeout_s: float = 120.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._license = license
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout_s, headers=headers)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=f"llm:{self._model}",
            license=self._license,
            requires_gpu=False,  # remote endpoint
        )

    async def generate(self, system: str, user: str, temperature: float = 0.7) -> str:
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"LLM request failed: {e}") from e

        return response.json()["choices"][0]["message"]["content"]

    async def generate_json(self, system: str, user: str, temperature: float = 0.3) -> dict:
        raw = await self.generate(
            system + "\n\nRespond ONLY with valid JSON. No markdown, no prose.",
            user,
            temperature,
        )

        try:
            return json.loads(_strip_fences(raw))
        except json.JSONDecodeError as e:
            # Surface what came back. A silent fallback here is how a broken
            # script reaches the video model and wastes GPU minutes.
            raise ProviderError(
                f"LLM returned invalid JSON: {e}. First 200 chars: {raw[:200]!r}"
            ) from e

    async def close(self) -> None:
        await self._client.aclose()


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()

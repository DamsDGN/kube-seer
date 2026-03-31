import httpx
import structlog

from src.intelligence.providers.base import BaseLLMProvider

logger = structlog.get_logger()


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible provider. Works with Ollama, OpenAI, Mistral, vLLM, LM Studio."""

    def __init__(self, api_url: str, api_key: str, model: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        headers: dict = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self._api_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"LLM request failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )

        data = resp.json()
        return data["choices"][0]["message"]["content"]

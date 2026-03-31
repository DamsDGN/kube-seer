import anthropic
import structlog

from src.intelligence.providers.base import BaseLLMProvider

logger = structlog.get_logger()

MAX_TOKENS = 1024


class AnthropicProvider(BaseLLMProvider):
    """Claude provider via the official Anthropic SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        message = await client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestOpenAIProvider:
    def _make(self, api_url="http://localhost:11434", api_key="", model="llama3.2"):
        from src.intelligence.providers.openai import OpenAIProvider

        return OpenAIProvider(api_url=api_url, api_key=api_key, model=model)

    @pytest.mark.asyncio
    async def test_complete_returns_content(self):
        provider = self._make()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"summary": "all good"}'}}]
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await provider.complete("system prompt", "user prompt")
        assert result == '{"summary": "all good"}'

    @pytest.mark.asyncio
    async def test_complete_raises_on_non_200(self):
        provider = self._make()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            with pytest.raises(RuntimeError, match="LLM request failed"):
                await provider.complete("system", "user")

    @pytest.mark.asyncio
    async def test_uses_bearer_auth_when_api_key_set(self):
        provider = self._make(api_key="sk-test")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            await provider.complete("system", "user")
            call_kwargs = mock_client.post.call_args
            headers = call_kwargs.kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer sk-test"

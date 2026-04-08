import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import Config
from src.models import Anomaly, AnalysisResult, LLMInsight, Severity


def _make_config(**kwargs):
    defaults = dict(
        elasticsearch_url="http://localhost:9200",
        intelligence_enabled=True,
        intelligence_provider="ollama",
        intelligence_api_url="http://localhost:11434",
        intelligence_model="llama3.2",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def _make_anomaly(aid, sev=Severity.WARNING, resource_name="my-pod"):
    return Anomaly(
        anomaly_id=aid,
        source="events",
        severity=sev,
        resource_type="pod",
        resource_name=resource_name,
        namespace="default",
        description="something bad",
        score=0.8,
        details={},
        timestamp=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )


def _make_result(anomalies=None):
    return AnalysisResult(
        anomalies=anomalies or [],
        analysis_timestamp=datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc),
        metrics_analyzed=5,
        events_analyzed=3,
    )


class TestShouldCallLLM:
    def _service(self):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config()
        storage = AsyncMock()
        storage.query = AsyncMock(return_value=[])
        return IntelligenceService(cfg, storage)

    @pytest.mark.asyncio
    async def test_skip_when_no_anomalies(self):
        svc = self._service()
        assert await svc._should_call_llm(_make_result(anomalies=[])) is False

    @pytest.mark.asyncio
    async def test_call_when_new_anomalies(self):
        svc = self._service()
        result = _make_result(anomalies=[_make_anomaly("a1")])
        assert await svc._should_call_llm(result) is True

    @pytest.mark.asyncio
    async def test_skip_when_same_fingerprint(self):
        svc = self._service()
        # Same resource/severity across two cycles (different UUIDs, same content)
        result1 = _make_result(anomalies=[_make_anomaly("a1")])
        result2 = _make_result(
            anomalies=[_make_anomaly("a2")]
        )  # new UUID, same content
        await svc._should_call_llm(result1)  # first call — sets state
        assert await svc._should_call_llm(result2) is False  # same fingerprint → skip

    @pytest.mark.asyncio
    async def test_call_when_anomalies_change(self):
        svc = self._service()
        await svc._should_call_llm(
            _make_result(anomalies=[_make_anomaly("a1", resource_name="pod-a")])
        )
        result2 = _make_result(anomalies=[_make_anomaly("a2", resource_name="pod-b")])
        assert await svc._should_call_llm(result2) is True


_VALID_RESPONSE = (
    '{"summary":"ok","root_causes":[],"recommendations":[],'
    '"severity_assessment":"ok","affected_namespaces":[]}'
)


class TestIntelligenceServiceRun:
    def _service(
        self,
        provider_response=_VALID_RESPONSE,
    ):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config()
        storage = AsyncMock()
        svc = IntelligenceService(cfg, storage)
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=provider_response)
        svc._provider = mock_provider
        return svc, storage

    @pytest.mark.asyncio
    async def test_run_returns_insight(self):
        svc, _ = self._service()
        result = _make_result(anomalies=[_make_anomaly("a1")])
        insight = await svc.run(result)
        assert isinstance(insight, LLMInsight)
        assert insight.summary == "ok"

    @pytest.mark.asyncio
    async def test_run_stores_insight(self):
        svc, storage = self._service()
        result = _make_result(anomalies=[_make_anomaly("a1")])
        await svc.run(result)
        storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_skips_when_no_anomalies(self):
        svc, storage = self._service()
        insight = await svc.run(_make_result(anomalies=[]))
        assert insight is None
        storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_stores_raw_on_invalid_json(self):
        svc, _ = self._service(provider_response="not valid json")
        result = _make_result(anomalies=[_make_anomaly("a1")])
        insight = await svc.run(result)
        assert insight is not None
        assert insight.summary == ""
        assert insight.raw_response == "not valid json"

    @pytest.mark.asyncio
    async def test_run_returns_none_when_llm_raises(self):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config()
        storage = AsyncMock()
        svc = IntelligenceService(cfg, storage)
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("timeout"))
        svc._provider = mock_provider
        result = _make_result(anomalies=[_make_anomaly("a1")])
        insight = await svc.run(result)
        assert insight is None

    @pytest.mark.asyncio
    async def test_last_insight_updated_after_run(self):
        svc, _ = self._service()
        result = _make_result(anomalies=[_make_anomaly("a1")])
        assert svc._last_insight is None
        await svc.run(result)
        assert svc._last_insight is not None

    @pytest.mark.asyncio
    async def test_disabled_service_returns_none(self):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config(intelligence_enabled=False)
        storage = AsyncMock()
        svc = IntelligenceService(cfg, storage)
        result = _make_result(anomalies=[_make_anomaly("a1")])
        insight = await svc.run(result)
        assert insight is None


class TestIntelligenceServiceSlack:
    @pytest.mark.asyncio
    async def test_slack_not_called_when_no_webhook(self):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config(alerter_slack_webhook_url="")
        storage = AsyncMock()
        svc = IntelligenceService(cfg, storage)
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=_VALID_RESPONSE)
        svc._provider = mock_provider
        with patch("httpx.AsyncClient") as mock_cls:
            result = _make_result(anomalies=[_make_anomaly("a1")])
            await svc.run(result)
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_slack_called_when_webhook_set(self):
        from src.intelligence.service import IntelligenceService

        cfg = _make_config(alerter_slack_webhook_url="https://hooks.slack.com/test")
        storage = AsyncMock()
        svc = IntelligenceService(cfg, storage)
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=_VALID_RESPONSE)
        svc._provider = mock_provider

        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client
            result = _make_result(anomalies=[_make_anomaly("a1")])
            await svc.run(result)
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args.args[0] == "https://hooks.slack.com/test"

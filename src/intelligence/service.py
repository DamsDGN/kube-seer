import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from src.config import Config
from src.intelligence.prompt import (
    SYSTEM_PROMPT,
    build_prompt,
    format_slack_message,
    parse_llm_response,
)
from src.intelligence.providers.base import BaseLLMProvider
from src.models import AnalysisResult, LLMInsight, StoredRecord

logger = structlog.get_logger()

_VALID_SEVERITIES = {"ok", "warning", "critical"}


def _coerce_str_list(items: list) -> list:
    """Ensure each item in a list is a plain string (LLMs sometimes return dicts)."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(next(iter(item.values()), str(item)))
        else:
            result.append(str(item))
    return result


def _normalize_severity(raw: str) -> str:
    """Return the severity value if valid, else pick the highest found, else 'warning'."""
    val = raw.lower().strip()
    if val in _VALID_SEVERITIES:
        return val
    for sev in ("critical", "warning", "ok"):
        if sev in val:
            return sev
    return "warning"


def _dated_index(base: str) -> str:
    return f"{base}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


class IntelligenceService:
    def __init__(self, config: Config, storage) -> None:
        self._config = config
        self._storage = storage
        self._provider: Optional[BaseLLMProvider] = None
        self._last_fingerprint: Optional[str] = None
        self._last_insight: Optional[LLMInsight] = None

        if config.intelligence_enabled and config.intelligence_provider:
            self._provider = self._build_provider()

    def _build_provider(self) -> Optional[BaseLLMProvider]:
        name = self._config.intelligence_provider.lower()
        if name in ("ollama", "openai"):
            from src.intelligence.providers.openai import OpenAIProvider

            api_url = self._config.intelligence_api_url or "https://api.openai.com"
            return OpenAIProvider(
                api_url=api_url,
                api_key=self._config.intelligence_api_key,
                model=self._config.intelligence_model,
                timeout=float(self._config.intelligence_timeout_seconds),
            )
        if name == "anthropic":
            from src.intelligence.providers.anthropic import AnthropicProvider

            return AnthropicProvider(
                api_key=self._config.intelligence_api_key,
                model=self._config.intelligence_model,
            )
        logger.warning(
            "intelligence_service.unknown_provider",
            provider=self._config.intelligence_provider,
        )
        return None

    def _compute_fingerprint(self, result: AnalysisResult) -> str:
        key = frozenset(
            (a.source, a.resource_type, a.resource_name, a.namespace, a.severity)
            for a in result.anomalies
        )
        return hashlib.md5(str(sorted(key)).encode()).hexdigest()

    async def _load_last_fingerprint(self) -> None:
        """Restore the last fingerprint from ES so dedup survives pod restarts."""
        try:
            results = await self._storage.query(
                index=f"{self._config.elasticsearch_indices_insights}-*",
                query_body={
                    "bool": {"must": [{"term": {"record_type.keyword": "llm_insight"}}]}
                },
                size=1,
            )
            if results:
                self._last_fingerprint = results[0].get("data", {}).get("fingerprint")
        except Exception:
            pass

    async def _should_call_llm(self, result: AnalysisResult) -> bool:
        if not result.anomalies:
            return False
        if self._last_fingerprint is None:
            await self._load_last_fingerprint()
        fingerprint = self._compute_fingerprint(result)
        if fingerprint == self._last_fingerprint:
            return False
        self._last_fingerprint = fingerprint
        return True

    async def run(self, result: AnalysisResult) -> Optional[LLMInsight]:
        if not self._provider:
            return None
        if not await self._should_call_llm(result):
            return None

        try:
            raw = await self._provider.complete(SYSTEM_PROMPT, build_prompt(result))
        except Exception as e:
            logger.error("intelligence_service.llm_error", error=str(e))
            return None

        parsed = parse_llm_response(raw)
        insight = LLMInsight(
            insight_id=str(uuid.uuid4()),
            cycle_timestamp=result.analysis_timestamp,
            anomaly_count=len(result.anomalies),
            summary=parsed.get("summary", ""),
            root_causes=_coerce_str_list(parsed.get("root_causes", [])),
            recommendations=parsed.get("recommendations", []),
            severity_assessment=_normalize_severity(
                parsed.get("severity_assessment", "")
            ),
            affected_namespaces=parsed.get("affected_namespaces", []),
            raw_response=raw,
            provider=f"{self._config.intelligence_provider}/{self._config.intelligence_model}",
            fingerprint=self._last_fingerprint,
        )

        self._last_insight = insight
        await self._store(insight)
        await self._notify_slack(insight)
        return insight

    async def _store(self, insight: LLMInsight) -> None:
        record = StoredRecord(
            record_type="llm_insight",
            data=insight.model_dump(mode="json"),
            timestamp=insight.cycle_timestamp,
        )
        index = _dated_index(self._config.elasticsearch_indices_insights)
        try:
            await self._storage.store(index, record)
        except Exception as e:
            logger.warning("intelligence_service.store_error", error=str(e))

    async def _notify_slack(self, insight: LLMInsight) -> None:
        webhook_url = self._config.alerter_slack_webhook_url
        if not webhook_url:
            return
        text = format_slack_message(insight)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json={"text": text})
                if resp.status_code != 200:
                    logger.warning(
                        "intelligence_service.slack_error", status=resp.status_code
                    )
        except Exception as e:
            logger.warning("intelligence_service.slack_error", error=str(e))

import hashlib
import time
from typing import Dict, List, Optional

import structlog

from src.alerter.alertmanager import AlertmanagerClient
from src.alerter.webhook import WebhookAlerter
from src.config import Config
from src.models import Anomaly, AnalysisResult, Severity

logger = structlog.get_logger()

DEDUP_COOLDOWN_SECONDS = 300


class AlerterService:
    def __init__(self, config: Config):
        self._config = config
        self._alertmanager: Optional[AlertmanagerClient] = None
        self._webhook: Optional[WebhookAlerter] = None
        self._dedup_cache: Dict[str, float] = {}
        self._stats = {
            "total_sent": 0,
            "alertmanager_sent": 0,
            "webhook_sent": 0,
            "deduped": 0,
            "skipped_info": 0,
        }
        if config.alerter_alertmanager_enabled:
            self._alertmanager = AlertmanagerClient(config)
        if config.alerter_fallback_webhook_enabled:
            self._webhook = WebhookAlerter(config)

    async def connect(self) -> None:
        if self._alertmanager:
            await self._alertmanager.connect()
        if self._webhook:
            await self._webhook.connect()

    async def close(self) -> None:
        if self._alertmanager:
            await self._alertmanager.close()
        if self._webhook:
            await self._webhook.close()

    async def send_alerts(self, result: AnalysisResult) -> None:
        alertable = self._filter_alertable(result.anomalies)
        if not alertable:
            return
        new_anomalies = self._deduplicate(alertable)
        if not new_anomalies:
            return
        sent = await self._dispatch(new_anomalies)
        self._stats["total_sent"] += sent

    def get_stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def _filter_alertable(self, anomalies: List[Anomaly]) -> List[Anomaly]:
        alertable = []
        for a in anomalies:
            if a.severity == Severity.INFO:
                self._stats["skipped_info"] += 1
                continue
            alertable.append(a)
        return alertable

    def _dedup_key(self, anomaly: Anomaly) -> str:
        raw = (
            f"{anomaly.source}:{anomaly.resource_type}:"
            f"{anomaly.resource_name}:{anomaly.namespace}:"
            f"{anomaly.severity}"
        )
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def _deduplicate(self, anomalies: List[Anomaly]) -> List[Anomaly]:
        now = time.monotonic()
        new = []
        for a in anomalies:
            key = self._dedup_key(a)
            last_sent = self._dedup_cache.get(key)
            if last_sent and (now - last_sent) < DEDUP_COOLDOWN_SECONDS:
                self._stats["deduped"] += 1
                continue
            self._dedup_cache[key] = now
            new.append(a)
        self._cleanup_cache(now)
        return new

    def _cleanup_cache(self, now: float) -> None:
        expired = [
            k
            for k, v in self._dedup_cache.items()
            if (now - v) > DEDUP_COOLDOWN_SECONDS * 2
        ]
        for k in expired:
            del self._dedup_cache[k]

    async def _dispatch(self, anomalies: List[Anomaly]) -> int:
        if self._alertmanager:
            healthy = await self._alertmanager.is_healthy()
            if healthy:
                sent = await self._alertmanager.send(anomalies)
                if sent > 0:
                    self._stats["alertmanager_sent"] += sent
                    return sent
                logger.warning("alerter.alertmanager_send_failed")
        if self._webhook:
            sent = await self._webhook.send(anomalies)
            if sent > 0:
                self._stats["webhook_sent"] += sent
                logger.info("alerter.webhook_fallback_used", count=sent)
                return sent
        logger.warning("alerter.no_channel_available")
        return 0

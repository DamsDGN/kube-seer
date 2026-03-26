from typing import Any, Dict, List, Optional

import httpx
import structlog

from src.alerter.base import BaseAlerter
from src.config import Config
from src.models import Anomaly

logger = structlog.get_logger()


class WebhookAlerter(BaseAlerter):
    def __init__(self, config: Config):
        self._config = config
        self._url = config.alerter_fallback_webhook_url
        self._http: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        if self._url:
            self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def send(self, anomalies: List[Anomaly]) -> int:
        if not anomalies or not self._url:
            return 0
        if not self._http:
            return 0
        payload = self._format_payload(anomalies)
        try:
            resp = await self._http.post(self._url, json=payload)
            if resp.status_code == 200:
                logger.info("webhook.sent", count=len(anomalies))
                return len(anomalies)
            logger.warning("webhook.send_failed", status=resp.status_code)
            return 0
        except Exception as e:
            logger.error("webhook.send_error", error=str(e))
            return 0

    async def is_healthy(self) -> bool:
        return bool(self._url and self._http)

    def _format_payload(self, anomalies: List[Anomaly]) -> Dict[str, Any]:
        return {
            "agent": "efk-sre-agent",
            "anomalies": [a.model_dump() for a in anomalies],
            "count": len(anomalies),
        }

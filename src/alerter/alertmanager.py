from typing import Any, Dict, List, Optional

import httpx
import structlog

from src.alerter.base import BaseAlerter
from src.config import Config
from src.models import Anomaly, Severity

logger = structlog.get_logger()

SEVERITY_MAP = {
    Severity.INFO: "info",
    Severity.WARNING: "warning",
    Severity.CRITICAL: "critical",
}


class AlertmanagerClient(BaseAlerter):
    def __init__(self, config: Config):
        self._config = config
        self._base_url = config.alerter_alertmanager_url
        self._http: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def send(self, anomalies: List[Anomaly]) -> int:
        if not anomalies:
            return 0
        if not self._http:
            return 0
        alerts = self._format_alerts(anomalies)
        try:
            resp = await self._http.post("/api/v2/alerts", json=alerts)
            if resp.status_code == 200:
                logger.info("alertmanager.sent", count=len(alerts))
                return len(alerts)
            logger.warning("alertmanager.send_failed", status=resp.status_code)
            return 0
        except Exception as e:
            logger.error("alertmanager.send_error", error=str(e))
            return 0

    async def is_healthy(self) -> bool:
        if not self._http:
            return False
        try:
            resp = await self._http.get("/-/healthy")
            return resp.status_code == 200
        except Exception:
            return False

    def _format_alerts(self, anomalies: List[Anomaly]) -> List[Dict[str, Any]]:
        alerts = []
        for a in anomalies:
            labels: Dict[str, str] = {
                "alertname": f"sre_{a.source}_{a.resource_type}",
                "agent": "efk-sre-agent",
                "severity": SEVERITY_MAP.get(a.severity, "warning"),
                "source": a.source,
                "resource_type": a.resource_type,
                "resource_name": a.resource_name,
            }
            if a.namespace:
                labels["namespace"] = a.namespace
            alerts.append(
                {
                    "labels": labels,
                    "annotations": {
                        "description": a.description,
                        "anomaly_id": a.anomaly_id,
                        "score": str(a.score),
                    },
                    "startsAt": a.timestamp.isoformat(),
                }
            )
        return alerts

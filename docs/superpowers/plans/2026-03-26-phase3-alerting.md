# Phase 3 — Alerting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add alerting to the SRE agent — push anomalies to Alertmanager (primary) with webhook fallback, including severity mapping, deduplication, and rate-limiting.

**Architecture:** An `AlerterService` orchestrates alert dispatch. It tries Alertmanager first (Prometheus alert format via `/api/v2/alerts`); if unavailable or disabled, falls back to a generic webhook (POST JSON). Deduplication uses a hash of (source + resource_type + resource_name + namespace + severity) with a configurable cooldown. The agent calls the alerter after storing anomalies.

**Tech Stack:** httpx (async HTTP), FastAPI (existing API)

---

## File Structure

```
src/
├── alerter/
│   ├── __init__.py
│   ├── base.py              # BaseAlerter interface
│   ├── alertmanager.py      # Alertmanager /api/v2/alerts push
│   ├── webhook.py           # Generic webhook POST fallback
│   └── service.py           # AlerterService: orchestration, dedup, routing
├── agent.py                 # Add: alert step in cycle
└── api/
    └── routes.py            # Add: /alerts/stats endpoint

tests/
├── alerter/
│   ├── __init__.py
│   ├── test_alertmanager.py
│   ├── test_webhook.py
│   └── test_service.py
├── test_agent.py            # Add: alert cycle tests
└── test_api.py              # Add: alert stats tests
```

---

## Task 1: Alerter base interface

**Files:**
- Create: `src/alerter/__init__.py`
- Create: `src/alerter/base.py`
- Create: `tests/alerter/__init__.py`

- [ ] **Step 1: Create package files**

`src/alerter/__init__.py`: empty file
`tests/alerter/__init__.py`: empty file

- [ ] **Step 2: Write the base interface**

`src/alerter/base.py`:
```python
from abc import ABC, abstractmethod
from typing import List

from src.models import Anomaly


class BaseAlerter(ABC):
    @abstractmethod
    async def send(self, anomalies: List[Anomaly]) -> int:
        """Send alerts for anomalies. Returns count of successfully sent alerts."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the alerting backend is reachable."""
```

- [ ] **Step 3: Commit**

```bash
git add src/alerter/ tests/alerter/__init__.py
git commit -m "feat: add alerter base interface"
```

---

## Task 2: Alertmanager client

**Files:**
- Create: `tests/alerter/test_alertmanager.py`
- Create: `src/alerter/alertmanager.py`

- [ ] **Step 1: Write the failing tests**

`tests/alerter/test_alertmanager.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.alerter.alertmanager import AlertmanagerClient
from src.config import Config
from src.models import Anomaly, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_alertmanager_url="http://alertmanager:9093",
    )


@pytest.fixture
def client(config):
    return AlertmanagerClient(config)


@pytest.fixture
def critical_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-001",
        source="metrics",
        severity=Severity.CRITICAL,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="CPU usage critical: 92.0%",
        score=0.92,
        details={"cpu_usage_percent": 92.0},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def warning_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-002",
        source="events",
        severity=Severity.WARNING,
        resource_type="pod",
        resource_name="web-abc",
        namespace="default",
        description="FailedScheduling: 0/3 nodes available",
        score=0.7,
        details={},
        timestamp=sample_timestamp,
    )


class TestAlertmanagerFormat:
    def test_format_alert_critical(self, client, critical_anomaly):
        alerts = client._format_alerts([critical_anomaly])
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["labels"]["severity"] == "critical"
        assert alert["labels"]["agent"] == "efk-sre-agent"
        assert alert["labels"]["resource_type"] == "node"
        assert alert["labels"]["resource_name"] == "node-1"
        assert "CPU usage critical" in alert["annotations"]["description"]

    def test_format_alert_warning(self, client, warning_anomaly):
        alerts = client._format_alerts([warning_anomaly])
        assert alerts[0]["labels"]["severity"] == "warning"
        assert alerts[0]["labels"]["namespace"] == "default"

    def test_format_alert_includes_source(self, client, critical_anomaly):
        alerts = client._format_alerts([critical_anomaly])
        assert alerts[0]["labels"]["source"] == "metrics"


class TestAlertmanagerSend:
    @pytest.mark.asyncio
    async def test_send_success(self, client, critical_anomaly):
        client._http = AsyncMock()
        client._http.post = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        count = await client.send([critical_anomaly])
        assert count == 1
        client._http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_empty_list(self, client):
        count = await client.send([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_failure_returns_zero(self, client, critical_anomaly):
        client._http = AsyncMock()
        client._http.post = AsyncMock(
            return_value=MagicMock(status_code=500)
        )
        count = await client.send([critical_anomaly])
        assert count == 0


class TestAlertmanagerHealth:
    @pytest.mark.asyncio
    async def test_healthy(self, client):
        client._http = AsyncMock()
        client._http.get = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        assert await client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_no_client(self, client):
        assert await client.is_healthy() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/alerter/test_alertmanager.py -v`

- [ ] **Step 3: Write the implementation**

`src/alerter/alertmanager.py`:
```python
from datetime import datetime, timezone
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
        self._http = httpx.AsyncClient(
            base_url=self._base_url, timeout=10.0
        )

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
                logger.info(
                    "alertmanager.sent",
                    count=len(alerts),
                )
                return len(alerts)
            logger.warning(
                "alertmanager.send_failed",
                status=resp.status_code,
            )
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
            alerts.append({
                "labels": labels,
                "annotations": {
                    "description": a.description,
                    "anomaly_id": a.anomaly_id,
                    "score": str(a.score),
                },
                "startsAt": a.timestamp.isoformat(),
            })
        return alerts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/alerter/test_alertmanager.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/alerter/alertmanager.py tests/alerter/test_alertmanager.py
git commit -m "feat: add Alertmanager client"
```

---

## Task 3: Webhook fallback client

**Files:**
- Create: `tests/alerter/test_webhook.py`
- Create: `src/alerter/webhook.py`

- [ ] **Step 1: Write the failing tests**

`tests/alerter/test_webhook.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.alerter.webhook import WebhookAlerter
from src.config import Config
from src.models import Anomaly, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_fallback_webhook_url="http://hooks.example.com/alert",
    )


@pytest.fixture
def alerter(config):
    return WebhookAlerter(config)


@pytest.fixture
def anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-001",
        source="metrics",
        severity=Severity.CRITICAL,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="CPU critical",
        score=0.92,
        details={"cpu": 92.0},
        timestamp=sample_timestamp,
    )


class TestWebhookSend:
    @pytest.mark.asyncio
    async def test_send_success(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        count = await alerter.send([anomaly])
        assert count == 1

    @pytest.mark.asyncio
    async def test_send_posts_json(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        await alerter.send([anomaly])
        call_args = alerter._http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "anomalies" in payload
        assert len(payload["anomalies"]) == 1
        assert payload["anomalies"][0]["anomaly_id"] == "a-001"

    @pytest.mark.asyncio
    async def test_send_empty(self, alerter):
        count = await alerter.send([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_failure(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(
            return_value=MagicMock(status_code=500)
        )
        count = await alerter.send([anomaly])
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_url_configured(self):
        config = Config(
            elasticsearch_url="http://localhost:9200",
            alerter_fallback_webhook_url="",
        )
        alerter = WebhookAlerter(config)
        count = await alerter.send([MagicMock()])
        assert count == 0


class TestWebhookHealth:
    @pytest.mark.asyncio
    async def test_healthy_with_url(self, alerter):
        alerter._http = AsyncMock()
        assert await alerter.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_no_url(self):
        config = Config(
            elasticsearch_url="http://localhost:9200",
            alerter_fallback_webhook_url="",
        )
        alerter = WebhookAlerter(config)
        assert await alerter.is_healthy() is False
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write the implementation**

`src/alerter/webhook.py`:
```python
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
            logger.warning(
                "webhook.send_failed", status=resp.status_code
            )
            return 0
        except Exception as e:
            logger.error("webhook.send_error", error=str(e))
            return 0

    async def is_healthy(self) -> bool:
        return bool(self._url and self._http)

    def _format_payload(
        self, anomalies: List[Anomaly]
    ) -> Dict[str, Any]:
        return {
            "agent": "efk-sre-agent",
            "anomalies": [a.model_dump() for a in anomalies],
            "count": len(anomalies),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/alerter/test_webhook.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/alerter/webhook.py tests/alerter/test_webhook.py
git commit -m "feat: add webhook fallback alerter"
```

---

## Task 4: AlerterService (orchestration, dedup, routing)

**Files:**
- Create: `tests/alerter/test_service.py`
- Create: `src/alerter/service.py`

- [ ] **Step 1: Write the failing tests**

`tests/alerter/test_service.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.alerter.service import AlerterService
from src.config import Config
from src.models import Anomaly, AnalysisResult, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_alertmanager_enabled=True,
        alerter_alertmanager_url="http://alertmanager:9093",
        alerter_fallback_webhook_enabled=True,
        alerter_fallback_webhook_url="http://hooks.example.com/alert",
    )


@pytest.fixture
def service(config):
    svc = AlerterService(config)
    svc._alertmanager = AsyncMock()
    svc._webhook = AsyncMock()
    return svc


@pytest.fixture
def anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-001",
        source="metrics",
        severity=Severity.CRITICAL,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="CPU critical",
        score=0.92,
        details={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def info_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-003",
        source="metrics",
        severity=Severity.INFO,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="Low usage",
        score=0.1,
        details={},
        timestamp=sample_timestamp,
    )


class TestAlerterServiceRouting:
    @pytest.mark.asyncio
    async def test_sends_to_alertmanager_primary(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=anomaly.timestamp,
        )
        await service.send_alerts(result)
        service._alertmanager.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_webhook(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=False)
        service._webhook.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=anomaly.timestamp,
        )
        await service.send_alerts(result)
        service._webhook.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_alerts_on_empty_anomalies(self, service):
        result = AnalysisResult(
            anomalies=[],
            analysis_timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        await service.send_alerts(result)
        service._alertmanager.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_info_severity(self, service, info_anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=0)
        result = AnalysisResult(
            anomalies=[info_anomaly],
            analysis_timestamp=info_anomaly.timestamp,
        )
        await service.send_alerts(result)
        service._alertmanager.send.assert_not_awaited()


class TestAlerterServiceDedup:
    @pytest.mark.asyncio
    async def test_deduplicates_same_anomaly(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=anomaly.timestamp,
        )
        await service.send_alerts(result)
        await service.send_alerts(result)
        assert service._alertmanager.send.await_count == 1

    @pytest.mark.asyncio
    async def test_different_anomalies_not_deduped(self, service, sample_timestamp):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.CRITICAL,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU critical",
            score=0.9,
            details={},
            timestamp=sample_timestamp,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-2",
            namespace="",
            description="Memory warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)

        r1 = AnalysisResult(anomalies=[a1], analysis_timestamp=sample_timestamp)
        r2 = AnalysisResult(anomalies=[a2], analysis_timestamp=sample_timestamp)
        await service.send_alerts(r1)
        await service.send_alerts(r2)
        assert service._alertmanager.send.await_count == 2


class TestAlerterServiceStats:
    @pytest.mark.asyncio
    async def test_stats_tracking(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=anomaly.timestamp,
        )
        await service.send_alerts(result)
        stats = service.get_stats()
        assert stats["total_sent"] >= 1
        assert stats["alertmanager_sent"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write the implementation**

`src/alerter/service.py`:
```python
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
        return hashlib.md5(raw.encode()).hexdigest()

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
            k for k, v in self._dedup_cache.items()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/alerter/test_service.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/alerter/service.py tests/alerter/test_service.py
git commit -m "feat: add AlerterService with dedup, routing, and fallback"
```

---

## Task 5: Integrate alerter into agent cycle

**Files:**
- Modify: `src/agent.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agent.py`:
```python
class TestSREAgentAlerts:
    @pytest.mark.asyncio
    async def test_run_cycle_sends_alerts(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.analyze = AsyncMock(
            return_value=AnalysisResult(
                anomalies=[],
                analysis_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()
        agent.store_anomalies = AsyncMock()
        agent.update_models = AsyncMock()
        agent._alerter = AsyncMock()
        agent._alerter.send_alerts = AsyncMock()

        await agent.run_cycle()
        agent._alerter.send_alerts.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Modify `src/agent.py`**

Read the current file first, then:

Add import at top:
```python
from src.alerter.service import AlerterService
```

In `__init__`, after `self._last_analysis`, add:
```python
        self._alerter = AlerterService(config)
```

In `initialize()`, after connecting K8s API, add:
```python
        await self._alerter.connect()
```

In `stop()`, before `logger.info("agent.stopped")`, add:
```python
        await self._alerter.close()
```

Update `run_cycle()` to:
```python
    async def run_cycle(self) -> None:
        logger.info("agent.cycle_start")
        data = await self.collect()
        await self.store(data)
        result = await self.analyze(data)
        await self.store_anomalies(result)
        await self._alerter.send_alerts(result)
        await self.update_models(data)
        logger.info("agent.cycle_end")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: integrate alerter into agent cycle"
```

---

## Task 6: Alert stats API endpoint

**Files:**
- Modify: `src/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:
```python
class TestAlertStatsEndpoint:
    @pytest.mark.asyncio
    async def test_alert_stats(self, client, mock_agent):
        mock_agent._alerter = MagicMock()
        mock_agent._alerter.get_stats.return_value = {
            "total_sent": 5,
            "alertmanager_sent": 3,
            "webhook_sent": 2,
            "deduped": 1,
            "skipped_info": 0,
        }
        resp = await client.get("/alerts/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sent"] == 5
        assert data["alertmanager_sent"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add endpoint to `src/api/routes.py`**

Add inside `create_app()`, before `return app`:
```python
    @app.get("/alerts/stats")
    async def alert_stats():
        if hasattr(agent, "_alerter") and agent._alerter:
            return agent._alerter.get_stats()
        return {"total_sent": 0, "alertmanager_sent": 0, "webhook_sent": 0, "deduped": 0, "skipped_info": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat: add /alerts/stats API endpoint"
```

---

## Task 7: Full test suite + linting

**Files:**
- Potentially any file

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 2: Run linting**

Run: `python -m flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503`

- [ ] **Step 3: Run type checking**

Run: `python -m mypy src/ --ignore-missing-imports`

- [ ] **Step 4: Fix any issues**

- [ ] **Step 5: Commit fixes if any**

```bash
git add -A
git commit -m "fix: resolve linting and type issues for Phase 3"
```

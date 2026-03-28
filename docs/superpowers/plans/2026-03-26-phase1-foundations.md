# Phase 1 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild kube-seer with a modular architecture, implementing collectors (Prometheus, metrics-server, K8s API), Elasticsearch storage, Helm chart, and base API endpoints.

**Architecture:** Each module exposes a base interface in `base.py`. The orchestrator (`agent.py`) wires modules together. Collectors gather data from Prometheus, metrics-server, and the Kubernetes API. Storage writes/reads Elasticsearch. The API exposes health, readiness, status, and config endpoints via FastAPI.

**Tech Stack:** Python 3.13, FastAPI, elasticsearch-py 8.x, kubernetes-client, prometheus-api-client, structlog, pytest, Helm 3.x

---

## File Structure

```
src/
├── collector/
│   ├── __init__.py
│   ├── base.py              # Abstract BaseCollector interface
│   ├── prometheus.py         # PromQL-based metrics collector
│   ├── k8s_api.py           # K8s events, states, resource inventory
│   └── metrics_server.py    # Realtime CPU/mem via metrics API
│
├── storage/
│   ├── __init__.py
│   ├── base.py              # Abstract BaseStorage interface
│   └── elasticsearch.py     # ES read/write implementation
│
├── api/
│   ├── __init__.py
│   └── routes.py            # FastAPI endpoints
│
├── config.py                # Pydantic-based configuration
├── models.py                # Pydantic data models
├── agent.py                 # Orchestrator (collection cycles)
└── main.py                  # Entrypoint

tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_config.py
├── test_models.py
├── collector/
│   ├── __init__.py
│   ├── test_prometheus.py
│   ├── test_k8s_api.py
│   └── test_metrics_server.py
├── storage/
│   ├── __init__.py
│   └── test_elasticsearch.py
├── test_agent.py
└── test_api.py

helm/kube-seer/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── serviceaccount.yaml
│   ├── clusterrole.yaml
│   ├── clusterrolebinding.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── servicemonitor.yaml
│   └── pdb.yaml
```

---

## Task 1: Project scaffolding and dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `src/collector/__init__.py`
- Create: `src/storage/__init__.py`
- Create: `src/api/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/collector/__init__.py`
- Create: `tests/storage/__init__.py`

- [ ] **Step 1: Update requirements.txt**

Replace the current `requirements.txt` with the dependencies needed for the redesign:

```txt
# Core
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

# Elasticsearch
elasticsearch>=8.0.0

# Kubernetes
kubernetes>=25.0.0

# Prometheus
prometheus-api-client>=0.5.0
prometheus-client>=0.15.0

# HTTP
aiohttp>=3.8.0
httpx>=0.25.0

# ML (used in later phases, keep for compatibility)
scikit-learn>=1.2.0
pandas>=1.5.0
numpy>=1.24.0

# Logging
structlog>=22.0.0

# Utils
pyyaml>=6.0
python-dotenv>=0.19.0

# Testing
pytest>=7.0.0
pytest-asyncio>=0.20.0
pytest-cov>=4.0.0
```

- [ ] **Step 2: Create package directories**

Create empty `__init__.py` files for all packages:

`src/collector/__init__.py`:
```python
```

`src/storage/__init__.py`:
```python
```

`src/api/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

`tests/collector/__init__.py`:
```python
```

`tests/storage/__init__.py`:
```python
```

- [ ] **Step 3: Create shared test fixtures**

`tests/conftest.py`:
```python
import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_timestamp():
    return datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
```

- [ ] **Step 4: Install dependencies**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && pip install -r requirements.txt`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/collector/__init__.py src/storage/__init__.py src/api/__init__.py tests/__init__.py tests/conftest.py tests/collector/__init__.py tests/storage/__init__.py
git commit -m "chore: scaffold modular architecture and update dependencies"
```

---

## Task 2: Configuration module (Pydantic)

**Files:**
- Create: `tests/test_config.py`
- Rewrite: `src/config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import pytest
from src.config import Config


class TestConfigDefaults:
    def test_default_values(self):
        config = Config(elasticsearch_url="http://localhost:9200")
        assert config.elasticsearch_url == "http://localhost:9200"
        assert config.elasticsearch_username == ""
        assert config.elasticsearch_password == ""
        assert config.elasticsearch_indices_metrics == "sre-metrics"
        assert config.elasticsearch_indices_logs == "sre-logs"
        assert config.elasticsearch_indices_anomalies == "sre-anomalies"
        assert config.agent_analysis_interval == 300
        assert config.agent_log_level == "INFO"
        assert config.collectors_prometheus_enabled is True
        assert config.collectors_prometheus_url == "http://prometheus-server:9090"
        assert config.collectors_metrics_server_enabled is True
        assert config.collectors_k8s_api_enabled is True
        assert config.collectors_k8s_api_watch_events is True
        assert config.thresholds_cpu_warning == 70.0
        assert config.thresholds_cpu_critical == 85.0
        assert config.thresholds_memory_warning == 70.0
        assert config.thresholds_memory_critical == 85.0
        assert config.thresholds_disk_warning == 80.0
        assert config.thresholds_disk_critical == 90.0
        assert config.ml_retrain_interval == 3600
        assert config.ml_window_size == 100
        assert config.ml_anomaly_threshold == 0.05
        assert config.intelligence_enabled is False
        assert config.intelligence_provider == ""
        assert config.intelligence_api_url == ""
        assert config.intelligence_api_key == ""
        assert config.intelligence_model == ""
        assert config.alerter_alertmanager_enabled is True
        assert config.alerter_alertmanager_url == "http://alertmanager:9093"
        assert config.alerter_fallback_webhook_enabled is False
        assert config.alerter_fallback_webhook_url == ""


class TestConfigValidation:
    def test_elasticsearch_url_required(self):
        with pytest.raises(ValueError):
            Config(elasticsearch_url="")

    def test_analysis_interval_minimum(self):
        with pytest.raises(ValueError):
            Config(elasticsearch_url="http://localhost:9200", agent_analysis_interval=30)

    def test_anomaly_threshold_range(self):
        with pytest.raises(ValueError):
            Config(elasticsearch_url="http://localhost:9200", ml_anomaly_threshold=1.5)

    def test_threshold_ordering_cpu(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_cpu_warning=90.0,
                thresholds_cpu_critical=80.0,
            )

    def test_threshold_ordering_memory(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_memory_warning=90.0,
                thresholds_memory_critical=80.0,
            )

    def test_threshold_ordering_disk(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_disk_warning=95.0,
                thresholds_disk_critical=90.0,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_config.py -v`
Expected: FAIL — `src.config` module does not have the new Config class yet.

- [ ] **Step 3: Write the implementation**

`src/config.py`:
```python
from pydantic import BaseModel, model_validator


class Config(BaseModel):
    # Elasticsearch
    elasticsearch_url: str
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""
    elasticsearch_secret_ref: str = ""
    elasticsearch_indices_metrics: str = "sre-metrics"
    elasticsearch_indices_logs: str = "sre-logs"
    elasticsearch_indices_anomalies: str = "sre-anomalies"

    # Agent
    agent_analysis_interval: int = 300
    agent_log_level: str = "INFO"

    # Collectors
    collectors_prometheus_enabled: bool = True
    collectors_prometheus_url: str = "http://prometheus-server:9090"
    collectors_metrics_server_enabled: bool = True
    collectors_k8s_api_enabled: bool = True
    collectors_k8s_api_watch_events: bool = True

    # Thresholds
    thresholds_cpu_warning: float = 70.0
    thresholds_cpu_critical: float = 85.0
    thresholds_memory_warning: float = 70.0
    thresholds_memory_critical: float = 85.0
    thresholds_disk_warning: float = 80.0
    thresholds_disk_critical: float = 90.0

    # ML
    ml_retrain_interval: int = 3600
    ml_window_size: int = 100
    ml_anomaly_threshold: float = 0.05

    # Intelligence (optional LLM)
    intelligence_enabled: bool = False
    intelligence_provider: str = ""
    intelligence_api_url: str = ""
    intelligence_api_key: str = ""
    intelligence_api_key_secret_ref: str = ""
    intelligence_model: str = ""

    # Alerter
    alerter_alertmanager_enabled: bool = True
    alerter_alertmanager_url: str = "http://alertmanager:9093"
    alerter_fallback_webhook_enabled: bool = False
    alerter_fallback_webhook_url: str = ""

    @model_validator(mode="after")
    def validate_config(self) -> "Config":
        if not self.elasticsearch_url:
            raise ValueError("elasticsearch_url is required")
        if self.agent_analysis_interval < 60:
            raise ValueError("agent_analysis_interval must be >= 60 seconds")
        if not (0 < self.ml_anomaly_threshold < 1):
            raise ValueError("ml_anomaly_threshold must be between 0 and 1")
        if self.thresholds_cpu_warning >= self.thresholds_cpu_critical:
            raise ValueError("cpu warning threshold must be less than critical")
        if self.thresholds_memory_warning >= self.thresholds_memory_critical:
            raise ValueError("memory warning threshold must be less than critical")
        if self.thresholds_disk_warning >= self.thresholds_disk_critical:
            raise ValueError("disk warning threshold must be less than critical")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_config.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: rewrite config module with Pydantic validation"
```

---

## Task 3: Data models (Pydantic)

**Files:**
- Create: `tests/test_models.py`
- Rewrite: `src/models.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py`:
```python
import pytest
from datetime import datetime, timezone
from src.models import (
    Severity,
    NodeMetrics,
    PodMetrics,
    KubernetesEvent,
    ResourceState,
    CollectedData,
    StoredRecord,
)


class TestSeverity:
    def test_ordering(self):
        assert Severity.INFO < Severity.WARNING < Severity.CRITICAL


class TestNodeMetrics:
    def test_creation(self, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.2,
            memory_usage_percent=62.1,
            disk_usage_percent=30.0,
            network_rx_bytes=1000000,
            network_tx_bytes=500000,
            conditions={"Ready": True, "DiskPressure": False},
            timestamp=sample_timestamp,
        )
        assert node.node_name == "node-1"
        assert node.cpu_usage_percent == 45.2
        assert node.conditions["Ready"] is True

    def test_to_dict(self, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.2,
            memory_usage_percent=62.1,
            disk_usage_percent=30.0,
            network_rx_bytes=1000000,
            network_tx_bytes=500000,
            conditions={},
            timestamp=sample_timestamp,
        )
        d = node.model_dump()
        assert d["node_name"] == "node-1"
        assert "timestamp" in d


class TestPodMetrics:
    def test_creation(self, sample_timestamp):
        pod = PodMetrics(
            pod_name="web-abc123",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,
            restart_count=0,
            status="Running",
            timestamp=sample_timestamp,
        )
        assert pod.pod_name == "web-abc123"
        assert pod.cpu_usage_millicores == 250
        assert pod.restart_count == 0


class TestKubernetesEvent:
    def test_creation(self, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="OOMKilled",
            message="Container killed due to OOM",
            involved_object_kind="Pod",
            involved_object_name="web-abc123",
            involved_object_namespace="default",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        assert event.event_type == "Warning"
        assert event.reason == "OOMKilled"


class TestResourceState:
    def test_creation(self, sample_timestamp):
        state = ResourceState(
            kind="Deployment",
            name="web",
            namespace="default",
            desired_replicas=3,
            ready_replicas=3,
            conditions={"Available": True},
            timestamp=sample_timestamp,
        )
        assert state.kind == "Deployment"
        assert state.desired_replicas == 3


class TestCollectedData:
    def test_creation(self, sample_timestamp):
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        assert data.node_metrics == []
        assert data.collection_timestamp == sample_timestamp


class TestStoredRecord:
    def test_creation(self, sample_timestamp):
        record = StoredRecord(
            record_type="node_metrics",
            data={"node_name": "node-1", "cpu": 45.2},
            timestamp=sample_timestamp,
            cluster_name="prod-01",
        )
        assert record.record_type == "node_metrics"
        assert record.cluster_name == "prod-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_models.py -v`
Expected: FAIL — imports don't resolve.

- [ ] **Step 3: Write the implementation**

`src/models.py`:
```python
from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    CRITICAL = 2


class NodeMetrics(BaseModel):
    node_name: str
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_rx_bytes: int
    network_tx_bytes: int
    conditions: Dict[str, bool]
    timestamp: datetime


class PodMetrics(BaseModel):
    pod_name: str
    namespace: str
    node_name: str
    cpu_usage_millicores: int
    memory_usage_bytes: int
    restart_count: int
    status: str
    timestamp: datetime


class KubernetesEvent(BaseModel):
    event_type: str
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    involved_object_namespace: str
    count: int
    first_timestamp: datetime
    last_timestamp: datetime


class ResourceState(BaseModel):
    kind: str
    name: str
    namespace: str
    desired_replicas: Optional[int] = None
    ready_replicas: Optional[int] = None
    conditions: Dict[str, Any] = {}
    timestamp: datetime


class CollectedData(BaseModel):
    node_metrics: List[NodeMetrics]
    pod_metrics: List[PodMetrics]
    events: List[KubernetesEvent]
    resource_states: List[ResourceState]
    collection_timestamp: datetime


class StoredRecord(BaseModel):
    record_type: str
    data: Dict[str, Any]
    timestamp: datetime
    cluster_name: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_models.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: rewrite data models with Pydantic"
```

---

## Task 4: Collector base interface

**Files:**
- Create: `src/collector/base.py`

- [ ] **Step 1: Write the base interface**

`src/collector/base.py`:
```python
from abc import ABC, abstractmethod
from typing import List

from src.models import (
    CollectedData,
    KubernetesEvent,
    NodeMetrics,
    PodMetrics,
    ResourceState,
)


class BaseCollector(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection to the data source."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the data source is reachable."""


class MetricsCollector(BaseCollector):
    @abstractmethod
    async def collect_node_metrics(self) -> List[NodeMetrics]:
        """Collect metrics for all nodes."""

    @abstractmethod
    async def collect_pod_metrics(
        self, namespace: str = ""
    ) -> List[PodMetrics]:
        """Collect metrics for pods. If namespace is empty, collect from all namespaces."""


class StateCollector(BaseCollector):
    @abstractmethod
    async def collect_events(
        self, namespace: str = ""
    ) -> List[KubernetesEvent]:
        """Collect Kubernetes events."""

    @abstractmethod
    async def collect_resource_states(
        self, namespace: str = ""
    ) -> List[ResourceState]:
        """Collect state of deployments, statefulsets, daemonsets, jobs, etc."""
```

- [ ] **Step 2: Commit**

```bash
git add src/collector/base.py
git commit -m "feat: add collector base interfaces"
```

---

## Task 5: Prometheus collector

**Files:**
- Create: `tests/collector/test_prometheus.py`
- Create: `src/collector/prometheus.py`

- [ ] **Step 1: Write the failing tests**

`tests/collector/test_prometheus.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.collector.prometheus import PrometheusCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        collectors_prometheus_url="http://prometheus:9090",
    )


@pytest.fixture
def collector(config):
    return PrometheusCollector(config)


class TestPrometheusCollectorConnect:
    @pytest.mark.asyncio
    async def test_connect_sets_connected(self, collector):
        with patch("src.collector.prometheus.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client_cls.return_value = mock_client
            await collector.connect()
            assert collector._client is not None


class TestPrometheusCollectorHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, collector):
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        assert await collector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false_no_client(self, collector):
        assert await collector.is_healthy() is False


class TestPrometheusCollectorNodeMetrics:
    @pytest.mark.asyncio
    async def test_collect_node_metrics(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance": "node-1"}, "value": [1700000000, "45.2"]},
                ]
            },
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        nodes = await collector.collect_node_metrics()
        assert len(nodes) >= 1
        assert nodes[0].node_name == "node-1"

    @pytest.mark.asyncio
    async def test_collect_node_metrics_empty(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        nodes = await collector.collect_node_metrics()
        assert nodes == []


class TestPrometheusCollectorPodMetrics:
    @pytest.mark.asyncio
    async def test_collect_pod_metrics(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {
                            "pod": "web-abc123",
                            "namespace": "default",
                            "node": "node-1",
                        },
                        "value": [1700000000, "250"],
                    },
                ]
            },
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        pods = await collector.collect_pod_metrics()
        assert len(pods) >= 1
        assert pods[0].pod_name == "web-abc123"

    @pytest.mark.asyncio
    async def test_collect_pod_metrics_filtered_namespace(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        pods = await collector.collect_pod_metrics(namespace="kube-system")
        assert pods == []
        call_args = collector._client.get.call_args
        assert "kube-system" in str(call_args)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_prometheus.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/collector/prometheus.py`:
```python
import structlog
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.collector.base import MetricsCollector
from src.config import Config
from src.models import NodeMetrics, PodMetrics

logger = structlog.get_logger()

# PromQL queries
NODE_CPU_QUERY = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
NODE_MEMORY_QUERY = "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
NODE_DISK_QUERY = '(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100'
NODE_NETWORK_RX_QUERY = "rate(node_network_receive_bytes_total[5m])"
NODE_NETWORK_TX_QUERY = "rate(node_network_transmit_bytes_total[5m])"

POD_CPU_QUERY = "sum by (pod, namespace, node) (rate(container_cpu_usage_seconds_total[5m])) * 1000"
POD_MEMORY_QUERY = "sum by (pod, namespace, node) (container_memory_working_set_bytes)"
POD_RESTART_QUERY = "sum by (pod, namespace) (kube_pod_container_status_restarts_total)"
POD_STATUS_QUERY = "kube_pod_status_phase"


class PrometheusCollector(MetricsCollector):
    def __init__(self, config: Config):
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = config.collectors_prometheus_url

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        logger.info("prometheus_collector.connected", url=self._base_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get("/-/healthy")
            return resp.status_code == 200
        except Exception:
            return False

    async def _query(self, promql: str) -> List[Dict]:
        if not self._client:
            return []
        try:
            resp = await self._client.get(
                "/api/v1/query", params={"query": promql}
            )
            if resp.status_code != 200:
                logger.warning("prometheus_collector.query_failed", query=promql, status=resp.status_code)
                return []
            data = resp.json()
            if data.get("status") != "success":
                return []
            return data.get("data", {}).get("result", [])
        except Exception as e:
            logger.error("prometheus_collector.query_error", query=promql, error=str(e))
            return []

    async def collect_node_metrics(self) -> List[NodeMetrics]:
        cpu_results = await self._query(NODE_CPU_QUERY)
        memory_results = await self._query(NODE_MEMORY_QUERY)
        disk_results = await self._query(NODE_DISK_QUERY)
        rx_results = await self._query(NODE_NETWORK_RX_QUERY)
        tx_results = await self._query(NODE_NETWORK_TX_QUERY)

        def _by_instance(results: List[Dict]) -> Dict[str, float]:
            return {
                r["metric"].get("instance", ""): float(r["value"][1])
                for r in results
                if r.get("value")
            }

        cpu_map = _by_instance(cpu_results)
        mem_map = _by_instance(memory_results)
        disk_map = _by_instance(disk_results)
        rx_map = _by_instance(rx_results)
        tx_map = _by_instance(tx_results)

        now = datetime.now(timezone.utc)
        nodes = []
        for instance in cpu_map:
            nodes.append(
                NodeMetrics(
                    node_name=instance,
                    cpu_usage_percent=cpu_map.get(instance, 0.0),
                    memory_usage_percent=mem_map.get(instance, 0.0),
                    disk_usage_percent=disk_map.get(instance, 0.0),
                    network_rx_bytes=int(rx_map.get(instance, 0)),
                    network_tx_bytes=int(tx_map.get(instance, 0)),
                    conditions={},
                    timestamp=now,
                )
            )
        return nodes

    async def collect_pod_metrics(
        self, namespace: str = ""
    ) -> List[PodMetrics]:
        ns_filter = f'namespace="{namespace}"' if namespace else ""

        cpu_query = POD_CPU_QUERY
        mem_query = POD_MEMORY_QUERY
        restart_query = POD_RESTART_QUERY
        if ns_filter:
            cpu_query = f"sum by (pod, namespace, node) (rate(container_cpu_usage_seconds_total{{{ns_filter}}}[5m])) * 1000"
            mem_query = f"sum by (pod, namespace, node) (container_memory_working_set_bytes{{{ns_filter}}})"
            restart_query = f"sum by (pod, namespace) (kube_pod_container_status_restarts_total{{{ns_filter}}})"

        cpu_results = await self._query(cpu_query)
        mem_results = await self._query(mem_query)
        restart_results = await self._query(restart_query)

        def _pod_key(metric: Dict) -> str:
            return f"{metric.get('namespace', '')}/{metric.get('pod', '')}"

        cpu_map = {
            _pod_key(r["metric"]): float(r["value"][1])
            for r in cpu_results
            if r.get("value")
        }
        mem_map = {
            _pod_key(r["metric"]): int(float(r["value"][1]))
            for r in mem_results
            if r.get("value")
        }
        restart_map = {
            _pod_key(r["metric"]): int(float(r["value"][1]))
            for r in restart_results
            if r.get("value")
        }

        now = datetime.now(timezone.utc)
        pods = []
        for r in cpu_results:
            metric = r["metric"]
            key = _pod_key(metric)
            pod_name = metric.get("pod", "")
            if not pod_name:
                continue
            pods.append(
                PodMetrics(
                    pod_name=pod_name,
                    namespace=metric.get("namespace", ""),
                    node_name=metric.get("node", ""),
                    cpu_usage_millicores=int(cpu_map.get(key, 0)),
                    memory_usage_bytes=mem_map.get(key, 0),
                    restart_count=restart_map.get(key, 0),
                    status="Running",
                    timestamp=now,
                )
            )
        return pods
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_prometheus.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/collector/base.py src/collector/prometheus.py tests/collector/test_prometheus.py
git commit -m "feat: add Prometheus metrics collector"
```

---

## Task 6: metrics-server collector

**Files:**
- Create: `tests/collector/test_metrics_server.py`
- Create: `src/collector/metrics_server.py`

- [ ] **Step 1: Write the failing tests**

`tests/collector/test_metrics_server.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.collector.metrics_server import MetricsServerCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def collector(config):
    return MetricsServerCollector(config)


class TestMetricsServerConnect:
    @pytest.mark.asyncio
    async def test_connect_in_cluster(self, collector):
        with patch("src.collector.metrics_server.config") as mock_k8s_config:
            with patch("src.collector.metrics_server.client") as mock_k8s_client:
                mock_k8s_config.load_incluster_config = MagicMock()
                mock_api = MagicMock()
                mock_k8s_client.CustomObjectsApi.return_value = mock_api
                await collector.connect()
                assert collector._api is not None

    @pytest.mark.asyncio
    async def test_connect_fallback_kubeconfig(self, collector):
        with patch("src.collector.metrics_server.config") as mock_k8s_config:
            with patch("src.collector.metrics_server.client") as mock_k8s_client:
                mock_k8s_config.load_incluster_config = MagicMock(
                    side_effect=Exception("not in cluster")
                )
                mock_k8s_config.load_kube_config = MagicMock()
                mock_api = MagicMock()
                mock_k8s_client.CustomObjectsApi.return_value = mock_api
                await collector.connect()
                assert collector._api is not None


class TestMetricsServerNodeMetrics:
    @pytest.mark.asyncio
    async def test_collect_node_metrics(self, collector):
        mock_api = MagicMock()
        mock_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "node-1"},
                    "usage": {"cpu": "500m", "memory": "2Gi"},
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        nodes = await collector.collect_node_metrics()
        assert len(nodes) == 1
        assert nodes[0].node_name == "node-1"
        assert nodes[0].cpu_usage_percent > 0


class TestMetricsServerPodMetrics:
    @pytest.mark.asyncio
    async def test_collect_pod_metrics_all_namespaces(self, collector):
        mock_api = MagicMock()
        mock_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "web-abc", "namespace": "default"},
                    "containers": [
                        {"name": "web", "usage": {"cpu": "100m", "memory": "128Mi"}}
                    ],
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        pods = await collector.collect_pod_metrics()
        assert len(pods) == 1
        assert pods[0].pod_name == "web-abc"
        assert pods[0].namespace == "default"

    @pytest.mark.asyncio
    async def test_collect_pod_metrics_specific_namespace(self, collector):
        mock_api = MagicMock()
        mock_api.list_namespaced_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "api-xyz", "namespace": "production"},
                    "containers": [
                        {"name": "api", "usage": {"cpu": "200m", "memory": "256Mi"}}
                    ],
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        pods = await collector.collect_pod_metrics(namespace="production")
        assert len(pods) == 1
        assert pods[0].namespace == "production"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_metrics_server.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/collector/metrics_server.py`:
```python
import structlog
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client, config

from src.collector.base import MetricsCollector
from src.config import Config
from src.models import NodeMetrics, PodMetrics

logger = structlog.get_logger()


def _parse_cpu(cpu_str: str) -> int:
    """Parse CPU string to millicores. E.g. '500m' -> 500, '1' -> 1000."""
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    if cpu_str.endswith("n"):
        return int(cpu_str[:-1]) // 1_000_000
    return int(float(cpu_str) * 1000)


def _parse_memory(mem_str: str) -> int:
    """Parse memory string to bytes. E.g. '128Mi' -> 134217728."""
    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for suffix, multiplier in suffixes.items():
        if mem_str.endswith(suffix):
            return int(float(mem_str[: -len(suffix)]) * multiplier)
    return int(mem_str)


class MetricsServerCollector(MetricsCollector):
    def __init__(self, config_obj: Config):
        self._config = config_obj
        self._api: Optional[client.CustomObjectsApi] = None

    async def connect(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._api = client.CustomObjectsApi()
        logger.info("metrics_server_collector.connected")

    async def close(self) -> None:
        self._api = None

    async def is_healthy(self) -> bool:
        if not self._api:
            return False
        try:
            self._api.list_cluster_custom_object(
                group="metrics.k8s.io", version="v1beta1", plural="nodes"
            )
            return True
        except Exception:
            return False

    async def collect_node_metrics(self) -> List[NodeMetrics]:
        if not self._api:
            return []
        try:
            result = self._api.list_cluster_custom_object(
                group="metrics.k8s.io", version="v1beta1", plural="nodes"
            )
        except Exception as e:
            logger.error("metrics_server_collector.node_error", error=str(e))
            return []

        now = datetime.now(timezone.utc)
        nodes = []
        for item in result.get("items", []):
            usage = item.get("usage", {})
            cpu_millicores = _parse_cpu(usage.get("cpu", "0"))
            memory_bytes = _parse_memory(usage.get("memory", "0"))
            nodes.append(
                NodeMetrics(
                    node_name=item["metadata"]["name"],
                    cpu_usage_percent=cpu_millicores / 10.0,
                    memory_usage_percent=memory_bytes / (1024**3) * 100,
                    disk_usage_percent=0.0,
                    network_rx_bytes=0,
                    network_tx_bytes=0,
                    conditions={},
                    timestamp=now,
                )
            )
        return nodes

    async def collect_pod_metrics(
        self, namespace: str = ""
    ) -> List[PodMetrics]:
        if not self._api:
            return []
        try:
            if namespace:
                result = self._api.list_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                )
            else:
                result = self._api.list_cluster_custom_object(
                    group="metrics.k8s.io", version="v1beta1", plural="pods"
                )
        except Exception as e:
            logger.error("metrics_server_collector.pod_error", error=str(e))
            return []

        now = datetime.now(timezone.utc)
        pods = []
        for item in result.get("items", []):
            containers = item.get("containers", [])
            total_cpu = sum(_parse_cpu(c["usage"].get("cpu", "0")) for c in containers)
            total_mem = sum(_parse_memory(c["usage"].get("memory", "0")) for c in containers)
            pods.append(
                PodMetrics(
                    pod_name=item["metadata"]["name"],
                    namespace=item["metadata"].get("namespace", ""),
                    node_name="",
                    cpu_usage_millicores=total_cpu,
                    memory_usage_bytes=total_mem,
                    restart_count=0,
                    status="Running",
                    timestamp=now,
                )
            )
        return pods
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_metrics_server.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/collector/metrics_server.py tests/collector/test_metrics_server.py
git commit -m "feat: add metrics-server collector"
```

---

## Task 7: Kubernetes API collector

**Files:**
- Create: `tests/collector/test_k8s_api.py`
- Create: `src/collector/k8s_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/collector/test_k8s_api.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.collector.k8s_api import KubernetesApiCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def collector(config):
    return KubernetesApiCollector(config)


def _make_event(reason="OOMKilled", event_type="Warning", name="web-abc", namespace="default"):
    event = MagicMock()
    event.type = event_type
    event.reason = reason
    event.message = f"Container {reason}"
    event.count = 1
    event.first_timestamp = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    event.last_timestamp = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    event.involved_object = MagicMock()
    event.involved_object.kind = "Pod"
    event.involved_object.name = name
    event.involved_object.namespace = namespace
    return event


def _make_deployment(name="web", namespace="default", desired=3, ready=3):
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.namespace = namespace
    dep.spec.replicas = desired
    dep.status.ready_replicas = ready
    dep.status.conditions = []
    return dep


class TestKubernetesApiConnect:
    @pytest.mark.asyncio
    async def test_connect(self, collector):
        with patch("src.collector.k8s_api.config") as mock_config:
            with patch("src.collector.k8s_api.client") as mock_client:
                mock_config.load_incluster_config = MagicMock()
                await collector.connect()
                assert collector._core_api is not None
                assert collector._apps_api is not None


class TestKubernetesApiEvents:
    @pytest.mark.asyncio
    async def test_collect_events(self, collector):
        mock_core = MagicMock()
        event = _make_event()
        mock_core.list_event_for_all_namespaces.return_value = MagicMock(items=[event])
        collector._core_api = mock_core

        events = await collector.collect_events()
        assert len(events) == 1
        assert events[0].reason == "OOMKilled"
        assert events[0].event_type == "Warning"

    @pytest.mark.asyncio
    async def test_collect_events_namespace(self, collector):
        mock_core = MagicMock()
        event = _make_event()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[event])
        collector._core_api = mock_core

        events = await collector.collect_events(namespace="production")
        assert len(events) == 1
        mock_core.list_namespaced_event.assert_called_once_with("production")


class TestKubernetesApiResourceStates:
    @pytest.mark.asyncio
    async def test_collect_resource_states(self, collector):
        mock_apps = MagicMock()
        dep = _make_deployment()
        mock_apps.list_deployment_for_all_namespaces.return_value = MagicMock(items=[dep])
        mock_apps.list_stateful_set_for_all_namespaces.return_value = MagicMock(items=[])
        mock_apps.list_daemon_set_for_all_namespaces.return_value = MagicMock(items=[])
        collector._apps_api = mock_apps

        mock_batch = MagicMock()
        mock_batch.list_job_for_all_namespaces.return_value = MagicMock(items=[])
        mock_batch.list_cron_job_for_all_namespaces.return_value = MagicMock(items=[])
        collector._batch_api = mock_batch

        states = await collector.collect_resource_states()
        assert len(states) >= 1
        assert states[0].kind == "Deployment"
        assert states[0].name == "web"
        assert states[0].desired_replicas == 3
        assert states[0].ready_replicas == 3


class TestKubernetesApiHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, collector):
        mock_core = MagicMock()
        mock_core.get_api_versions.return_value = MagicMock()
        collector._core_api = mock_core
        assert await collector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false(self, collector):
        assert await collector.is_healthy() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_k8s_api.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/collector/k8s_api.py`:
```python
import structlog
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client, config

from src.collector.base import StateCollector
from src.config import Config
from src.models import KubernetesEvent, ResourceState

logger = structlog.get_logger()


class KubernetesApiCollector(StateCollector):
    def __init__(self, config_obj: Config):
        self._config = config_obj
        self._core_api: Optional[client.CoreV1Api] = None
        self._apps_api: Optional[client.AppsV1Api] = None
        self._batch_api: Optional[client.BatchV1Api] = None

    async def connect(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()
        self._batch_api = client.BatchV1Api()
        logger.info("k8s_api_collector.connected")

    async def close(self) -> None:
        self._core_api = None
        self._apps_api = None
        self._batch_api = None

    async def is_healthy(self) -> bool:
        if not self._core_api:
            return False
        try:
            self._core_api.get_api_versions()
            return True
        except Exception:
            return False

    async def collect_events(
        self, namespace: str = ""
    ) -> List[KubernetesEvent]:
        if not self._core_api:
            return []
        try:
            if namespace:
                result = self._core_api.list_namespaced_event(namespace)
            else:
                result = self._core_api.list_event_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.events_error", error=str(e))
            return []

        events = []
        for item in result.items:
            events.append(
                KubernetesEvent(
                    event_type=item.type or "Normal",
                    reason=item.reason or "",
                    message=item.message or "",
                    involved_object_kind=item.involved_object.kind or "",
                    involved_object_name=item.involved_object.name or "",
                    involved_object_namespace=item.involved_object.namespace or "",
                    count=item.count or 1,
                    first_timestamp=item.first_timestamp or datetime.now(timezone.utc),
                    last_timestamp=item.last_timestamp or datetime.now(timezone.utc),
                )
            )
        return events

    async def collect_resource_states(
        self, namespace: str = ""
    ) -> List[ResourceState]:
        states: List[ResourceState] = []
        now = datetime.now(timezone.utc)

        states.extend(await self._collect_deployments(namespace, now))
        states.extend(await self._collect_statefulsets(namespace, now))
        states.extend(await self._collect_daemonsets(namespace, now))
        states.extend(await self._collect_jobs(namespace, now))
        states.extend(await self._collect_cronjobs(namespace, now))

        return states

    async def _collect_deployments(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_deployment(namespace)
            else:
                result = self._apps_api.list_deployment_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.deployments_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Deployment",
                name=d.metadata.name,
                namespace=d.metadata.namespace,
                desired_replicas=d.spec.replicas,
                ready_replicas=d.status.ready_replicas or 0,
                conditions={},
                timestamp=now,
            )
            for d in result.items
        ]

    async def _collect_statefulsets(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_stateful_set(namespace)
            else:
                result = self._apps_api.list_stateful_set_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.statefulsets_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="StatefulSet",
                name=s.metadata.name,
                namespace=s.metadata.namespace,
                desired_replicas=s.spec.replicas,
                ready_replicas=s.status.ready_replicas or 0,
                conditions={},
                timestamp=now,
            )
            for s in result.items
        ]

    async def _collect_daemonsets(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_daemon_set(namespace)
            else:
                result = self._apps_api.list_daemon_set_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.daemonsets_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="DaemonSet",
                name=d.metadata.name,
                namespace=d.metadata.namespace,
                desired_replicas=d.status.desired_number_scheduled,
                ready_replicas=d.status.number_ready or 0,
                conditions={},
                timestamp=now,
            )
            for d in result.items
        ]

    async def _collect_jobs(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._batch_api:
            return []
        try:
            if namespace:
                result = self._batch_api.list_namespaced_job(namespace)
            else:
                result = self._batch_api.list_job_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.jobs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Job",
                name=j.metadata.name,
                namespace=j.metadata.namespace,
                desired_replicas=j.spec.completions,
                ready_replicas=j.status.succeeded or 0,
                conditions={},
                timestamp=now,
            )
            for j in result.items
        ]

    async def _collect_cronjobs(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._batch_api:
            return []
        try:
            if namespace:
                result = self._batch_api.list_namespaced_cron_job(namespace)
            else:
                result = self._batch_api.list_cron_job_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.cronjobs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="CronJob",
                name=c.metadata.name,
                namespace=c.metadata.namespace,
                conditions={
                    "schedule": c.spec.schedule or "",
                    "suspended": c.spec.suspend or False,
                },
                timestamp=now,
            )
            for c in result.items
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/collector/test_k8s_api.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/collector/k8s_api.py tests/collector/test_k8s_api.py
git commit -m "feat: add Kubernetes API state collector"
```

---

## Task 8: Storage base interface and Elasticsearch implementation

**Files:**
- Create: `src/storage/base.py`
- Create: `tests/storage/test_elasticsearch.py`
- Create: `src/storage/elasticsearch.py`

- [ ] **Step 1: Write the base interface**

`src/storage/base.py`:
```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.models import StoredRecord


class BaseStorage(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the storage backend."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection to the storage backend."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the storage backend is reachable."""

    @abstractmethod
    async def store(self, index: str, record: StoredRecord) -> None:
        """Store a single record."""

    @abstractmethod
    async def store_bulk(self, index: str, records: List[StoredRecord]) -> int:
        """Store multiple records. Returns the number of successfully stored records."""

    @abstractmethod
    async def query(
        self,
        index: str,
        query_body: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query records from the storage backend."""
```

- [ ] **Step 2: Write the failing tests**

`tests/storage/test_elasticsearch.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.storage.elasticsearch import ElasticsearchStorage
from src.config import Config
from src.models import StoredRecord


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        elasticsearch_username="elastic",
        elasticsearch_password="changeme",
    )


@pytest.fixture
def storage(config):
    return ElasticsearchStorage(config)


class TestElasticsearchConnect:
    @pytest.mark.asyncio
    async def test_connect(self, storage):
        with patch("src.storage.elasticsearch.AsyncElasticsearch") as mock_es_cls:
            mock_es = AsyncMock()
            mock_es.info = AsyncMock(return_value={"version": {"number": "8.0.0"}})
            mock_es_cls.return_value = mock_es
            await storage.connect()
            assert storage._client is not None


class TestElasticsearchHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, storage):
        storage._client = AsyncMock()
        storage._client.ping = AsyncMock(return_value=True)
        assert await storage.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false(self, storage):
        assert await storage.is_healthy() is False


class TestElasticsearchStore:
    @pytest.mark.asyncio
    async def test_store_single(self, storage, sample_timestamp):
        storage._client = AsyncMock()
        storage._client.index = AsyncMock(return_value={"result": "created"})

        record = StoredRecord(
            record_type="node_metrics",
            data={"node_name": "node-1", "cpu": 45.2},
            timestamp=sample_timestamp,
            cluster_name="prod",
        )
        await storage.store("sre-metrics", record)
        storage._client.index.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_bulk(self, storage, sample_timestamp):
        storage._client = AsyncMock()

        with patch("src.storage.elasticsearch.async_bulk") as mock_bulk:
            mock_bulk.return_value = (2, [])
            records = [
                StoredRecord(
                    record_type="node_metrics",
                    data={"node_name": "node-1"},
                    timestamp=sample_timestamp,
                    cluster_name="prod",
                ),
                StoredRecord(
                    record_type="node_metrics",
                    data={"node_name": "node-2"},
                    timestamp=sample_timestamp,
                    cluster_name="prod",
                ),
            ]
            count = await storage.store_bulk("sre-metrics", records)
            assert count == 2


class TestElasticsearchQuery:
    @pytest.mark.asyncio
    async def test_query(self, storage):
        storage._client = AsyncMock()
        storage._client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {"_source": {"record_type": "node_metrics", "data": {"cpu": 45}}},
                        {"_source": {"record_type": "node_metrics", "data": {"cpu": 60}}},
                    ]
                }
            }
        )

        results = await storage.query("sre-metrics", {"match_all": {}})
        assert len(results) == 2
        assert results[0]["record_type"] == "node_metrics"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/storage/test_elasticsearch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the implementation**

`src/storage/elasticsearch.py`:
```python
import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from src.config import Config
from src.models import StoredRecord
from src.storage.base import BaseStorage

logger = structlog.get_logger()


class ElasticsearchStorage(BaseStorage):
    def __init__(self, config: Config):
        self._config = config
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        kwargs: Dict[str, Any] = {
            "hosts": [self._config.elasticsearch_url],
        }
        if self._config.elasticsearch_username and self._config.elasticsearch_password:
            kwargs["basic_auth"] = (
                self._config.elasticsearch_username,
                self._config.elasticsearch_password,
            )
        self._client = AsyncElasticsearch(**kwargs)
        info = await self._client.info()
        logger.info(
            "elasticsearch_storage.connected",
            version=info["version"]["number"],
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def store(self, index: str, record: StoredRecord) -> None:
        if not self._client:
            return
        doc = record.model_dump()
        doc["data"] = record.data
        try:
            await self._client.index(index=index, document=doc)
        except Exception as e:
            logger.error("elasticsearch_storage.store_error", index=index, error=str(e))

    async def store_bulk(self, index: str, records: List[StoredRecord]) -> int:
        if not self._client:
            return 0
        actions = [
            {
                "_index": index,
                "_source": r.model_dump(),
            }
            for r in records
        ]
        try:
            success, errors = await async_bulk(self._client, actions)
            if errors:
                logger.warning(
                    "elasticsearch_storage.bulk_errors",
                    error_count=len(errors),
                )
            return success
        except Exception as e:
            logger.error("elasticsearch_storage.bulk_error", index=index, error=str(e))
            return 0

    async def query(
        self,
        index: str,
        query_body: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        try:
            result = await self._client.search(
                index=index, query=query_body, size=size
            )
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.error("elasticsearch_storage.query_error", index=index, error=str(e))
            return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/storage/test_elasticsearch.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/storage/base.py src/storage/elasticsearch.py tests/storage/test_elasticsearch.py
git commit -m "feat: add Elasticsearch storage module"
```

---

## Task 9: Agent orchestrator

**Files:**
- Create: `tests/test_agent.py` (replace existing)
- Rewrite: `src/agent.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_agent.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.agent import SREAgent
from src.config import Config
from src.models import (
    CollectedData,
    NodeMetrics,
    PodMetrics,
    KubernetesEvent,
    ResourceState,
    StoredRecord,
)


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        collectors_prometheus_enabled=True,
        collectors_metrics_server_enabled=True,
        collectors_k8s_api_enabled=True,
    )


@pytest.fixture
def agent(config):
    a = SREAgent(config)
    a._prometheus = AsyncMock()
    a._metrics_server = AsyncMock()
    a._k8s_api = AsyncMock()
    a._storage = AsyncMock()
    return a


class TestSREAgentInit:
    def test_init(self, config):
        agent = SREAgent(config)
        assert agent._config is config
        assert agent._running is False


class TestSREAgentCollect:
    @pytest.mark.asyncio
    async def test_collect_aggregates_all_sources(self, agent, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.0,
            memory_usage_percent=60.0,
            disk_usage_percent=30.0,
            network_rx_bytes=0,
            network_tx_bytes=0,
            conditions={},
            timestamp=sample_timestamp,
        )
        pod = PodMetrics(
            pod_name="web-abc",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,
            restart_count=0,
            status="Running",
            timestamp=sample_timestamp,
        )
        event = KubernetesEvent(
            event_type="Warning",
            reason="OOMKilled",
            message="OOM",
            involved_object_kind="Pod",
            involved_object_name="web-abc",
            involved_object_namespace="default",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        state = ResourceState(
            kind="Deployment",
            name="web",
            namespace="default",
            desired_replicas=3,
            ready_replicas=3,
            conditions={},
            timestamp=sample_timestamp,
        )

        agent._prometheus.collect_node_metrics = AsyncMock(return_value=[node])
        agent._prometheus.collect_pod_metrics = AsyncMock(return_value=[pod])
        agent._metrics_server.collect_node_metrics = AsyncMock(return_value=[])
        agent._metrics_server.collect_pod_metrics = AsyncMock(return_value=[])
        agent._k8s_api.collect_events = AsyncMock(return_value=[event])
        agent._k8s_api.collect_resource_states = AsyncMock(return_value=[state])

        data = await agent.collect()
        assert len(data.node_metrics) == 1
        assert len(data.pod_metrics) == 1
        assert len(data.events) == 1
        assert len(data.resource_states) == 1

    @pytest.mark.asyncio
    async def test_collect_handles_disabled_collectors(self, config):
        config_disabled = Config(
            elasticsearch_url="http://localhost:9200",
            collectors_prometheus_enabled=False,
            collectors_metrics_server_enabled=False,
            collectors_k8s_api_enabled=False,
        )
        agent = SREAgent(config_disabled)
        data = await agent.collect()
        assert data.node_metrics == []
        assert data.pod_metrics == []
        assert data.events == []
        assert data.resource_states == []


class TestSREAgentStore:
    @pytest.mark.asyncio
    async def test_store_writes_to_elasticsearch(self, agent, sample_timestamp):
        data = CollectedData(
            node_metrics=[
                NodeMetrics(
                    node_name="node-1",
                    cpu_usage_percent=45.0,
                    memory_usage_percent=60.0,
                    disk_usage_percent=30.0,
                    network_rx_bytes=0,
                    network_tx_bytes=0,
                    conditions={},
                    timestamp=sample_timestamp,
                )
            ],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        agent._storage.store_bulk = AsyncMock(return_value=1)

        await agent.store(data)
        agent._storage.store_bulk.assert_called()


class TestSREAgentCycle:
    @pytest.mark.asyncio
    async def test_run_cycle(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()

        await agent.run_cycle()
        agent.collect.assert_awaited_once()
        agent.store.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_agent.py -v`
Expected: FAIL — new SREAgent class not implemented.

- [ ] **Step 3: Write the implementation**

`src/agent.py`:
```python
import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.collector.k8s_api import KubernetesApiCollector
from src.collector.metrics_server import MetricsServerCollector
from src.collector.prometheus import PrometheusCollector
from src.config import Config
from src.models import CollectedData, StoredRecord
from src.storage.elasticsearch import ElasticsearchStorage

logger = structlog.get_logger()


class SREAgent:
    def __init__(self, config: Config):
        self._config = config
        self._running = False

        self._prometheus: Optional[PrometheusCollector] = (
            PrometheusCollector(config) if config.collectors_prometheus_enabled else None
        )
        self._metrics_server: Optional[MetricsServerCollector] = (
            MetricsServerCollector(config) if config.collectors_metrics_server_enabled else None
        )
        self._k8s_api: Optional[KubernetesApiCollector] = (
            KubernetesApiCollector(config) if config.collectors_k8s_api_enabled else None
        )
        self._storage = ElasticsearchStorage(config)

    async def initialize(self) -> None:
        logger.info("agent.initializing")
        await self._storage.connect()
        if self._prometheus:
            await self._prometheus.connect()
        if self._metrics_server:
            await self._metrics_server.connect()
        if self._k8s_api:
            await self._k8s_api.connect()
        logger.info("agent.initialized")

    async def collect(self) -> CollectedData:
        now = datetime.now(timezone.utc)
        node_metrics = []
        pod_metrics = []
        events = []
        resource_states = []

        if self._prometheus:
            try:
                node_metrics.extend(await self._prometheus.collect_node_metrics())
                pod_metrics.extend(await self._prometheus.collect_pod_metrics())
            except Exception as e:
                logger.error("agent.prometheus_error", error=str(e))

        if self._metrics_server:
            try:
                ms_nodes = await self._metrics_server.collect_node_metrics()
                ms_pods = await self._metrics_server.collect_pod_metrics()
                existing_node_names = {n.node_name for n in node_metrics}
                for n in ms_nodes:
                    if n.node_name not in existing_node_names:
                        node_metrics.append(n)
                existing_pod_names = {p.pod_name for p in pod_metrics}
                for p in ms_pods:
                    if p.pod_name not in existing_pod_names:
                        pod_metrics.append(p)
            except Exception as e:
                logger.error("agent.metrics_server_error", error=str(e))

        if self._k8s_api:
            try:
                events = await self._k8s_api.collect_events()
                resource_states = await self._k8s_api.collect_resource_states()
            except Exception as e:
                logger.error("agent.k8s_api_error", error=str(e))

        logger.info(
            "agent.collected",
            nodes=len(node_metrics),
            pods=len(pod_metrics),
            events=len(events),
            resources=len(resource_states),
        )
        return CollectedData(
            node_metrics=node_metrics,
            pod_metrics=pod_metrics,
            events=events,
            resource_states=resource_states,
            collection_timestamp=now,
        )

    async def store(self, data: CollectedData) -> None:
        metrics_index = self._config.elasticsearch_indices_metrics
        logs_index = self._config.elasticsearch_indices_logs

        records = []
        for node in data.node_metrics:
            records.append(
                StoredRecord(
                    record_type="node_metrics",
                    data=node.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for pod in data.pod_metrics:
            records.append(
                StoredRecord(
                    record_type="pod_metrics",
                    data=pod.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for event in data.events:
            records.append(
                StoredRecord(
                    record_type="k8s_event",
                    data=event.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for state in data.resource_states:
            records.append(
                StoredRecord(
                    record_type="resource_state",
                    data=state.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )

        if records:
            stored = await self._storage.store_bulk(metrics_index, records)
            logger.info("agent.stored", count=stored)

    async def run_cycle(self) -> None:
        logger.info("agent.cycle_start")
        data = await self.collect()
        await self.store(data)
        logger.info("agent.cycle_end")

    async def start(self) -> None:
        await self.initialize()
        self._running = True
        logger.info("agent.started", interval=self._config.agent_analysis_interval)
        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error("agent.cycle_error", error=str(e))
            await asyncio.sleep(self._config.agent_analysis_interval)

    async def stop(self) -> None:
        self._running = False
        await self._storage.close()
        if self._prometheus:
            await self._prometheus.close()
        if self._metrics_server:
            await self._metrics_server.close()
        if self._k8s_api:
            await self._k8s_api.close()
        logger.info("agent.stopped")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_agent.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: rewrite agent orchestrator with modular collectors"
```

---

## Task 10: FastAPI base endpoints

**Files:**
- Create: `tests/test_api.py`
- Rewrite: `src/api/routes.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from src.api.routes import create_app
from src.config import Config


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    agent._config = Config(elasticsearch_url="http://localhost:9200")
    agent._storage = AsyncMock()
    agent._storage.is_healthy = AsyncMock(return_value=True)
    agent._prometheus = AsyncMock()
    agent._prometheus.is_healthy = AsyncMock(return_value=True)
    agent._metrics_server = AsyncMock()
    agent._metrics_server.is_healthy = AsyncMock(return_value=True)
    agent._k8s_api = AsyncMock()
    agent._k8s_api.is_healthy = AsyncMock(return_value=True)
    agent._running = True
    return agent


@pytest.fixture
def app(config, mock_agent):
    return create_app(config, mock_agent)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestReadyEndpoint:
    @pytest.mark.asyncio
    async def test_ready_all_healthy(self, client):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    @pytest.mark.asyncio
    async def test_ready_es_unhealthy(self, client, mock_agent):
        mock_agent._storage.is_healthy = AsyncMock(return_value=False)
        resp = await client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status(self, client):
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "elasticsearch" in data
        assert "prometheus" in data
        assert "agent_running" in data


class TestConfigEndpoint:
    @pytest.mark.asyncio
    async def test_config_no_secrets(self, client):
        resp = await client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "elasticsearch_password" not in data
        assert "intelligence_api_key" not in data
        assert "elasticsearch_url" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_api.py -v`
Expected: FAIL — `create_app` not found.

- [ ] **Step 3: Write the implementation**

`src/api/routes.py`:
```python
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config import Config

SECRETS_FIELDS = {
    "elasticsearch_password",
    "elasticsearch_secret_ref",
    "intelligence_api_key",
    "intelligence_api_key_secret_ref",
}


def create_app(config: Config, agent) -> FastAPI:
    app = FastAPI(title="EFK SRE Agent", version="2.0.0")
    start_time = datetime.now(timezone.utc)

    @app.get("/health")
    async def health():
        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {"status": "ok", "uptime_seconds": uptime}

    @app.get("/ready")
    async def ready():
        es_ok = await agent._storage.is_healthy()
        prom_ok = True
        if agent._prometheus:
            prom_ok = await agent._prometheus.is_healthy()

        all_ready = es_ok and prom_ok
        status_code = 200 if all_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "ready": all_ready,
                "elasticsearch": es_ok,
                "prometheus": prom_ok,
            },
        )

    @app.get("/status")
    async def status():
        es_ok = await agent._storage.is_healthy()
        prom_ok = False
        ms_ok = False
        k8s_ok = False
        if agent._prometheus:
            prom_ok = await agent._prometheus.is_healthy()
        if agent._metrics_server:
            ms_ok = await agent._metrics_server.is_healthy()
        if agent._k8s_api:
            k8s_ok = await agent._k8s_api.is_healthy()

        return {
            "agent_running": agent._running,
            "uptime_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            "elasticsearch": es_ok,
            "prometheus": prom_ok,
            "metrics_server": ms_ok,
            "kubernetes_api": k8s_ok,
        }

    @app.get("/config")
    async def get_config():
        config_dict = config.model_dump()
        return {k: v for k, v in config_dict.items() if k not in SECRETS_FIELDS}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/test_api.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat: add FastAPI base endpoints (health, ready, status, config)"
```

---

## Task 11: Entrypoint

**Files:**
- Rewrite: `src/main.py`

- [ ] **Step 1: Write the implementation**

`src/main.py`:
```python
import asyncio
import signal
import os

import structlog
import uvicorn

from src.agent import SREAgent
from src.api.routes import create_app
from src.config import Config


def setup_logging(log_level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if os.getenv("LOG_FORMAT") == "console"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(log_level)
        ),
    )


async def main() -> None:
    config = Config(
        elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200"),
        elasticsearch_username=os.getenv("ELASTICSEARCH_USERNAME", ""),
        elasticsearch_password=os.getenv("ELASTICSEARCH_PASSWORD", ""),
        elasticsearch_indices_metrics=os.getenv("ELASTICSEARCH_INDICES_METRICS", "sre-metrics"),
        elasticsearch_indices_logs=os.getenv("ELASTICSEARCH_INDICES_LOGS", "sre-logs"),
        elasticsearch_indices_anomalies=os.getenv("ELASTICSEARCH_INDICES_ANOMALIES", "sre-anomalies"),
        agent_analysis_interval=int(os.getenv("AGENT_ANALYSIS_INTERVAL", "300")),
        agent_log_level=os.getenv("AGENT_LOG_LEVEL", "INFO"),
        collectors_prometheus_enabled=os.getenv("COLLECTORS_PROMETHEUS_ENABLED", "true").lower() == "true",
        collectors_prometheus_url=os.getenv("COLLECTORS_PROMETHEUS_URL", "http://prometheus-server:9090"),
        collectors_metrics_server_enabled=os.getenv("COLLECTORS_METRICS_SERVER_ENABLED", "true").lower() == "true",
        collectors_k8s_api_enabled=os.getenv("COLLECTORS_K8S_API_ENABLED", "true").lower() == "true",
        collectors_k8s_api_watch_events=os.getenv("COLLECTORS_K8S_API_WATCH_EVENTS", "true").lower() == "true",
        thresholds_cpu_warning=float(os.getenv("THRESHOLDS_CPU_WARNING", "70")),
        thresholds_cpu_critical=float(os.getenv("THRESHOLDS_CPU_CRITICAL", "85")),
        thresholds_memory_warning=float(os.getenv("THRESHOLDS_MEMORY_WARNING", "70")),
        thresholds_memory_critical=float(os.getenv("THRESHOLDS_MEMORY_CRITICAL", "85")),
        thresholds_disk_warning=float(os.getenv("THRESHOLDS_DISK_WARNING", "80")),
        thresholds_disk_critical=float(os.getenv("THRESHOLDS_DISK_CRITICAL", "90")),
        ml_retrain_interval=int(os.getenv("ML_RETRAIN_INTERVAL", "3600")),
        ml_window_size=int(os.getenv("ML_WINDOW_SIZE", "100")),
        ml_anomaly_threshold=float(os.getenv("ML_ANOMALY_THRESHOLD", "0.05")),
        intelligence_enabled=os.getenv("INTELLIGENCE_ENABLED", "false").lower() == "true",
        intelligence_provider=os.getenv("INTELLIGENCE_PROVIDER", ""),
        intelligence_api_url=os.getenv("INTELLIGENCE_API_URL", ""),
        intelligence_api_key=os.getenv("INTELLIGENCE_API_KEY", ""),
        intelligence_model=os.getenv("INTELLIGENCE_MODEL", ""),
        alerter_alertmanager_enabled=os.getenv("ALERTER_ALERTMANAGER_ENABLED", "true").lower() == "true",
        alerter_alertmanager_url=os.getenv("ALERTER_ALERTMANAGER_URL", "http://alertmanager:9093"),
        alerter_fallback_webhook_enabled=os.getenv("ALERTER_FALLBACK_WEBHOOK_ENABLED", "false").lower() == "true",
        alerter_fallback_webhook_url=os.getenv("ALERTER_FALLBACK_WEBHOOK_URL", ""),
    )

    setup_logging(config.agent_log_level)
    logger = structlog.get_logger()
    logger.info("agent.starting")

    agent = SREAgent(config)
    app = create_app(config, agent)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.stop()))

    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning")
    server = uvicorn.Server(uvicorn_config)

    await asyncio.gather(
        agent.start(),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: rewrite entrypoint with modular config and API"
```

---

## Task 12: Helm chart rewrite

**Files:**
- Modify: `helm/kube-seer/Chart.yaml`
- Rewrite: `helm/kube-seer/values.yaml`
- Rewrite: `helm/kube-seer/templates/deployment.yaml`
- Rewrite: `helm/kube-seer/templates/configmap.yaml`
- Rewrite: `helm/kube-seer/templates/secret.yaml`
- Rewrite: `helm/kube-seer/templates/service.yaml`
- Rewrite: `helm/kube-seer/templates/serviceaccount.yaml`
- Create: `helm/kube-seer/templates/clusterrole.yaml`
- Create: `helm/kube-seer/templates/clusterrolebinding.yaml`
- Create: `helm/kube-seer/templates/pdb.yaml`
- Rewrite: `helm/kube-seer/templates/servicemonitor.yaml`
- Delete: `helm/kube-seer/templates/ingress.yaml`
- Delete: `helm/kube-seer/templates/hpa.yaml`
- Delete: `helm/kube-seer/templates/pvc.yaml`

- [ ] **Step 1: Update Chart.yaml**

`helm/kube-seer/Chart.yaml`:
```yaml
apiVersion: v2
name: kube-seer
description: AI-powered SRE agent for Kubernetes cluster monitoring
type: application
version: 2.0.0
appVersion: "2.0.0"
```

- [ ] **Step 2: Rewrite values.yaml**

`helm/kube-seer/values.yaml`:
```yaml
# Agent
agent:
  analysisInterval: 300
  logLevel: INFO

# Elasticsearch (external prerequisite)
elasticsearch:
  url: ""
  username: ""
  password: ""
  secretRef: ""
  indices:
    metrics: "sre-metrics"
    logs: "sre-logs"
    anomalies: "sre-anomalies"

# Collectors
collectors:
  prometheus:
    enabled: true
    url: "http://prometheus-server:9090"
  metricsServer:
    enabled: true
  kubernetesApi:
    enabled: true
    watchEvents: true

# Detection thresholds
thresholds:
  cpu:
    warning: 70
    critical: 85
  memory:
    warning: 70
    critical: 85
  disk:
    warning: 80
    critical: 90

# ML
ml:
  retrainInterval: 3600
  windowSize: 100
  anomalyThreshold: 0.05

# Intelligence (optional LLM)
intelligence:
  enabled: false
  provider: ""
  apiUrl: ""
  apiKey: ""
  apiKeySecretRef: ""
  model: ""

# Alerting
alerter:
  alertmanager:
    enabled: true
    url: "http://alertmanager:9093"
  fallback:
    webhook:
      enabled: false
      url: ""

# Image
image:
  repository: damsdgn29/kube-seer
  tag: "2.0.0"
  pullPolicy: IfNotPresent

# Resources
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    memory: 256Mi

# Service
service:
  type: ClusterIP
  port: 8080

# ServiceMonitor
serviceMonitor:
  enabled: false
  interval: 30s

# Pod disruption budget
podDisruptionBudget:
  enabled: true
  minAvailable: 1

# Security
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  fsGroup: 1001
```

- [ ] **Step 3: Rewrite templates**

`helm/kube-seer/templates/configmap.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
data:
  ELASTICSEARCH_URL: {{ .Values.elasticsearch.url | quote }}
  ELASTICSEARCH_USERNAME: {{ .Values.elasticsearch.username | quote }}
  ELASTICSEARCH_INDICES_METRICS: {{ .Values.elasticsearch.indices.metrics | quote }}
  ELASTICSEARCH_INDICES_LOGS: {{ .Values.elasticsearch.indices.logs | quote }}
  ELASTICSEARCH_INDICES_ANOMALIES: {{ .Values.elasticsearch.indices.anomalies | quote }}
  AGENT_ANALYSIS_INTERVAL: {{ .Values.agent.analysisInterval | quote }}
  AGENT_LOG_LEVEL: {{ .Values.agent.logLevel | quote }}
  COLLECTORS_PROMETHEUS_ENABLED: {{ .Values.collectors.prometheus.enabled | quote }}
  COLLECTORS_PROMETHEUS_URL: {{ .Values.collectors.prometheus.url | quote }}
  COLLECTORS_METRICS_SERVER_ENABLED: {{ .Values.collectors.metricsServer.enabled | quote }}
  COLLECTORS_K8S_API_ENABLED: {{ .Values.collectors.kubernetesApi.enabled | quote }}
  COLLECTORS_K8S_API_WATCH_EVENTS: {{ .Values.collectors.kubernetesApi.watchEvents | quote }}
  THRESHOLDS_CPU_WARNING: {{ .Values.thresholds.cpu.warning | quote }}
  THRESHOLDS_CPU_CRITICAL: {{ .Values.thresholds.cpu.critical | quote }}
  THRESHOLDS_MEMORY_WARNING: {{ .Values.thresholds.memory.warning | quote }}
  THRESHOLDS_MEMORY_CRITICAL: {{ .Values.thresholds.memory.critical | quote }}
  THRESHOLDS_DISK_WARNING: {{ .Values.thresholds.disk.warning | quote }}
  THRESHOLDS_DISK_CRITICAL: {{ .Values.thresholds.disk.critical | quote }}
  ML_RETRAIN_INTERVAL: {{ .Values.ml.retrainInterval | quote }}
  ML_WINDOW_SIZE: {{ .Values.ml.windowSize | quote }}
  ML_ANOMALY_THRESHOLD: {{ .Values.ml.anomalyThreshold | quote }}
  INTELLIGENCE_ENABLED: {{ .Values.intelligence.enabled | quote }}
  INTELLIGENCE_PROVIDER: {{ .Values.intelligence.provider | quote }}
  INTELLIGENCE_API_URL: {{ .Values.intelligence.apiUrl | quote }}
  INTELLIGENCE_MODEL: {{ .Values.intelligence.model | quote }}
  ALERTER_ALERTMANAGER_ENABLED: {{ .Values.alerter.alertmanager.enabled | quote }}
  ALERTER_ALERTMANAGER_URL: {{ .Values.alerter.alertmanager.url | quote }}
  ALERTER_FALLBACK_WEBHOOK_ENABLED: {{ .Values.alerter.fallback.webhook.enabled | quote }}
  ALERTER_FALLBACK_WEBHOOK_URL: {{ .Values.alerter.fallback.webhook.url | quote }}
```

`helm/kube-seer/templates/secret.yaml`:
```yaml
{{- if not .Values.elasticsearch.secretRef }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
type: Opaque
stringData:
  ELASTICSEARCH_PASSWORD: {{ .Values.elasticsearch.password | quote }}
  {{- if .Values.intelligence.apiKey }}
  INTELLIGENCE_API_KEY: {{ .Values.intelligence.apiKey | quote }}
  {{- end }}
{{- end }}
```

`helm/kube-seer/templates/deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "kube-seer.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        checksum/secret: {{ include (print $.Template.BasePath "/secret.yaml") . | sha256sum }}
      labels:
        {{- include "kube-seer.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ include "kube-seer.fullname" . }}
      securityContext:
        runAsNonRoot: {{ .Values.securityContext.runAsNonRoot }}
        runAsUser: {{ .Values.securityContext.runAsUser }}
        runAsGroup: {{ .Values.securityContext.runAsGroup }}
        fsGroup: {{ .Values.securityContext.fsGroup }}
      containers:
        - name: agent
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          envFrom:
            - configMapRef:
                name: {{ include "kube-seer.fullname" . }}
            {{- if .Values.elasticsearch.secretRef }}
            - secretRef:
                name: {{ .Values.elasticsearch.secretRef }}
            {{- else }}
            - secretRef:
                name: {{ include "kube-seer.fullname" . }}
            {{- end }}
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
```

`helm/kube-seer/templates/service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "kube-seer.selectorLabels" . | nindent 4 }}
```

`helm/kube-seer/templates/serviceaccount.yaml`:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
```

`helm/kube-seer/templates/clusterrole.yaml`:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes", "events", "services", "namespaces", "persistentvolumes", "persistentvolumeclaims", "resourcequotas", "limitranges"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["clusterroles", "clusterrolebindings"]
    verbs: ["get", "list"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["nodes", "pods"]
    verbs: ["get", "list"]
```

`helm/kube-seer/templates/clusterrolebinding.yaml`:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ include "kube-seer.fullname" . }}
subjects:
  - kind: ServiceAccount
    name: {{ include "kube-seer.fullname" . }}
    namespace: {{ .Release.Namespace }}
```

`helm/kube-seer/templates/pdb.yaml`:
```yaml
{{- if .Values.podDisruptionBudget.enabled }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
spec:
  minAvailable: {{ .Values.podDisruptionBudget.minAvailable }}
  selector:
    matchLabels:
      {{- include "kube-seer.selectorLabels" . | nindent 6 }}
{{- end }}
```

`helm/kube-seer/templates/servicemonitor.yaml`:
```yaml
{{- if .Values.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
spec:
  selector:
    matchLabels:
      {{- include "kube-seer.selectorLabels" . | nindent 6 }}
  endpoints:
    - port: http
      path: /metrics
      interval: {{ .Values.serviceMonitor.interval }}
{{- end }}
```

- [ ] **Step 4: Remove obsolete templates**

```bash
rm -f helm/kube-seer/templates/ingress.yaml helm/kube-seer/templates/hpa.yaml helm/kube-seer/templates/pvc.yaml
```

- [ ] **Step 5: Lint the chart**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && helm lint helm/kube-seer --set elasticsearch.url=http://es:9200`
Expected: "0 chart(s) failed" — lint passes.

- [ ] **Step 6: Commit**

```bash
git add helm/kube-seer/
git commit -m "feat: rewrite Helm chart for modular SRE agent v2"
```

---

## Task 13: Run full test suite and fix issues

**Files:**
- Potentially any file from tasks 1-11

- [ ] **Step 1: Run all tests**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 2: Run linting**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503`
Expected: No errors.

- [ ] **Step 3: Run type checking**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m mypy src/ --ignore-missing-imports`
Expected: No errors.

- [ ] **Step 4: Fix any issues found in steps 1-3 and re-run**

- [ ] **Step 5: Commit fixes if any**

```bash
git add -A
git commit -m "fix: resolve linting and type issues"
```

---

## Task 14: Clean up obsolete files

**Files:**
- Delete: `src/metrics_analyzer.py`
- Delete: `src/log_analyzer.py`
- Delete: `src/alerting.py`
- Delete: `demo.py`
- Delete: `helm/kube-seer/templates/rbac.yaml` (replaced by clusterrole.yaml + clusterrolebinding.yaml)
- Delete: `helm/kube-seer/examples/` (outdated)

- [ ] **Step 1: Remove obsolete source files**

```bash
cd /home/dams/Documents/Projets/Perso/kube-seer
rm -f src/metrics_analyzer.py src/log_analyzer.py src/alerting.py demo.py
rm -f helm/kube-seer/templates/rbac.yaml
rm -rf helm/kube-seer/examples/
```

- [ ] **Step 2: Verify tests still pass**

Run: `cd /home/dams/Documents/Projets/Perso/kube-seer && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove obsolete files from v1 architecture"
```

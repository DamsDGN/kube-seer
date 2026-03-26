# Phase 2 — Anomaly Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add anomaly detection to the SRE agent — Isolation Forest for metrics, TF-IDF + DBSCAN for logs, pattern matching for K8s events, and expose results via `/anomalies` API endpoint.

**Architecture:** Three analyzers (metrics, logs, events) each implement a `BaseAnalyzer` interface. The agent cycle becomes collect → analyze → store. Metrics analyzer uses Isolation Forest on collected node/pod data. Log analyzer queries ES for logs pushed by Fluentd, then clusters with TF-IDF + DBSCAN. Event analyzer detects known error patterns and frequency bursts. Anomalies are stored in ES (`sre-anomalies` index) and exposed via the API.

**Tech Stack:** scikit-learn (IsolationForest, TfidfVectorizer, DBSCAN), pandas, numpy, FastAPI

---

## File Structure

```
src/
├── analyzer/
│   ├── __init__.py
│   ├── base.py              # BaseAnalyzer abstract interface
│   ├── metrics.py           # Isolation Forest on node/pod metrics
│   ├── logs.py              # TF-IDF + DBSCAN on ES logs
│   └── events.py            # Pattern matching + frequency on K8s events
├── models.py                # Add: Anomaly, AnalysisResult
├── agent.py                 # Add: analyze step in cycle
└── api/
    └── routes.py            # Add: /anomalies, /anomalies/{id}, /analyze

tests/
├── analyzer/
│   ├── __init__.py
│   ├── test_metrics.py
│   ├── test_logs.py
│   └── test_events.py
├── test_models.py           # Add anomaly model tests
├── test_agent.py            # Add analyze cycle tests
└── test_api.py              # Add anomaly endpoint tests
```

---

## Task 1: Anomaly data models

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py`:
```python
from src.models import Anomaly, AnalysisResult, Severity


class TestAnomaly:
    def test_creation(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU usage anomaly detected",
            score=0.85,
            details={"cpu_usage_percent": 92.3},
            timestamp=sample_timestamp,
        )
        assert anomaly.anomaly_id == "a-001"
        assert anomaly.severity == Severity.WARNING
        assert anomaly.score == 0.85

    def test_to_dict(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled detected",
            score=1.0,
            details={},
            timestamp=sample_timestamp,
        )
        d = anomaly.model_dump()
        assert d["anomaly_id"] == "a-002"
        assert d["severity"] == 2  # CRITICAL = 2


class TestAnalysisResult:
    def test_creation(self, sample_timestamp):
        result = AnalysisResult(
            anomalies=[],
            analysis_timestamp=sample_timestamp,
            metrics_analyzed=10,
            logs_analyzed=50,
            events_analyzed=5,
        )
        assert result.anomalies == []
        assert result.metrics_analyzed == 10

    def test_with_anomalies(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="test",
            score=0.5,
            details={},
            timestamp=sample_timestamp,
        )
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=sample_timestamp,
            metrics_analyzed=1,
            logs_analyzed=0,
            events_analyzed=0,
        )
        assert len(result.anomalies) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v -k "Anomaly or AnalysisResult"`
Expected: FAIL — imports not found.

- [ ] **Step 3: Write the implementation**

Add to `src/models.py` after the `StoredRecord` class:
```python
class Anomaly(BaseModel):
    anomaly_id: str
    source: str  # "metrics", "logs", "events"
    severity: Severity
    resource_type: str  # "node", "pod", "event", "log"
    resource_name: str
    namespace: str = ""
    description: str
    score: float  # 0.0 to 1.0, higher = more anomalous
    details: Dict[str, Any] = {}
    timestamp: datetime


class AnalysisResult(BaseModel):
    anomalies: List[Anomaly]
    analysis_timestamp: datetime
    metrics_analyzed: int = 0
    logs_analyzed: int = 0
    events_analyzed: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: All tests PASS (existing 8 + new 4 = 12).

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Anomaly and AnalysisResult data models"
```

---

## Task 2: Analyzer base interface

**Files:**
- Create: `src/analyzer/__init__.py`
- Create: `src/analyzer/base.py`
- Create: `tests/analyzer/__init__.py`

- [ ] **Step 1: Create package files**

`src/analyzer/__init__.py`: empty file

`tests/analyzer/__init__.py`: empty file

- [ ] **Step 2: Write the base interface**

`src/analyzer/base.py`:
```python
from abc import ABC, abstractmethod
from typing import List

from src.models import Anomaly


class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, **kwargs) -> List[Anomaly]:
        """Run analysis and return detected anomalies."""

    @abstractmethod
    async def update_model(self, **kwargs) -> None:
        """Update the ML model with new data."""
```

- [ ] **Step 3: Commit**

```bash
git add src/analyzer/ tests/analyzer/__init__.py
git commit -m "feat: add analyzer base interface"
```

---

## Task 3: Metrics analyzer (Isolation Forest)

**Files:**
- Create: `tests/analyzer/test_metrics.py`
- Create: `src/analyzer/metrics.py`

- [ ] **Step 1: Write the failing tests**

`tests/analyzer/test_metrics.py`:
```python
import pytest
from datetime import datetime, timezone
from src.analyzer.metrics import MetricsAnalyzer
from src.config import Config
from src.models import NodeMetrics, PodMetrics, Anomaly, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        thresholds_cpu_warning=70.0,
        thresholds_cpu_critical=85.0,
        thresholds_memory_warning=70.0,
        thresholds_memory_critical=85.0,
        thresholds_disk_warning=80.0,
        thresholds_disk_critical=90.0,
    )


@pytest.fixture
def analyzer(config):
    return MetricsAnalyzer(config)


@pytest.fixture
def normal_node(sample_timestamp):
    return NodeMetrics(
        node_name="node-1",
        cpu_usage_percent=30.0,
        memory_usage_percent=40.0,
        disk_usage_percent=25.0,
        network_rx_bytes=1000,
        network_tx_bytes=500,
        conditions={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def high_cpu_node(sample_timestamp):
    return NodeMetrics(
        node_name="node-2",
        cpu_usage_percent=92.0,
        memory_usage_percent=40.0,
        disk_usage_percent=25.0,
        network_rx_bytes=1000,
        network_tx_bytes=500,
        conditions={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def normal_pod(sample_timestamp):
    return PodMetrics(
        pod_name="web-abc",
        namespace="default",
        node_name="node-1",
        cpu_usage_millicores=100,
        memory_usage_bytes=67108864,
        restart_count=0,
        status="Running",
        timestamp=sample_timestamp,
    )


@pytest.fixture
def crashing_pod(sample_timestamp):
    return PodMetrics(
        pod_name="worker-xyz",
        namespace="default",
        node_name="node-1",
        cpu_usage_millicores=50,
        memory_usage_bytes=67108864,
        restart_count=15,
        status="CrashLoopBackOff",
        timestamp=sample_timestamp,
    )


class TestMetricsAnalyzerThresholds:
    @pytest.mark.asyncio
    async def test_no_anomaly_normal_node(self, analyzer, normal_node):
        anomalies = await analyzer.analyze(
            node_metrics=[normal_node], pod_metrics=[]
        )
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detects_high_cpu_node(self, analyzer, high_cpu_node):
        anomalies = await analyzer.analyze(
            node_metrics=[high_cpu_node], pod_metrics=[]
        )
        cpu_anomalies = [a for a in anomalies if "CPU" in a.description]
        assert len(cpu_anomalies) >= 1
        assert cpu_anomalies[0].severity == Severity.CRITICAL
        assert cpu_anomalies[0].resource_name == "node-2"

    @pytest.mark.asyncio
    async def test_detects_crashing_pod(self, analyzer, crashing_pod):
        anomalies = await analyzer.analyze(
            node_metrics=[], pod_metrics=[crashing_pod]
        )
        restart_anomalies = [a for a in anomalies if "restart" in a.description.lower()]
        assert len(restart_anomalies) >= 1
        assert restart_anomalies[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_detects_crashloop_status(self, analyzer, crashing_pod):
        anomalies = await analyzer.analyze(
            node_metrics=[], pod_metrics=[crashing_pod]
        )
        status_anomalies = [a for a in anomalies if "CrashLoop" in a.description]
        assert len(status_anomalies) >= 1


class TestMetricsAnalyzerML:
    @pytest.mark.asyncio
    async def test_update_model_stores_data(self, analyzer, normal_node):
        await analyzer.update_model(node_metrics=[normal_node], pod_metrics=[])
        assert analyzer._node_samples_count > 0

    @pytest.mark.asyncio
    async def test_model_trains_after_enough_samples(self, analyzer, sample_timestamp):
        nodes = []
        for i in range(50):
            nodes.append(
                NodeMetrics(
                    node_name=f"node-{i}",
                    cpu_usage_percent=30.0 + (i % 10),
                    memory_usage_percent=40.0 + (i % 8),
                    disk_usage_percent=20.0,
                    network_rx_bytes=1000,
                    network_tx_bytes=500,
                    conditions={},
                    timestamp=sample_timestamp,
                )
            )
        await analyzer.update_model(node_metrics=nodes, pod_metrics=[])
        assert analyzer._node_model is not None

    @pytest.mark.asyncio
    async def test_empty_input_returns_no_anomalies(self, analyzer):
        anomalies = await analyzer.analyze(node_metrics=[], pod_metrics=[])
        assert anomalies == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analyzer/test_metrics.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/analyzer/metrics.py`:
```python
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import structlog
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, NodeMetrics, PodMetrics, Severity

logger = structlog.get_logger()

UNHEALTHY_STATUSES = {"CrashLoopBackOff", "Error", "ImagePullBackOff", "OOMKilled"}
HIGH_RESTART_THRESHOLD = 5


class MetricsAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config):
        self._config = config
        self._node_model: Optional[IsolationForest] = None
        self._node_scaler: Optional[StandardScaler] = None
        self._node_buffer: List[List[float]] = []
        self._node_samples_count = 0
        self._pod_model: Optional[IsolationForest] = None
        self._pod_scaler: Optional[StandardScaler] = None
        self._pod_buffer: List[List[float]] = []
        self._pod_samples_count = 0

    async def analyze(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_node_thresholds(node_metrics))
        anomalies.extend(self._check_pod_thresholds(pod_metrics))
        anomalies.extend(self._check_node_ml(node_metrics))
        anomalies.extend(self._check_pod_ml(pod_metrics))
        return anomalies

    async def update_model(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> None:
        for node in node_metrics:
            self._node_buffer.append(self._node_features(node))
            self._node_samples_count += 1

        for pod in pod_metrics:
            self._pod_buffer.append(self._pod_features(pod))
            self._pod_samples_count += 1

        window = self._config.ml_window_size
        if len(self._node_buffer) >= window:
            self._train_node_model()
        if len(self._pod_buffer) >= window:
            self._train_pod_model()

    # -- Threshold checks --

    def _check_node_thresholds(self, nodes: List[NodeMetrics]) -> List[Anomaly]:
        anomalies = []
        for node in nodes:
            anomalies.extend(self._check_metric(
                value=node.cpu_usage_percent,
                warning=self._config.thresholds_cpu_warning,
                critical=self._config.thresholds_cpu_critical,
                metric_name="CPU",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
            anomalies.extend(self._check_metric(
                value=node.memory_usage_percent,
                warning=self._config.thresholds_memory_warning,
                critical=self._config.thresholds_memory_critical,
                metric_name="Memory",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
            anomalies.extend(self._check_metric(
                value=node.disk_usage_percent,
                warning=self._config.thresholds_disk_warning,
                critical=self._config.thresholds_disk_critical,
                metric_name="Disk",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
        return anomalies

    def _check_pod_thresholds(self, pods: List[PodMetrics]) -> List[Anomaly]:
        anomalies = []
        for pod in pods:
            if pod.restart_count >= HIGH_RESTART_THRESHOLD:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics",
                    severity=Severity.CRITICAL,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"High restart count: {pod.restart_count}",
                    score=min(pod.restart_count / 20.0, 1.0),
                    details={
                        "restart_count": pod.restart_count,
                        "status": pod.status,
                    },
                    timestamp=pod.timestamp,
                ))
            if pod.status in UNHEALTHY_STATUSES:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics",
                    severity=Severity.CRITICAL,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"Unhealthy status: {pod.status}",
                    score=1.0,
                    details={"status": pod.status},
                    timestamp=pod.timestamp,
                ))
        return anomalies

    def _check_metric(
        self,
        value: float,
        warning: float,
        critical: float,
        metric_name: str,
        resource_type: str,
        resource_name: str,
        timestamp: datetime,
        namespace: str = "",
    ) -> List[Anomaly]:
        if value >= critical:
            return [Anomaly(
                anomaly_id=str(uuid.uuid4()),
                source="metrics",
                severity=Severity.CRITICAL,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                description=f"{metric_name} usage critical: {value:.1f}%",
                score=min(value / 100.0, 1.0),
                details={f"{metric_name.lower()}_usage_percent": value},
                timestamp=timestamp,
            )]
        if value >= warning:
            return [Anomaly(
                anomaly_id=str(uuid.uuid4()),
                source="metrics",
                severity=Severity.WARNING,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                description=f"{metric_name} usage warning: {value:.1f}%",
                score=value / 100.0,
                details={f"{metric_name.lower()}_usage_percent": value},
                timestamp=timestamp,
            )]
        return []

    # -- ML detection --

    def _node_features(self, node: NodeMetrics) -> List[float]:
        return [
            node.cpu_usage_percent,
            node.memory_usage_percent,
            node.disk_usage_percent,
            float(node.network_rx_bytes),
            float(node.network_tx_bytes),
        ]

    def _pod_features(self, pod: PodMetrics) -> List[float]:
        return [
            float(pod.cpu_usage_millicores),
            float(pod.memory_usage_bytes),
            float(pod.restart_count),
        ]

    def _train_node_model(self) -> None:
        data = np.array(self._node_buffer[-self._config.ml_window_size:])
        self._node_scaler = StandardScaler()
        scaled = self._node_scaler.fit_transform(data)
        self._node_model = IsolationForest(
            contamination=self._config.ml_anomaly_threshold,
            n_estimators=100,
            random_state=42,
        )
        self._node_model.fit(scaled)
        logger.info("metrics_analyzer.node_model_trained", samples=len(data))

    def _train_pod_model(self) -> None:
        data = np.array(self._pod_buffer[-self._config.ml_window_size:])
        self._pod_scaler = StandardScaler()
        scaled = self._pod_scaler.fit_transform(data)
        self._pod_model = IsolationForest(
            contamination=self._config.ml_anomaly_threshold,
            n_estimators=100,
            random_state=42,
        )
        self._pod_model.fit(scaled)
        logger.info("metrics_analyzer.pod_model_trained", samples=len(data))

    def _check_node_ml(self, nodes: List[NodeMetrics]) -> List[Anomaly]:
        if not self._node_model or not self._node_scaler or not nodes:
            return []
        anomalies = []
        features = np.array([self._node_features(n) for n in nodes])
        scaled = self._node_scaler.transform(features)
        predictions = self._node_model.predict(scaled)
        scores = self._node_model.decision_function(scaled)
        for i, node in enumerate(nodes):
            if predictions[i] == -1:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics_ml",
                    severity=Severity.WARNING,
                    resource_type="node",
                    resource_name=node.node_name,
                    namespace="",
                    description=f"ML anomaly detected on node {node.node_name}",
                    score=max(0.0, min(1.0, -scores[i])),
                    details={
                        "cpu": node.cpu_usage_percent,
                        "memory": node.memory_usage_percent,
                        "disk": node.disk_usage_percent,
                    },
                    timestamp=node.timestamp,
                ))
        return anomalies

    def _check_pod_ml(self, pods: List[PodMetrics]) -> List[Anomaly]:
        if not self._pod_model or not self._pod_scaler or not pods:
            return []
        anomalies = []
        features = np.array([self._pod_features(p) for p in pods])
        scaled = self._pod_scaler.transform(features)
        predictions = self._pod_model.predict(scaled)
        scores = self._pod_model.decision_function(scaled)
        for i, pod in enumerate(pods):
            if predictions[i] == -1:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics_ml",
                    severity=Severity.WARNING,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"ML anomaly detected on pod {pod.pod_name}",
                    score=max(0.0, min(1.0, -scores[i])),
                    details={
                        "cpu_millicores": pod.cpu_usage_millicores,
                        "memory_bytes": pod.memory_usage_bytes,
                        "restarts": pod.restart_count,
                    },
                    timestamp=pod.timestamp,
                ))
        return anomalies
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analyzer/test_metrics.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/ tests/analyzer/test_metrics.py
git commit -m "feat: add metrics analyzer with Isolation Forest"
```

---

## Task 4: Event analyzer (pattern matching + frequency)

**Files:**
- Create: `tests/analyzer/test_events.py`
- Create: `src/analyzer/events.py`

- [ ] **Step 1: Write the failing tests**

`tests/analyzer/test_events.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from src.analyzer.events import EventAnalyzer
from src.config import Config
from src.models import KubernetesEvent, Severity


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def analyzer(config):
    return EventAnalyzer(config)


@pytest.fixture
def oom_event(sample_timestamp):
    return KubernetesEvent(
        event_type="Warning",
        reason="OOMKilled",
        message="Container web killed due to OOM",
        involved_object_kind="Pod",
        involved_object_name="web-abc",
        involved_object_namespace="default",
        count=1,
        first_timestamp=sample_timestamp,
        last_timestamp=sample_timestamp,
    )


@pytest.fixture
def normal_event(sample_timestamp):
    return KubernetesEvent(
        event_type="Normal",
        reason="Scheduled",
        message="Successfully assigned pod",
        involved_object_kind="Pod",
        involved_object_name="web-abc",
        involved_object_namespace="default",
        count=1,
        first_timestamp=sample_timestamp,
        last_timestamp=sample_timestamp,
    )


class TestEventAnalyzerPatterns:
    @pytest.mark.asyncio
    async def test_detects_oom_killed(self, analyzer, oom_event):
        anomalies = await analyzer.analyze(events=[oom_event])
        assert len(anomalies) >= 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "OOMKilled" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_event(self, analyzer, normal_event):
        anomalies = await analyzer.analyze(events=[normal_event])
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detects_failed_scheduling(self, analyzer, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="FailedScheduling",
            message="0/3 nodes are available",
            involved_object_kind="Pod",
            involved_object_name="api-xyz",
            involved_object_namespace="production",
            count=5,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        anomalies = await analyzer.analyze(events=[event])
        assert len(anomalies) >= 1
        assert anomalies[0].resource_name == "api-xyz"

    @pytest.mark.asyncio
    async def test_detects_failed_mount(self, analyzer, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="FailedMount",
            message="Unable to attach volume",
            involved_object_kind="Pod",
            involved_object_name="db-0",
            involved_object_namespace="data",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        anomalies = await analyzer.analyze(events=[event])
        assert len(anomalies) >= 1


class TestEventAnalyzerFrequency:
    @pytest.mark.asyncio
    async def test_detects_event_burst(self, analyzer, sample_timestamp):
        events = []
        for i in range(20):
            events.append(KubernetesEvent(
                event_type="Warning",
                reason="BackOff",
                message=f"Back-off restarting failed container {i}",
                involved_object_kind="Pod",
                involved_object_name="worker-fail",
                involved_object_namespace="default",
                count=1,
                first_timestamp=sample_timestamp,
                last_timestamp=sample_timestamp,
            ))
        anomalies = await analyzer.analyze(events=events)
        burst_anomalies = [a for a in anomalies if "burst" in a.description.lower()]
        assert len(burst_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_empty_events(self, analyzer):
        anomalies = await analyzer.analyze(events=[])
        assert anomalies == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analyzer/test_events.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/analyzer/events.py`:
```python
import uuid
from collections import Counter
from typing import Dict, List, Set

import structlog

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, KubernetesEvent, Severity

logger = structlog.get_logger()

CRITICAL_REASONS: Dict[str, Severity] = {
    "OOMKilled": Severity.CRITICAL,
    "OOMKilling": Severity.CRITICAL,
    "CrashLoopBackOff": Severity.CRITICAL,
    "FailedMount": Severity.CRITICAL,
    "FailedAttachVolume": Severity.CRITICAL,
    "NodeNotReady": Severity.CRITICAL,
    "FailedScheduling": Severity.WARNING,
    "BackOff": Severity.WARNING,
    "Unhealthy": Severity.WARNING,
    "FailedCreate": Severity.WARNING,
    "FailedKillPod": Severity.WARNING,
    "Evicted": Severity.WARNING,
    "ImagePullBackOff": Severity.WARNING,
    "ErrImagePull": Severity.WARNING,
}

EVENT_BURST_THRESHOLD = 10


class EventAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config):
        self._config = config

    async def analyze(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_patterns(events))
        anomalies.extend(self._check_frequency(events))
        return anomalies

    async def update_model(self, **kwargs) -> None:
        pass  # Event analysis is rule-based, no model to update

    def _check_patterns(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        anomalies = []
        seen: Set[str] = set()
        for event in events:
            if event.reason in CRITICAL_REASONS:
                key = f"{event.reason}:{event.involved_object_namespace}/{event.involved_object_name}"
                if key in seen:
                    continue
                seen.add(key)
                severity = CRITICAL_REASONS[event.reason]
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="events",
                    severity=severity,
                    resource_type=event.involved_object_kind.lower(),
                    resource_name=event.involved_object_name,
                    namespace=event.involved_object_namespace,
                    description=f"{event.reason}: {event.message}",
                    score=1.0 if severity == Severity.CRITICAL else 0.7,
                    details={
                        "reason": event.reason,
                        "count": event.count,
                        "event_type": event.event_type,
                    },
                    timestamp=event.last_timestamp,
                ))
        return anomalies

    def _check_frequency(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        if not events:
            return []
        resource_counts: Counter = Counter()
        for event in events:
            if event.event_type == "Warning":
                key = f"{event.involved_object_namespace}/{event.involved_object_name}"
                resource_counts[key] += 1

        anomalies = []
        for resource_key, count in resource_counts.items():
            if count >= EVENT_BURST_THRESHOLD:
                namespace, name = resource_key.split("/", 1) if "/" in resource_key else ("", resource_key)
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="events",
                    severity=Severity.WARNING,
                    resource_type="pod",
                    resource_name=name,
                    namespace=namespace,
                    description=f"Event burst: {count} warning events",
                    score=min(count / 30.0, 1.0),
                    details={"warning_event_count": count},
                    timestamp=events[-1].last_timestamp,
                ))
        return anomalies
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analyzer/test_events.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/events.py tests/analyzer/test_events.py
git commit -m "feat: add event analyzer with pattern matching and frequency detection"
```

---

## Task 5: Log analyzer (TF-IDF + DBSCAN)

**Files:**
- Create: `tests/analyzer/test_logs.py`
- Create: `src/analyzer/logs.py`

- [ ] **Step 1: Write the failing tests**

`tests/analyzer/test_logs.py`:
```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.analyzer.logs import LogAnalyzer
from src.config import Config
from src.models import Severity
from src.storage.base import BaseStorage


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def mock_storage():
    storage = AsyncMock(spec=BaseStorage)
    return storage


@pytest.fixture
def analyzer(config, mock_storage):
    return LogAnalyzer(config, mock_storage)


@pytest.fixture
def error_logs():
    return [
        {
            "timestamp": "2026-01-15T10:30:00Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "ERROR: Connection refused to database at 10.0.0.5:5432",
        },
        {
            "timestamp": "2026-01-15T10:30:01Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "ERROR: Connection refused to database at 10.0.0.5:5432",
        },
        {
            "timestamp": "2026-01-15T10:30:02Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "FATAL: Out of memory - kill process 1234",
        },
    ]


@pytest.fixture
def normal_logs():
    return [
        {
            "timestamp": "2026-01-15T10:30:00Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "INFO: Request processed successfully in 45ms",
        },
    ]


class TestLogAnalyzerPatterns:
    @pytest.mark.asyncio
    async def test_detects_error_logs(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        anomalies = await analyzer.analyze()
        error_anomalies = [a for a in anomalies if a.source == "logs"]
        assert len(error_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_detects_oom_in_logs(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        anomalies = await analyzer.analyze()
        oom_anomalies = [
            a for a in anomalies
            if "memory" in a.description.lower() or "oom" in a.description.lower()
        ]
        assert len(oom_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_logs(self, analyzer, mock_storage, normal_logs):
        mock_storage.query = AsyncMock(return_value=normal_logs)
        anomalies = await analyzer.analyze()
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_empty_logs(self, analyzer, mock_storage):
        mock_storage.query = AsyncMock(return_value=[])
        anomalies = await analyzer.analyze()
        assert anomalies == []


class TestLogAnalyzerML:
    @pytest.mark.asyncio
    async def test_update_model(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        await analyzer.update_model()
        assert analyzer._log_count > 0

    @pytest.mark.asyncio
    async def test_clustering_with_enough_data(self, analyzer, mock_storage):
        logs = []
        for i in range(60):
            level = "ERROR" if i % 5 == 0 else "INFO"
            logs.append({
                "timestamp": f"2026-01-15T10:{i:02d}:00Z",
                "kubernetes": {"pod_name": f"pod-{i % 3}", "namespace_name": "default"},
                "log": f"{level}: Processing request {i} {'failed' if level == 'ERROR' else 'success'}",
            })
        mock_storage.query = AsyncMock(return_value=logs)
        await analyzer.update_model()
        assert analyzer._vectorizer is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analyzer/test_logs.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

`src/analyzer/logs.py`:
```python
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, Severity
from src.storage.base import BaseStorage

logger = structlog.get_logger()

ERROR_PATTERNS = {
    "oom": (
        re.compile(r"(out of memory|oom|killed process)", re.IGNORECASE),
        Severity.CRITICAL,
    ),
    "connection_refused": (
        re.compile(r"connection refused|ECONNREFUSED", re.IGNORECASE),
        Severity.WARNING,
    ),
    "disk_full": (
        re.compile(r"no space left on device|disk full", re.IGNORECASE),
        Severity.CRITICAL,
    ),
    "permission_denied": (
        re.compile(r"permission denied|EACCES|403 forbidden", re.IGNORECASE),
        Severity.WARNING,
    ),
    "timeout": (
        re.compile(r"timeout|timed out|deadline exceeded", re.IGNORECASE),
        Severity.WARNING,
    ),
    "crash": (
        re.compile(r"FATAL|panic|segfault|core dump", re.IGNORECASE),
        Severity.CRITICAL,
    ),
}

MIN_LOGS_FOR_CLUSTERING = 50


class LogAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config, storage: BaseStorage):
        self._config = config
        self._storage = storage
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._log_buffer: List[str] = []
        self._log_count = 0

    async def analyze(self) -> List[Anomaly]:
        logs = await self._fetch_logs()
        if not logs:
            return []
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_patterns(logs))
        return anomalies

    async def update_model(self, **kwargs) -> None:
        logs = await self._fetch_logs()
        if not logs:
            return
        messages = [log.get("log", "") for log in logs]
        self._log_buffer.extend(messages)
        self._log_count += len(messages)

        if len(self._log_buffer) >= MIN_LOGS_FOR_CLUSTERING:
            self._train_clustering_model()
            self._log_buffer = self._log_buffer[-self._config.ml_window_size:]

    async def _fetch_logs(self) -> List[Dict[str, Any]]:
        query = {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": "now-5m"}}},
                ],
                "should": [
                    {"match": {"log": "ERROR"}},
                    {"match": {"log": "FATAL"}},
                    {"match": {"log": "CRITICAL"}},
                    {"match": {"log": "WARN"}},
                    {"match": {"log": "Exception"}},
                ],
                "minimum_should_match": 1,
            }
        }
        try:
            return await self._storage.query(
                index=self._config.elasticsearch_indices_logs,
                query_body=query,
                size=500,
            )
        except Exception as e:
            logger.error("log_analyzer.fetch_error", error=str(e))
            return []

    def _check_patterns(self, logs: List[Dict[str, Any]]) -> List[Anomaly]:
        anomalies = []
        seen_patterns: Dict[str, int] = {}
        for log in logs:
            message = log.get("log", "")
            k8s = log.get("kubernetes", {})
            pod_name = k8s.get("pod_name", "unknown")
            namespace = k8s.get("namespace_name", "")

            for pattern_name, (pattern, severity) in ERROR_PATTERNS.items():
                if pattern.search(message):
                    key = f"{pattern_name}:{namespace}/{pod_name}"
                    seen_patterns[key] = seen_patterns.get(key, 0) + 1
                    if seen_patterns[key] == 1:
                        anomalies.append(Anomaly(
                            anomaly_id=str(uuid.uuid4()),
                            source="logs",
                            severity=severity,
                            resource_type="pod",
                            resource_name=pod_name,
                            namespace=namespace,
                            description=f"Log pattern '{pattern_name}' detected: {message[:200]}",
                            score=1.0 if severity == Severity.CRITICAL else 0.7,
                            details={
                                "pattern": pattern_name,
                                "sample_message": message[:500],
                            },
                            timestamp=datetime.now(timezone.utc),
                        ))
        return anomalies

    def _train_clustering_model(self) -> None:
        try:
            self._vectorizer = TfidfVectorizer(
                max_features=1000, ngram_range=(1, 2)
            )
            tfidf_matrix = self._vectorizer.fit_transform(self._log_buffer)
            clustering = DBSCAN(eps=0.5, min_samples=3, metric="cosine")
            clustering.fit(tfidf_matrix.toarray())
            n_clusters = len(set(clustering.labels_)) - (1 if -1 in clustering.labels_ else 0)
            logger.info(
                "log_analyzer.model_trained",
                samples=len(self._log_buffer),
                clusters=n_clusters,
            )
        except Exception as e:
            logger.error("log_analyzer.training_error", error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analyzer/test_logs.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/logs.py tests/analyzer/test_logs.py
git commit -m "feat: add log analyzer with TF-IDF clustering and pattern matching"
```

---

## Task 6: Integrate analyzers into agent cycle

**Files:**
- Modify: `src/agent.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agent.py`:
```python
from src.models import Anomaly, AnalysisResult, Severity


class TestSREAgentAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, agent, sample_timestamp):
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert isinstance(result, AnalysisResult)
        assert result.anomalies == []

    @pytest.mark.asyncio
    async def test_analyze_aggregates_anomalies(self, agent, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="test",
            score=0.5,
            details={},
            timestamp=sample_timestamp,
        )
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[anomaly])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert len(result.anomalies) == 1
        assert result.anomalies[0].anomaly_id == "a-001"


class TestSREAgentCycleWithAnalysis:
    @pytest.mark.asyncio
    async def test_run_cycle_includes_analyze(self, agent, sample_timestamp):
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

        await agent.run_cycle()
        agent.collect.assert_awaited_once()
        agent.analyze.assert_awaited_once()
        agent.store.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent.py -v`
Expected: FAIL — `analyze` method and `AnalysisResult` not found on agent.

- [ ] **Step 3: Write the implementation**

Modify `src/agent.py`:

Add imports at top:
```python
from src.analyzer.events import EventAnalyzer
from src.analyzer.logs import LogAnalyzer
from src.analyzer.metrics import MetricsAnalyzer
from src.models import AnalysisResult, Anomaly, CollectedData, StoredRecord
```

Add to `__init__` after storage init:
```python
        self._metrics_analyzer = MetricsAnalyzer(config)
        self._event_analyzer = EventAnalyzer(config)
        self._log_analyzer = LogAnalyzer(config, self._storage)
        self._last_analysis: Optional[AnalysisResult] = None
```

Add `analyze` method:
```python
    async def analyze(self, data: CollectedData) -> AnalysisResult:
        anomalies: List[Anomaly] = []
        try:
            metrics_anomalies = await self._metrics_analyzer.analyze(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
            anomalies.extend(metrics_anomalies)
        except Exception as e:
            logger.error("agent.metrics_analysis_error", error=str(e))

        try:
            event_anomalies = await self._event_analyzer.analyze(
                events=data.events,
            )
            anomalies.extend(event_anomalies)
        except Exception as e:
            logger.error("agent.event_analysis_error", error=str(e))

        try:
            log_anomalies = await self._log_analyzer.analyze()
            anomalies.extend(log_anomalies)
        except Exception as e:
            logger.error("agent.log_analysis_error", error=str(e))

        result = AnalysisResult(
            anomalies=anomalies,
            analysis_timestamp=data.collection_timestamp,
            metrics_analyzed=len(data.node_metrics) + len(data.pod_metrics),
            logs_analyzed=0,
            events_analyzed=len(data.events),
        )
        self._last_analysis = result
        logger.info("agent.analyzed", anomaly_count=len(anomalies))
        return result
```

Add `store_anomalies` method:
```python
    async def store_anomalies(self, result: AnalysisResult) -> None:
        if not result.anomalies:
            return
        index = self._config.elasticsearch_indices_anomalies
        records = [
            StoredRecord(
                record_type="anomaly",
                data=a.model_dump(),
                timestamp=a.timestamp,
            )
            for a in result.anomalies
        ]
        stored = await self._storage.store_bulk(index, records)
        logger.info("agent.anomalies_stored", count=stored)
```

Add `update_models` method:
```python
    async def update_models(self, data: CollectedData) -> None:
        try:
            await self._metrics_analyzer.update_model(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
        except Exception as e:
            logger.error("agent.model_update_error", error=str(e))
        try:
            await self._log_analyzer.update_model()
        except Exception as e:
            logger.error("agent.log_model_update_error", error=str(e))
```

Update `run_cycle`:
```python
    async def run_cycle(self) -> None:
        logger.info("agent.cycle_start")
        data = await self.collect()
        await self.store(data)
        result = await self.analyze(data)
        await self.store_anomalies(result)
        await self.update_models(data)
        logger.info("agent.cycle_end")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent.py -v`
Expected: All tests PASS (existing 5 + new 3 = 8).

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: integrate analyzers into agent collect-analyze-store cycle"
```

---

## Task 7: API anomaly endpoints

**Files:**
- Modify: `src/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:
```python
from src.models import Anomaly, AnalysisResult, Severity
from datetime import datetime, timezone


class TestAnomaliesEndpoint:
    @pytest.mark.asyncio
    async def test_anomalies_empty(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies")
        assert resp.status_code == 200
        assert resp.json()["anomalies"] == []

    @pytest.mark.asyncio
    async def test_anomalies_with_results(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[
            {
                "record_type": "anomaly",
                "data": {
                    "anomaly_id": "a-001",
                    "source": "metrics",
                    "severity": 1,
                    "resource_type": "node",
                    "resource_name": "node-1",
                    "namespace": "",
                    "description": "CPU high",
                    "score": 0.85,
                    "details": {},
                    "timestamp": "2026-01-15T10:30:00Z",
                },
                "timestamp": "2026-01-15T10:30:00Z",
                "cluster_name": "",
            }
        ])
        resp = await client.get("/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["data"]["anomaly_id"] == "a-001"

    @pytest.mark.asyncio
    async def test_anomalies_filter_severity(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies?severity=critical")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_anomalies_filter_namespace(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies?namespace=production")
        assert resp.status_code == 200


class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_trigger_manual_analysis(self, client, mock_agent):
        mock_agent.run_cycle = AsyncMock()
        mock_agent._last_analysis = AnalysisResult(
            anomalies=[],
            analysis_timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
            metrics_analyzed=5,
            events_analyzed=3,
        )
        resp = await client.post("/analyze")
        assert resp.status_code == 200
        mock_agent.run_cycle.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v -k "Anomal or Analyze"`
Expected: FAIL — endpoints not found.

- [ ] **Step 3: Write the implementation**

Add to `src/api/routes.py` inside `create_app()`, before `return app`:

```python
    @app.get("/anomalies")
    async def get_anomalies(
        severity: str = "",
        namespace: str = "",
        limit: int = 100,
    ):
        query_parts: list = [{"match": {"record_type": "anomaly"}}]
        if severity:
            severity_map = {"info": 0, "warning": 1, "critical": 2}
            sev_val = severity_map.get(severity.lower())
            if sev_val is not None:
                query_parts.append({"match": {"data.severity": sev_val}})
        if namespace:
            query_parts.append({"match": {"data.namespace": namespace}})

        query_body = {"bool": {"must": query_parts}}
        results = await agent._storage.query(
            index=config.elasticsearch_indices_anomalies,
            query_body=query_body,
            size=limit,
        )
        return {"anomalies": results, "count": len(results)}

    @app.post("/analyze")
    async def trigger_analysis():
        await agent.run_cycle()
        result = agent._last_analysis
        if result:
            return {
                "status": "completed",
                "anomalies_found": len(result.anomalies),
                "metrics_analyzed": result.metrics_analyzed,
                "events_analyzed": result.events_analyzed,
                "timestamp": result.analysis_timestamp.isoformat(),
            }
        return {"status": "completed", "anomalies_found": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: All tests PASS (existing 5 + new 5 = 10).

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat: add /anomalies and /analyze API endpoints"
```

---

## Task 8: Full test suite + linting

**Files:**
- Potentially any file

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 2: Run linting**

Run: `python -m flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503`

- [ ] **Step 3: Run type checking**

Run: `python -m mypy src/ --ignore-missing-imports`

- [ ] **Step 4: Fix any issues found**

- [ ] **Step 5: Commit fixes if any**

```bash
git add -A
git commit -m "fix: resolve linting and type issues for Phase 2"
```

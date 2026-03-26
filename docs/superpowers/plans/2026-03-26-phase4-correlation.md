# Phase 4 — Correlation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add temporal and topological correlation to link related anomalies into incidents with an aggregated severity score.

**Architecture:** A `Correlator` receives the flat list of anomalies from all analyzers and groups them into `Incident` objects. Temporal correlation groups anomalies close in time on the same or related resources. Topological correlation uses K8s relationships (pod → node, pod → PVC, deployment → HPA). Each incident gets an aggregated severity (highest among correlated anomalies) and a combined score.

**Tech Stack:** Python (no new dependencies)

---

## File Structure

```
src/
├── analyzer/
│   └── correlator.py        # Correlator: temporal + topological grouping
├── models.py                # Add: Incident model
├── agent.py                 # Add: correlation step after analyze
└── api/
    └── routes.py            # Modify: /anomalies/{id} with correlations

tests/
├── analyzer/
│   └── test_correlator.py
├── test_models.py           # Add Incident tests
├── test_agent.py            # Add correlation cycle tests
└── test_api.py              # Add anomaly detail tests
```

---

## Task 1: Incident data model

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py`:
```python
from src.models import Incident


class TestIncident:
    def test_creation(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        incident = Incident(
            incident_id="inc-001",
            anomalies=[anomaly],
            severity=Severity.WARNING,
            score=0.7,
            description="CPU warning on node-1",
            resources=["node/node-1"],
            timestamp=sample_timestamp,
        )
        assert incident.incident_id == "inc-001"
        assert len(incident.anomalies) == 1
        assert incident.severity == Severity.WARNING

    def test_multi_anomaly_incident(self, sample_timestamp):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="Memory warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled",
            score=1.0,
            details={},
            timestamp=sample_timestamp,
        )
        incident = Incident(
            incident_id="inc-002",
            anomalies=[a1, a2],
            severity=Severity.CRITICAL,
            score=1.0,
            description="Correlated: Memory warning + OOMKilled",
            resources=["node/node-1", "default/pod/web-abc"],
            timestamp=sample_timestamp,
        )
        assert incident.severity == Severity.CRITICAL
        assert len(incident.resources) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v -k "Incident"`

- [ ] **Step 3: Write the implementation**

Add to `src/models.py` after `AnalysisResult`:
```python
class Incident(BaseModel):
    incident_id: str
    anomalies: List[Anomaly]
    severity: Severity
    score: float
    description: str
    resources: List[str]
    timestamp: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Incident data model"
```

---

## Task 2: Correlator

**Files:**
- Create: `tests/analyzer/test_correlator.py`
- Create: `src/analyzer/correlator.py`

- [ ] **Step 1: Write the failing tests**

`tests/analyzer/test_correlator.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta

from src.analyzer.correlator import Correlator
from src.config import Config
from src.models import (
    Anomaly,
    CollectedData,
    Incident,
    NodeMetrics,
    PodMetrics,
    ResourceState,
    Severity,
)


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def correlator(config):
    return Correlator(config)


@pytest.fixture
def ts():
    return datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


class TestTemporalCorrelation:
    @pytest.mark.asyncio
    async def test_groups_same_resource_anomalies(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="metrics",
            severity=Severity.CRITICAL,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="Memory critical",
            score=0.9,
            details={},
            timestamp=ts + timedelta(seconds=30),
        )
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(
            anomalies=[a1, a2], data=data
        )
        assert len(incidents) == 1
        assert len(incidents[0].anomalies) == 2
        assert incidents[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_separate_resources_separate_incidents(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-2",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(
            anomalies=[a1, a2], data=data
        )
        assert len(incidents) == 2

    @pytest.mark.asyncio
    async def test_empty_anomalies(self, correlator, ts):
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[], data=data)
        assert incidents == []


class TestTopologicalCorrelation:
    @pytest.mark.asyncio
    async def test_correlates_pod_with_node(self, correlator, ts):
        a_node = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="Memory warning on node",
            score=0.7,
            details={},
            timestamp=ts,
        )
        a_pod = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled",
            score=1.0,
            details={},
            timestamp=ts + timedelta(seconds=10),
        )
        pod = PodMetrics(
            pod_name="web-abc",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=200,
            memory_usage_bytes=1000000,
            restart_count=0,
            status="Running",
            timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[pod],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(
            anomalies=[a_node, a_pod], data=data
        )
        assert len(incidents) == 1
        assert len(incidents[0].anomalies) == 2
        assert incidents[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_no_topology_link_separate_incidents(self, correlator, ts):
        a_node = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=ts,
        )
        a_pod = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled",
            score=1.0,
            details={},
            timestamp=ts,
        )
        pod_on_other_node = PodMetrics(
            pod_name="web-abc",
            namespace="default",
            node_name="node-2",
            cpu_usage_millicores=200,
            memory_usage_bytes=1000000,
            restart_count=0,
            status="Running",
            timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[pod_on_other_node],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(
            anomalies=[a_node, a_pod], data=data
        )
        assert len(incidents) == 2


class TestIncidentScoring:
    @pytest.mark.asyncio
    async def test_incident_score_is_max(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="metrics",
            severity=Severity.CRITICAL,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="Memory critical",
            score=0.95,
            details={},
            timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(
            anomalies=[a1, a2], data=data
        )
        assert incidents[0].score == 0.95
        assert incidents[0].severity == Severity.CRITICAL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analyzer/test_correlator.py -v`

- [ ] **Step 3: Write the implementation**

`src/analyzer/correlator.py`:
```python
import uuid
from typing import Dict, List, Set, Tuple

import structlog

from src.config import Config
from src.models import Anomaly, CollectedData, Incident, Severity

logger = structlog.get_logger()

TEMPORAL_WINDOW_SECONDS = 300


class Correlator:
    def __init__(self, config: Config):
        self._config = config

    async def correlate(
        self, anomalies: List[Anomaly], data: CollectedData
    ) -> List[Incident]:
        if not anomalies:
            return []

        pod_to_node = self._build_pod_node_map(data)
        groups = self._group_anomalies(anomalies, pod_to_node)
        incidents = self._build_incidents(groups)

        logger.info(
            "correlator.done",
            anomalies=len(anomalies),
            incidents=len(incidents),
        )
        return incidents

    def _build_pod_node_map(self, data: CollectedData) -> Dict[str, str]:
        """Map (namespace/pod_name) -> node_name."""
        pod_to_node: Dict[str, str] = {}
        for pod in data.pod_metrics:
            if pod.node_name:
                key = f"{pod.namespace}/{pod.pod_name}"
                pod_to_node[key] = pod.node_name
        return pod_to_node

    def _resource_key(self, anomaly: Anomaly) -> str:
        if anomaly.namespace:
            return f"{anomaly.namespace}/{anomaly.resource_type}/{anomaly.resource_name}"
        return f"{anomaly.resource_type}/{anomaly.resource_name}"

    def _get_node_for_anomaly(
        self, anomaly: Anomaly, pod_to_node: Dict[str, str]
    ) -> str:
        if anomaly.resource_type == "node":
            return anomaly.resource_name
        if anomaly.resource_type == "pod":
            pod_key = f"{anomaly.namespace}/{anomaly.resource_name}"
            return pod_to_node.get(pod_key, "")
        return ""

    def _group_anomalies(
        self,
        anomalies: List[Anomaly],
        pod_to_node: Dict[str, str],
    ) -> List[List[Anomaly]]:
        # Build adjacency: anomaly index -> set of related anomaly indices
        n = len(anomalies)
        related: Dict[int, Set[int]] = {i: set() for i in range(n)}

        for i in range(n):
            for j in range(i + 1, n):
                if self._are_related(anomalies[i], anomalies[j], pod_to_node):
                    related[i].add(j)
                    related[j].add(i)

        # Union-find to build connected components
        visited: Set[int] = set()
        groups: List[List[Anomaly]] = []

        for i in range(n):
            if i in visited:
                continue
            group_indices: List[int] = []
            stack = [i]
            while stack:
                idx = stack.pop()
                if idx in visited:
                    continue
                visited.add(idx)
                group_indices.append(idx)
                stack.extend(related[idx] - visited)
            groups.append([anomalies[idx] for idx in group_indices])

        return groups

    def _are_related(
        self,
        a: Anomaly,
        b: Anomaly,
        pod_to_node: Dict[str, str],
    ) -> bool:
        # Temporal check: must be within window
        time_diff = abs(
            (a.timestamp - b.timestamp).total_seconds()
        )
        if time_diff > TEMPORAL_WINDOW_SECONDS:
            return False

        # Same resource
        if self._resource_key(a) == self._resource_key(b):
            return True

        # Topological: pod on same node
        node_a = self._get_node_for_anomaly(a, pod_to_node)
        node_b = self._get_node_for_anomaly(b, pod_to_node)
        if node_a and node_b and node_a == node_b:
            return True

        return False

    def _build_incidents(
        self, groups: List[List[Anomaly]]
    ) -> List[Incident]:
        incidents = []
        for group in groups:
            max_severity = max(a.severity for a in group)
            max_score = max(a.score for a in group)
            resources = list(
                {self._resource_key(a) for a in group}
            )
            descriptions = [a.description for a in group]
            if len(group) == 1:
                desc = descriptions[0]
            else:
                desc = "Correlated: " + " + ".join(
                    d[:50] for d in descriptions[:3]
                )
                if len(descriptions) > 3:
                    desc += f" (+{len(descriptions) - 3} more)"

            earliest = min(a.timestamp for a in group)
            incidents.append(
                Incident(
                    incident_id=str(uuid.uuid4()),
                    anomalies=group,
                    severity=Severity(max_severity),
                    score=max_score,
                    description=desc,
                    resources=resources,
                    timestamp=earliest,
                )
            )
        return incidents
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analyzer/test_correlator.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/correlator.py tests/analyzer/test_correlator.py
git commit -m "feat: add correlator with temporal and topological grouping"
```

---

## Task 3: Integrate correlator into agent

**Files:**
- Modify: `src/agent.py`
- Modify: `src/models.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Add incidents to AnalysisResult**

In `src/models.py`, modify `AnalysisResult` to add an incidents field:
```python
class AnalysisResult(BaseModel):
    anomalies: List[Anomaly]
    incidents: List["Incident"] = []
    analysis_timestamp: datetime
    metrics_analyzed: int = 0
    logs_analyzed: int = 0
    events_analyzed: int = 0
```

Note: `Incident` is defined after `AnalysisResult` in the file, so use a forward reference string `"Incident"` and add `model_rebuild()` at the bottom of models.py:
```python
AnalysisResult.model_rebuild()
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_agent.py`:
```python
from src.models import Incident


class TestSREAgentCorrelation:
    @pytest.mark.asyncio
    async def test_analyze_includes_correlation(self, agent, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
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
        assert len(result.incidents) >= 1
        assert result.incidents[0].anomalies[0].anomaly_id == "a-001"
```

- [ ] **Step 3: Modify `src/agent.py`**

Read the file first, then:

Add import:
```python
from src.analyzer.correlator import Correlator
```

In `__init__`, after `self._log_analyzer`, add:
```python
        self._correlator = Correlator(config)
```

In `analyze()`, after aggregating all anomalies and before building `AnalysisResult`, add:
```python
        try:
            incidents = await self._correlator.correlate(
                anomalies=anomalies, data=data
            )
        except Exception as e:
            logger.error("agent.correlation_error", error=str(e))
            incidents = []
```

Update the `AnalysisResult` construction to include incidents:
```python
        result = AnalysisResult(
            anomalies=anomalies,
            incidents=incidents,
            analysis_timestamp=data.collection_timestamp,
            metrics_analyzed=len(data.node_metrics) + len(data.pod_metrics),
            logs_analyzed=0,
            events_analyzed=len(data.events),
        )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_agent.py tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/models.py src/agent.py tests/test_agent.py
git commit -m "feat: integrate correlator into agent analysis pipeline"
```

---

## Task 4: API anomaly detail with correlations

**Files:**
- Modify: `src/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:
```python
class TestIncidentsEndpoint:
    @pytest.mark.asyncio
    async def test_incidents_from_last_analysis(self, client, mock_agent):
        mock_agent._last_analysis = AnalysisResult(
            anomalies=[],
            incidents=[],
            analysis_timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        )
        resp = await client.get("/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incidents"] == []

    @pytest.mark.asyncio
    async def test_incidents_no_analysis_yet(self, client, mock_agent):
        mock_agent._last_analysis = None
        resp = await client.get("/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incidents"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add endpoint**

Add to `src/api/routes.py` inside `create_app()`, before `return app`:
```python
    @app.get("/incidents")
    async def get_incidents():
        if agent._last_analysis and agent._last_analysis.incidents:
            return {
                "incidents": [
                    inc.model_dump() for inc in agent._last_analysis.incidents
                ],
                "count": len(agent._last_analysis.incidents),
            }
        return {"incidents": [], "count": 0}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat: add /incidents API endpoint"
```

---

## Task 5: Full test suite + linting + black

**Files:**
- Potentially any file

- [ ] **Step 1: Run black**

Run: `black src/ tests/`

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 3: Run linting**

Run: `python -m flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503`

- [ ] **Step 4: Run type checking**

Run: `python -m mypy src/ --ignore-missing-imports`

- [ ] **Step 5: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: apply black formatting and resolve linting issues for Phase 4"
```

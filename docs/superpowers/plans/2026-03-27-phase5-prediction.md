# Phase 5 — Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trend-based prediction to the SRE agent — detect resource exhaustion trends (disk, memory, CPU) and generate predictive alerts with estimated time-to-saturation.

**Architecture:** A `Predictor` stores historical metric snapshots in a rolling buffer, fits linear regression on trends, and generates `Prediction` objects when a metric is projected to hit a threshold within a configurable horizon. Predictions are stored in ES (`sre-anomalies` index as record_type=prediction) and exposed via `/predictions` API endpoint.

**Tech Stack:** numpy (linear regression), Python (no new dependencies)

---

## File Structure

```
src/
├── analyzer/
│   └── predictor.py         # Trend regression + time-to-saturation
├── models.py                # Add: Prediction model
├── agent.py                 # Add: prediction step in cycle
└── api/
    └── routes.py            # Add: /predictions endpoint

tests/
├── analyzer/
│   └── test_predictor.py
├── test_models.py           # Add Prediction tests
├── test_agent.py            # Add prediction cycle tests
└── test_api.py              # Add predictions endpoint tests
```

---

## Task 1: Prediction data model

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py`:
```python
from src.models import Prediction


class TestPrediction:
    def test_creation(self, sample_timestamp):
        pred = Prediction(
            prediction_id="p-001",
            resource_type="node",
            resource_name="node-1",
            namespace="",
            metric_name="disk_usage_percent",
            current_value=82.0,
            predicted_value=100.0,
            threshold=90.0,
            hours_to_threshold=48.5,
            confidence=0.92,
            trend_per_hour=0.165,
            description="Disk saturation estimated in 48h",
            timestamp=sample_timestamp,
        )
        assert pred.prediction_id == "p-001"
        assert pred.hours_to_threshold == 48.5
        assert pred.confidence == 0.92

    def test_to_dict(self, sample_timestamp):
        pred = Prediction(
            prediction_id="p-002",
            resource_type="pod",
            resource_name="db-0",
            namespace="data",
            metric_name="memory_usage_percent",
            current_value=75.0,
            predicted_value=90.0,
            threshold=85.0,
            hours_to_threshold=24.0,
            confidence=0.85,
            trend_per_hour=0.42,
            description="Memory threshold in 24h",
            timestamp=sample_timestamp,
        )
        d = pred.model_dump()
        assert d["metric_name"] == "memory_usage_percent"
        assert d["namespace"] == "data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v -k "Prediction"`

- [ ] **Step 3: Write the implementation**

Add to `src/models.py` after `Incident`:
```python
class Prediction(BaseModel):
    prediction_id: str
    resource_type: str
    resource_name: str
    namespace: str = ""
    metric_name: str
    current_value: float
    predicted_value: float
    threshold: float
    hours_to_threshold: float
    confidence: float
    trend_per_hour: float
    description: str
    timestamp: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Prediction data model"
```

---

## Task 2: Predictor

**Files:**
- Create: `tests/analyzer/test_predictor.py`
- Create: `src/analyzer/predictor.py`

- [ ] **Step 1: Write the failing tests**

`tests/analyzer/test_predictor.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta

from src.analyzer.predictor import Predictor
from src.config import Config
from src.models import NodeMetrics, PodMetrics, Prediction


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        thresholds_cpu_critical=85.0,
        thresholds_memory_critical=85.0,
        thresholds_disk_critical=90.0,
    )


@pytest.fixture
def predictor(config):
    return Predictor(config)


def make_node(name, cpu, memory, disk, ts):
    return NodeMetrics(
        node_name=name,
        cpu_usage_percent=cpu,
        memory_usage_percent=memory,
        disk_usage_percent=disk,
        network_rx_bytes=0,
        network_tx_bytes=0,
        conditions={},
        timestamp=ts,
    )


class TestPredictorTrend:
    @pytest.mark.asyncio
    async def test_no_prediction_without_history(self, predictor):
        ts = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        node = make_node("node-1", 50.0, 50.0, 50.0, ts)
        predictions = await predictor.predict(node_metrics=[node], pod_metrics=[])
        assert predictions == []

    @pytest.mark.asyncio
    async def test_predicts_rising_disk(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 70.0 + i * 2.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 90.0, ts)
        await predictor.update(node_metrics=[node], pod_metrics=[])

        predictions = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        disk_preds = [p for p in predictions if p.metric_name == "disk_usage_percent"]
        assert len(disk_preds) >= 1
        assert disk_preds[0].hours_to_threshold > 0
        assert disk_preds[0].trend_per_hour > 0

    @pytest.mark.asyncio
    async def test_no_prediction_stable_metrics(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 30.0, 30.0, 30.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 30.0, 30.0, 30.0, ts)
        predictions = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        assert predictions == []

    @pytest.mark.asyncio
    async def test_no_prediction_decreasing_trend(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 80.0 - i * 2.0, 50.0, 50.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 60.0, 50.0, 50.0, ts)
        predictions = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        cpu_preds = [p for p in predictions if p.metric_name == "cpu_usage_percent"]
        assert cpu_preds == []


class TestPredictorConfidence:
    @pytest.mark.asyncio
    async def test_confidence_from_r_squared(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 70.0 + i * 2.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 90.0, ts)
        await predictor.update(node_metrics=[node], pod_metrics=[])

        predictions = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        if predictions:
            assert 0.0 <= predictions[0].confidence <= 1.0


class TestPredictorHorizon:
    @pytest.mark.asyncio
    async def test_ignores_far_future_predictions(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 50.0 + i * 0.1, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 51.0, ts)
        predictions = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        for p in predictions:
            assert p.hours_to_threshold <= 168
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analyzer/test_predictor.py -v`

- [ ] **Step 3: Write the implementation**

`src/analyzer/predictor.py`:
```python
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
import structlog

from src.config import Config
from src.models import NodeMetrics, PodMetrics, Prediction

logger = structlog.get_logger()

PREDICTION_HORIZON_HOURS = 168  # 7 days
MIN_SAMPLES_FOR_PREDICTION = 5


class Predictor:
    def __init__(self, config: Config):
        self._config = config
        # resource_key -> metric_name -> list of (timestamp_hours, value)
        self._history: Dict[str, Dict[str, List[Tuple[float, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._max_history = config.ml_window_size

    async def update(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> None:
        for node in node_metrics:
            key = f"node/{node.node_name}"
            ts_h = node.timestamp.timestamp() / 3600.0
            self._append(key, "cpu_usage_percent", ts_h, node.cpu_usage_percent)
            self._append(key, "memory_usage_percent", ts_h, node.memory_usage_percent)
            self._append(key, "disk_usage_percent", ts_h, node.disk_usage_percent)

        for pod in pod_metrics:
            key = f"{pod.namespace}/pod/{pod.pod_name}"
            ts_h = pod.timestamp.timestamp() / 3600.0
            self._append(
                key,
                "cpu_millicores",
                ts_h,
                float(pod.cpu_usage_millicores),
            )
            self._append(
                key,
                "memory_bytes",
                ts_h,
                float(pod.memory_usage_bytes),
            )

    async def predict(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> List[Prediction]:
        predictions: List[Prediction] = []

        thresholds = {
            "cpu_usage_percent": self._config.thresholds_cpu_critical,
            "memory_usage_percent": self._config.thresholds_memory_critical,
            "disk_usage_percent": self._config.thresholds_disk_critical,
        }

        for node in node_metrics:
            key = f"node/{node.node_name}"
            for metric_name, threshold in thresholds.items():
                current = getattr(node, metric_name)
                pred = self._predict_metric(
                    key=key,
                    metric_name=metric_name,
                    current_value=current,
                    threshold=threshold,
                    resource_type="node",
                    resource_name=node.node_name,
                    namespace="",
                    timestamp=node.timestamp,
                )
                if pred:
                    predictions.append(pred)

        return predictions

    def _append(
        self, key: str, metric: str, ts_h: float, value: float
    ) -> None:
        buf = self._history[key][metric]
        buf.append((ts_h, value))
        if len(buf) > self._max_history:
            self._history[key][metric] = buf[-self._max_history:]

    def _predict_metric(
        self,
        key: str,
        metric_name: str,
        current_value: float,
        threshold: float,
        resource_type: str,
        resource_name: str,
        namespace: str,
        timestamp: datetime,
    ) -> Prediction | None:
        buf = self._history.get(key, {}).get(metric_name, [])
        if len(buf) < MIN_SAMPLES_FOR_PREDICTION:
            return None

        times = np.array([t for t, _ in buf])
        values = np.array([v for _, v in buf])

        # Normalize times to start at 0
        t0 = times[0]
        times_norm = times - t0

        # Linear regression
        slope, intercept, r_squared = self._linear_regression(
            times_norm, values
        )

        # Only predict if trend is positive and meaningful
        if slope <= 0:
            return None

        # Already above threshold
        if current_value >= threshold:
            return None

        # Time to threshold from now
        current_t = times_norm[-1]
        threshold_t = (threshold - intercept) / slope
        hours_to_threshold = threshold_t - current_t

        if hours_to_threshold <= 0 or hours_to_threshold > PREDICTION_HORIZON_HOURS:
            return None

        predicted_value = min(intercept + slope * (current_t + hours_to_threshold), 100.0)

        return Prediction(
            prediction_id=str(uuid.uuid4()),
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            metric_name=metric_name,
            current_value=current_value,
            predicted_value=predicted_value,
            threshold=threshold,
            hours_to_threshold=round(hours_to_threshold, 1),
            confidence=round(max(0.0, min(1.0, r_squared)), 2),
            trend_per_hour=round(slope, 4),
            description=(
                f"{metric_name} on {resource_type}/{resource_name}: "
                f"estimated to reach {threshold}% in {hours_to_threshold:.0f}h "
                f"(current: {current_value:.1f}%, trend: +{slope:.2f}%/h)"
            ),
            timestamp=timestamp,
        )

    def _linear_regression(
        self, x: np.ndarray, y: np.ndarray
    ) -> Tuple[float, float, float]:
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)

        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-10:
            return 0.0, float(np.mean(y)), 0.0

        slope = float((n * sum_xy - sum_x * sum_y) / denom)
        intercept = float((sum_y - slope * sum_x) / n)

        # R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return slope, intercept, r_squared
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analyzer/test_predictor.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/predictor.py tests/analyzer/test_predictor.py
git commit -m "feat: add predictor with trend regression and time-to-saturation"
```

---

## Task 3: Integrate predictor into agent + add predictions to AnalysisResult

**Files:**
- Modify: `src/models.py`
- Modify: `src/agent.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Add predictions to AnalysisResult**

Modify `AnalysisResult` in `src/models.py`:
```python
class AnalysisResult(BaseModel):
    anomalies: List[Anomaly]
    incidents: List["Incident"] = []
    predictions: List["Prediction"] = []
    analysis_timestamp: datetime
    metrics_analyzed: int = 0
    logs_analyzed: int = 0
    events_analyzed: int = 0
```

Update `model_rebuild()` at the bottom (it should already be there).

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_agent.py`:
```python
class TestSREAgentPrediction:
    @pytest.mark.asyncio
    async def test_run_cycle_includes_predictions(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[], pod_metrics=[], events=[], resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.analyze = AsyncMock(
            return_value=AnalysisResult(
                anomalies=[], incidents=[], predictions=[],
                analysis_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()
        agent.store_anomalies = AsyncMock()
        agent.update_models = AsyncMock()
        agent._alerter = AsyncMock()
        agent._alerter.send_alerts = AsyncMock()

        await agent.run_cycle()
        agent.analyze.assert_awaited_once()
```

- [ ] **Step 3: Modify `src/agent.py`**

Read the file first, then:

Add import: `from src.analyzer.predictor import Predictor`

In `__init__`, after `self._correlator`, add:
```python
        self._predictor = Predictor(config)
```

In `analyze()`, after the correlator call and before building `AnalysisResult`, add:
```python
        try:
            predictions = await self._predictor.predict(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
        except Exception as e:
            logger.error("agent.prediction_error", error=str(e))
            predictions = []
```

Update `AnalysisResult` construction to include `predictions=predictions`.

In `update_models()`, after the log model update, add:
```python
        try:
            await self._predictor.update(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
        except Exception as e:
            logger.error("agent.predictor_update_error", error=str(e))
```

Also in `store_anomalies()`, add prediction storage after anomaly storage:
```python
        if result.predictions:
            pred_records = [
                StoredRecord(
                    record_type="prediction",
                    data=p.model_dump(),
                    timestamp=p.timestamp,
                )
                for p in result.predictions
            ]
            stored = await self._storage.store_bulk(index, pred_records)
            logger.info("agent.predictions_stored", count=stored)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_agent.py tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/models.py src/agent.py tests/test_agent.py
git commit -m "feat: integrate predictor into agent pipeline"
```

---

## Task 4: /predictions API endpoint

**Files:**
- Modify: `src/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:
```python
class TestPredictionsEndpoint:
    @pytest.mark.asyncio
    async def test_predictions_from_last_analysis(self, client, mock_agent):
        mock_agent._last_analysis = AnalysisResult(
            anomalies=[], incidents=[], predictions=[],
            analysis_timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        )
        resp = await client.get("/predictions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["predictions"] == []

    @pytest.mark.asyncio
    async def test_predictions_no_analysis_yet(self, client, mock_agent):
        mock_agent._last_analysis = None
        resp = await client.get("/predictions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["predictions"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add endpoint**

Add to `src/api/routes.py` inside `create_app()`, before `return app`:
```python
    @app.get("/predictions")
    async def get_predictions():
        if agent._last_analysis and agent._last_analysis.predictions:
            return {
                "predictions": [
                    p.model_dump() for p in agent._last_analysis.predictions
                ],
                "count": len(agent._last_analysis.predictions),
            }
        return {"predictions": [], "count": 0}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat: add /predictions API endpoint"
```

---

## Task 5: Black + tests + linting

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
git commit -m "fix: apply black formatting and resolve linting issues for Phase 5"
```

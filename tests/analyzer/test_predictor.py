import pytest
from datetime import datetime, timezone, timedelta

from src.analyzer.predictor import Predictor
from src.config import Config
from src.models import NodeMetrics, PodMetrics


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
        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
        assert predictions == []

    @pytest.mark.asyncio
    async def test_predicts_rising_disk(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 70.0 + i * 2.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])

        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 88.0, ts)
        await predictor.update(node_metrics=[node], pod_metrics=[])

        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
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
        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
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
        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
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
        node = make_node("node-1", 50.0, 50.0, 88.0, ts)
        await predictor.update(node_metrics=[node], pod_metrics=[])

        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
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
        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
        for p in predictions:
            assert p.hours_to_threshold <= 168


class TestPredictorConfigurableHorizon:
    @pytest.mark.asyncio
    async def test_custom_horizon_respected(self):
        from src.config import Config

        cfg = Config(
            elasticsearch_url="http://localhost:9200",
            prediction_horizon_hours=24,
            thresholds_cpu_critical=85.0,
            thresholds_memory_critical=85.0,
            thresholds_disk_critical=90.0,
        )
        predictor = Predictor(cfg)
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        # Slow rise: would reach threshold in ~200h (beyond 24h horizon)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 50.0 + i * 0.1, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])
        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 51.0, ts)
        predictions, _ = await predictor.predict(node_metrics=[node], pod_metrics=[])
        assert predictions == []


class TestPredictorPodUpdate:
    @pytest.mark.asyncio
    async def test_pod_with_limits_stored_as_pct(self, predictor):
        from src.models import PodMetrics

        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        pod = PodMetrics(
            pod_name="web-0",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,  # 128Mi
            restart_count=0,
            status="Running",
            cpu_limit_millicores=500,
            memory_limit_bytes=268435456,  # 256Mi
            timestamp=base_ts,
        )
        await predictor.update(node_metrics=[], pod_metrics=[pod])
        key = "default/pod/web-0"
        assert "memory_pct" in predictor._history[key]
        assert "cpu_pct" in predictor._history[key]
        mem_pct = predictor._history[key]["memory_pct"][0][1]
        assert abs(mem_pct - 50.0) < 0.1

    @pytest.mark.asyncio
    async def test_pod_without_memory_limit_not_stored(self, predictor):
        from src.models import PodMetrics

        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        pod = PodMetrics(
            pod_name="web-0",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,
            restart_count=0,
            status="Running",
            cpu_limit_millicores=None,
            memory_limit_bytes=None,
            timestamp=base_ts,
        )
        await predictor.update(node_metrics=[], pod_metrics=[pod])
        key = "default/pod/web-0"
        assert "memory_pct" not in predictor._history.get(key, {})
        assert "cpu_pct" not in predictor._history.get(key, {})


def make_pod_with_limits(name, ns, cpu_m, mem_bytes, cpu_limit_m, mem_limit_bytes, ts):
    return PodMetrics(
        pod_name=name,
        namespace=ns,
        node_name="node-1",
        cpu_usage_millicores=cpu_m,
        memory_usage_bytes=mem_bytes,
        restart_count=0,
        status="Running",
        cpu_limit_millicores=cpu_limit_m,
        memory_limit_bytes=mem_limit_bytes,
        timestamp=ts,
    )


class TestPredictorPodPredict:
    @pytest.mark.asyncio
    async def test_returns_tuple(self, predictor):
        ts = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        node = make_node("node-1", 50.0, 50.0, 50.0, ts)
        result = await predictor.predict(node_metrics=[node], pod_metrics=[])
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_missing_memory_limit_generates_anomaly(self, predictor):
        ts = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        pod = make_pod_with_limits("web-0", "default", 100, 50000000, None, None, ts)
        _, anomalies = await predictor.predict(node_metrics=[], pod_metrics=[pod])
        assert len(anomalies) == 1
        assert anomalies[0].severity.name == "WARNING"
        assert "web-0" in anomalies[0].description
        assert "memory" in anomalies[0].description.lower()

    @pytest.mark.asyncio
    async def test_missing_cpu_limit_no_anomaly(self, predictor):
        ts = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        pod = make_pod_with_limits(
            "web-0", "default", 100, 50000000, None, 268435456, ts
        )
        _, anomalies = await predictor.predict(node_metrics=[], pod_metrics=[pod])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_pod_memory_prediction(self, predictor):
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        mem_limit = 268435456  # 256Mi
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            usage = int(mem_limit * (0.60 + i * 0.02))
            pod = make_pod_with_limits("db-0", "data", 100, usage, 500, mem_limit, ts)
            await predictor.update(node_metrics=[], pod_metrics=[pod])

        ts = base_ts + timedelta(hours=10)
        pod = make_pod_with_limits(
            "db-0", "data", 100, int(mem_limit * 0.80), 500, mem_limit, ts
        )
        await predictor.update(node_metrics=[], pod_metrics=[pod])
        predictions, _ = await predictor.predict(node_metrics=[], pod_metrics=[pod])
        mem_preds = [p for p in predictions if p.metric_name == "memory_pct"]
        assert len(mem_preds) >= 1
        assert mem_preds[0].hours_to_threshold > 0

    @pytest.mark.asyncio
    async def test_node_predictions_still_work(self, predictor):
        """Ensure existing node prediction is unaffected by tuple change."""
        base_ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_ts + timedelta(hours=i)
            node = make_node("node-1", 50.0, 50.0, 70.0 + i * 2.0, ts)
            await predictor.update(node_metrics=[node], pod_metrics=[])
        ts = base_ts + timedelta(hours=10)
        node = make_node("node-1", 50.0, 50.0, 88.0, ts)
        await predictor.update(node_metrics=[node], pod_metrics=[])
        predictions, anomalies = await predictor.predict(
            node_metrics=[node], pod_metrics=[]
        )
        disk_preds = [p for p in predictions if p.metric_name == "disk_usage_percent"]
        assert len(disk_preds) >= 1
        assert anomalies == []

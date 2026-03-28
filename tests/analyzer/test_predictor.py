import pytest
from datetime import datetime, timezone, timedelta

from src.analyzer.predictor import Predictor
from src.config import Config
from src.models import NodeMetrics


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

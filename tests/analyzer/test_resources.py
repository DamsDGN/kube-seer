import pytest

from src.analyzer.resources import ResourceStateAnalyzer, _parse_quantity, _usage_pct
from src.config import Config
from src.models import ResourceState, Severity


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def analyzer(config):
    return ResourceStateAnalyzer(config)


def _make_rs(kind, name="my-resource", namespace="default", **kwargs):
    from datetime import datetime, timezone

    return ResourceState(
        kind=kind,
        name=name,
        namespace=namespace,
        timestamp=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        **kwargs,
    )


# ── _parse_quantity ───────────────────────────────────────────────────────────


class TestParseQuantity:
    def test_millicores(self):
        assert _parse_quantity("500m") == pytest.approx(0.5)

    def test_plain_integer(self):
        assert _parse_quantity("2") == pytest.approx(2.0)

    def test_mebibytes(self):
        assert _parse_quantity("256Mi") == pytest.approx(256 * 1024**2)

    def test_gibibytes(self):
        assert _parse_quantity("1Gi") == pytest.approx(1024**3)

    def test_kibibytes(self):
        assert _parse_quantity("4Ki") == pytest.approx(4096)

    def test_megabytes_decimal(self):
        assert _parse_quantity("100M") == pytest.approx(100 * 1000**2)

    def test_empty_string_returns_zero(self):
        assert _parse_quantity("") == 0.0

    def test_invalid_string_returns_zero(self):
        assert _parse_quantity("notanumber") == 0.0


class TestUsagePct:
    def test_normal(self):
        assert _usage_pct("500m", "2") == pytest.approx(25.0)

    def test_zero_hard_returns_zero(self):
        assert _usage_pct("500m", "0") == 0.0

    def test_full(self):
        assert _usage_pct("1Gi", "1Gi") == pytest.approx(100.0)


# ── Deployments / StatefulSets / DaemonSets ──────────────────────────────────


class TestCheckReplicas:
    @pytest.mark.asyncio
    async def test_healthy_deployment_no_anomaly(self, analyzer):
        rs = _make_rs("Deployment", desired_replicas=3, ready_replicas=3)
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_zero_desired_skipped(self, analyzer):
        rs = _make_rs("Deployment", desired_replicas=0, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_none_desired_skipped(self, analyzer):
        rs = _make_rs("Deployment", desired_replicas=None, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_zero_ready_is_critical(self, analyzer):
        rs = _make_rs("Deployment", desired_replicas=3, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "0/3" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_partial_ready_is_warning(self, analyzer):
        rs = _make_rs("StatefulSet", desired_replicas=3, ready_replicas=1)
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "1/3" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_daemonset_degraded(self, analyzer):
        rs = _make_rs("DaemonSet", desired_replicas=5, ready_replicas=3)
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING

    @pytest.mark.asyncio
    async def test_resource_type_snake_case(self, analyzer):
        rs = _make_rs("StatefulSet", desired_replicas=2, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert anomalies[0].resource_type == "stateful_set"

    @pytest.mark.asyncio
    async def test_source_is_resources(self, analyzer):
        rs = _make_rs("Deployment", desired_replicas=1, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert anomalies[0].source == "resources"


# ── Jobs ──────────────────────────────────────────────────────────────────────


class TestCheckJob:
    @pytest.mark.asyncio
    async def test_successful_job_no_anomaly(self, analyzer):
        rs = _make_rs("Job", desired_replicas=1, ready_replicas=1)
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_zero_completions_is_warning(self, analyzer):
        rs = _make_rs("Job", desired_replicas=1, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "0/1" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_no_desired_skipped(self, analyzer):
        rs = _make_rs("Job", desired_replicas=None, ready_replicas=0)
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── CronJobs ──────────────────────────────────────────────────────────────────


class TestCheckCronJob:
    @pytest.mark.asyncio
    async def test_active_cronjob_no_anomaly(self, analyzer):
        rs = _make_rs(
            "CronJob", conditions={"suspended": False, "schedule": "0 * * * *"}
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_suspended_cronjob_is_warning(self, analyzer):
        rs = _make_rs(
            "CronJob",
            conditions={"suspended": True, "schedule": "0 * * * *"},
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "suspended" in anomalies[0].description
        assert "0 * * * *" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_suspended_without_schedule_uses_placeholder(self, analyzer):
        rs = _make_rs("CronJob", conditions={"suspended": True})
        anomalies = await analyzer.analyze([rs])
        assert "?" in anomalies[0].description


# ── PersistentVolumeClaims ────────────────────────────────────────────────────


class TestCheckPVC:
    @pytest.mark.asyncio
    async def test_bound_pvc_no_anomaly(self, analyzer):
        rs = _make_rs("PersistentVolumeClaim", conditions={"status": "Bound"})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_pending_pvc_is_warning(self, analyzer):
        rs = _make_rs("PersistentVolumeClaim", conditions={"status": "Pending"})
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "Pending" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_lost_pvc_is_critical(self, analyzer):
        rs = _make_rs("PersistentVolumeClaim", conditions={"status": "Lost"})
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_pvc_includes_capacity(self, analyzer):
        rs = _make_rs(
            "PersistentVolumeClaim",
            conditions={
                "status": "Pending",
                "capacity": "10Gi",
                "storage_class": "standard",
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert "10Gi" in anomalies[0].description
        assert "standard" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_pvc_capacity_without_storage_class(self, analyzer):
        rs = _make_rs(
            "PersistentVolumeClaim",
            conditions={"status": "Pending", "capacity": "5Gi"},
        )
        anomalies = await analyzer.analyze([rs])
        assert "5Gi" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_unknown_status_is_warning(self, analyzer):
        rs = _make_rs("PersistentVolumeClaim", conditions={})
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING


# ── HorizontalPodAutoscalers ──────────────────────────────────────────────────


class TestCheckHPA:
    @pytest.mark.asyncio
    async def test_below_max_no_anomaly(self, analyzer):
        rs = _make_rs(
            "HorizontalPodAutoscaler",
            ready_replicas=3,
            conditions={"max_replicas": 10, "target": "my-deployment"},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_at_max_is_warning(self, analyzer):
        rs = _make_rs(
            "HorizontalPodAutoscaler",
            ready_replicas=10,
            conditions={"max_replicas": 10, "target": "my-deployment"},
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "10/10" in anomalies[0].description
        assert "my-deployment" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_no_max_replicas_no_anomaly(self, analyzer):
        rs = _make_rs(
            "HorizontalPodAutoscaler",
            ready_replicas=10,
            conditions={},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── ResourceQuotas ────────────────────────────────────────────────────────────


class TestCheckQuota:
    @pytest.mark.asyncio
    async def test_low_usage_no_anomaly(self, analyzer):
        rs = _make_rs(
            "ResourceQuota",
            conditions={
                "cpu_used": "500m",
                "cpu_hard": "4",
                "memory_used": "256Mi",
                "memory_hard": "8Gi",
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_high_cpu_is_warning(self, analyzer):
        rs = _make_rs(
            "ResourceQuota",
            conditions={
                "cpu_used": "3600m",
                "cpu_hard": "4",
                "memory_used": "256Mi",
                "memory_hard": "8Gi",
            },
        )
        anomalies = await analyzer.analyze([rs])
        cpu_anomalies = [a for a in anomalies if "CPU" in a.description]
        assert len(cpu_anomalies) == 1
        assert cpu_anomalies[0].severity == Severity.WARNING
        assert "90%" in cpu_anomalies[0].description

    @pytest.mark.asyncio
    async def test_high_memory_is_warning(self, analyzer):
        rs = _make_rs(
            "ResourceQuota",
            conditions={
                "cpu_used": "100m",
                "cpu_hard": "4",
                "memory_used": "7Gi",
                "memory_hard": "8Gi",
            },
        )
        anomalies = await analyzer.analyze([rs])
        mem_anomalies = [a for a in anomalies if "memory" in a.description]
        assert len(mem_anomalies) == 1
        assert mem_anomalies[0].severity == Severity.WARNING

    @pytest.mark.asyncio
    async def test_both_high_produces_two_anomalies(self, analyzer):
        rs = _make_rs(
            "ResourceQuota",
            conditions={
                "cpu_used": "4",
                "cpu_hard": "4",
                "memory_used": "8Gi",
                "memory_hard": "8Gi",
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 2

    @pytest.mark.asyncio
    async def test_exactly_at_threshold_triggers(self, analyzer):
        # 80% should trigger (>= 80.0)
        rs = _make_rs(
            "ResourceQuota",
            conditions={
                "cpu_used": "800m",
                "cpu_hard": "1",
                "memory_used": "0",
                "memory_hard": "1Gi",
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1

    @pytest.mark.asyncio
    async def test_missing_quota_values_no_anomaly(self, analyzer):
        rs = _make_rs("ResourceQuota", conditions={})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── Nodes ─────────────────────────────────────────────────────────────────────


class TestCheckNode:
    @pytest.mark.asyncio
    async def test_healthy_node_no_anomaly(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={
                "ready": True,
                "memory_pressure": False,
                "disk_pressure": False,
                "pid_pressure": False,
                "unschedulable": False,
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_notready_is_critical(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": False},
        )
        anomalies = await analyzer.analyze([rs])
        assert any(a.severity == Severity.CRITICAL for a in anomalies)
        assert any("NotReady" in a.description for a in anomalies)

    @pytest.mark.asyncio
    async def test_memory_pressure_is_critical(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": True, "memory_pressure": True},
        )
        anomalies = await analyzer.analyze([rs])
        assert any(
            a.severity == Severity.CRITICAL and "MemoryPressure" in a.description
            for a in anomalies
        )

    @pytest.mark.asyncio
    async def test_disk_pressure_is_critical(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": True, "disk_pressure": True},
        )
        anomalies = await analyzer.analyze([rs])
        assert any(
            a.severity == Severity.CRITICAL and "DiskPressure" in a.description
            for a in anomalies
        )

    @pytest.mark.asyncio
    async def test_pid_pressure_is_warning(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": True, "pid_pressure": True},
        )
        anomalies = await analyzer.analyze([rs])
        assert any(
            a.severity == Severity.WARNING and "PIDPressure" in a.description
            for a in anomalies
        )

    @pytest.mark.asyncio
    async def test_unschedulable_is_warning(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": True, "unschedulable": True},
        )
        anomalies = await analyzer.analyze([rs])
        assert any(
            a.severity == Severity.WARNING and "unschedulable" in a.description
            for a in anomalies
        )

    @pytest.mark.asyncio
    async def test_multiple_conditions_produces_multiple_anomalies(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={
                "ready": False,
                "memory_pressure": True,
                "disk_pressure": True,
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 3

    @pytest.mark.asyncio
    async def test_empty_conditions_healthy(self, analyzer):
        # ready defaults to True via .get("ready", True)
        rs = _make_rs("Node", name="node-1", namespace="", conditions={})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_resource_type_is_node(self, analyzer):
        rs = _make_rs(
            "Node",
            name="node-1",
            namespace="",
            conditions={"ready": False},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies[0].resource_type == "node"


# ── Services ──────────────────────────────────────────────────────────────────


class TestCheckService:
    @pytest.mark.asyncio
    async def test_service_with_endpoints_no_anomaly(self, analyzer):
        rs = _make_rs(
            "Service",
            conditions={"ready_endpoints": 3, "service_type": "ClusterIP"},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_zero_endpoints_is_critical(self, analyzer):
        rs = _make_rs(
            "Service",
            conditions={"ready_endpoints": 0, "service_type": "ClusterIP"},
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "0 ready endpoints" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_missing_ready_endpoints_no_anomaly(self, analyzer):
        # -1 sentinel (no selector) → skip
        rs = _make_rs("Service", conditions={"ready_endpoints": -1})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_description_includes_namespace_and_name(self, analyzer):
        rs = _make_rs(
            "Service",
            name="my-svc",
            namespace="production",
            conditions={"ready_endpoints": 0},
        )
        anomalies = await analyzer.analyze([rs])
        assert "production/my-svc" in anomalies[0].description


# ── PodDisruptionBudgets ──────────────────────────────────────────────────────


class TestCheckPDB:
    @pytest.mark.asyncio
    async def test_healthy_pdb_no_anomaly(self, analyzer):
        rs = _make_rs(
            "PodDisruptionBudget",
            conditions={
                "current_healthy": 3,
                "desired_healthy": 2,
                "disruptions_allowed": 1,
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_violated_pdb_is_critical(self, analyzer):
        rs = _make_rs(
            "PodDisruptionBudget",
            conditions={
                "current_healthy": 1,
                "desired_healthy": 3,
                "disruptions_allowed": 0,
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "1/3" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_disruptions_allowed_shown_in_description(self, analyzer):
        rs = _make_rs(
            "PodDisruptionBudget",
            conditions={
                "current_healthy": 0,
                "desired_healthy": 2,
                "disruptions_allowed": 0,
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert "disruptions_allowed=0" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_zero_desired_skipped(self, analyzer):
        rs = _make_rs(
            "PodDisruptionBudget",
            conditions={"current_healthy": 0, "desired_healthy": 0},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_missing_conditions_skipped(self, analyzer):
        rs = _make_rs("PodDisruptionBudget", conditions={})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── PersistentVolumes ─────────────────────────────────────────────────────────


class TestCheckPV:
    @pytest.mark.asyncio
    async def test_bound_pv_no_anomaly(self, analyzer):
        rs = _make_rs(
            "PersistentVolume",
            name="pv-001",
            namespace="",
            conditions={"phase": "Bound", "capacity": "10Gi"},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_available_pv_no_anomaly(self, analyzer):
        rs = _make_rs(
            "PersistentVolume",
            name="pv-001",
            namespace="",
            conditions={"phase": "Available"},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_failed_pv_is_critical(self, analyzer):
        rs = _make_rs(
            "PersistentVolume",
            name="pv-001",
            namespace="",
            conditions={"phase": "Failed", "claim_ref": "default/my-pvc"},
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "Failed" in anomalies[0].description
        assert "default/my-pvc" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_released_pv_is_warning(self, analyzer):
        rs = _make_rs(
            "PersistentVolume",
            name="pv-001",
            namespace="",
            conditions={
                "phase": "Released",
                "capacity": "50Gi",
                "reclaim_policy": "Retain",
            },
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert "Released" in anomalies[0].description
        assert "50Gi" in anomalies[0].description
        assert "Retain" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_unknown_phase_no_anomaly(self, analyzer):
        rs = _make_rs(
            "PersistentVolume",
            name="pv-001",
            namespace="",
            conditions={"phase": "Pending"},
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── Namespaces ────────────────────────────────────────────────────────────────


class TestCheckNamespace:
    @pytest.mark.asyncio
    async def test_active_namespace_no_anomaly(self, analyzer):
        rs = _make_rs(
            "Namespace", name="production", namespace="", conditions={"phase": "Active"}
        )
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_terminating_namespace_is_critical(self, analyzer):
        rs = _make_rs(
            "Namespace",
            name="stuck-ns",
            namespace="",
            conditions={"phase": "Terminating"},
        )
        anomalies = await analyzer.analyze([rs])
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "Terminating" in anomalies[0].description
        assert "stuck-ns" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_empty_conditions_no_anomaly(self, analyzer):
        rs = _make_rs("Namespace", name="default", namespace="", conditions={})
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []


# ── Unknown kinds are ignored ─────────────────────────────────────────────────


class TestUnknownKind:
    @pytest.mark.asyncio
    async def test_unknown_kind_no_anomaly(self, analyzer):
        rs = _make_rs("NetworkPolicy")
        anomalies = await analyzer.analyze([rs])
        assert anomalies == []

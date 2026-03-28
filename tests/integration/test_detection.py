"""Integration tests for anomaly detection.

Each test deploys a specific workload in the test namespace, triggers an analysis,
and asserts that the expected anomaly is detected.

Requires a running Kind cluster: make kind-up
Run with: make test-integration
"""

import time

import pytest
from kubernetes import client as k8s_client

pytestmark = pytest.mark.integration

WAIT_TIMEOUT = 60  # seconds
POLL_INTERVAL = 3  # seconds


def _wait_for_pod_restarts(
    core_v1, namespace, label_selector, min_restarts=1, timeout=WAIT_TIMEOUT
):
    """Poll until at least one pod has restarted min_restarts times."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pods = core_v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        for pod in pods.items:
            for cs in pod.status.container_statuses or []:
                if cs.restart_count >= min_restarts:
                    return True
        time.sleep(POLL_INTERVAL)
    return False


def _wait_for_pod_pending(core_v1, namespace, pod_name, timeout=WAIT_TIMEOUT):
    """Poll until the pod is in Pending phase."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.status.phase == "Pending":
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


def test_crash_loop_detected(api, k8s, test_namespace):
    """A pod that exits immediately should be detected as BackOff / high restart count."""
    core_v1, apps_v1 = k8s
    deployment_name = "int-test-crash-loop"

    deployment = k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name=deployment_name, namespace=test_namespace
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(match_labels={"app": deployment_name}),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels={"app": deployment_name}),
                spec=k8s_client.V1PodSpec(
                    containers=[
                        k8s_client.V1Container(
                            name="crash",
                            image="busybox:latest",
                            command=["sh", "-c", "exit 1"],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"cpu": "10m", "memory": "16Mi"}
                            ),
                        )
                    ]
                ),
            ),
        ),
    )
    apps_v1.create_namespaced_deployment(namespace=test_namespace, body=deployment)

    restarted = _wait_for_pod_restarts(
        core_v1, test_namespace, f"app={deployment_name}", min_restarts=2
    )
    assert restarted, f"Pod {deployment_name} did not restart within {WAIT_TIMEOUT}s"

    r = api.post("/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["anomalies_found"] > 0

    # Verify the anomaly is queryable by namespace
    r = api.get("/anomalies", params={"namespace": test_namespace, "limit": 50})
    assert r.status_code == 200
    descriptions = [a["data"]["description"] for a in r.json()["anomalies"]]
    assert any(
        deployment_name in d or "restart" in d.lower() or "BackOff" in d
        for d in descriptions
    ), f"No crash-loop anomaly found for {deployment_name}. Got: {descriptions}"


def test_pending_pod_detected(api, k8s, test_namespace):
    """An unschedulable pod should be detected via FailedScheduling event."""
    core_v1, _ = k8s
    pod_name = "int-test-pending"

    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(name=pod_name, namespace=test_namespace),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="pending",
                    image="nginx:latest",
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "9999", "memory": "9999Gi"}
                    ),
                )
            ]
        ),
    )
    core_v1.create_namespaced_pod(namespace=test_namespace, body=pod)

    pending = _wait_for_pod_pending(core_v1, test_namespace, pod_name)
    assert pending, f"Pod {pod_name} did not reach Pending state within {WAIT_TIMEOUT}s"

    # Wait for FailedScheduling event to be recorded
    time.sleep(5)

    r = api.post("/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["anomalies_found"] > 0

    r = api.get("/anomalies", params={"namespace": test_namespace, "limit": 50})
    assert r.status_code == 200
    descriptions = [a["data"]["description"] for a in r.json()["anomalies"]]
    assert any(
        "FailedScheduling" in d or "Insufficient" in d for d in descriptions
    ), f"No scheduling anomaly found. Got: {descriptions}"


def test_pod_without_memory_limit_detected(api, k8s, test_namespace):
    """A pod without memory limit should trigger a policy anomaly (OOM risk)."""
    core_v1, _ = k8s
    pod_name = "int-test-no-limit"

    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(name=pod_name, namespace=test_namespace),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="app",
                    image="busybox:latest",
                    command=["sh", "-c", "sleep 3600"],
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "10m", "memory": "16Mi"}
                        # intentionally no limits
                    ),
                )
            ]
        ),
    )
    core_v1.create_namespaced_pod(namespace=test_namespace, body=pod)

    # Wait for pod to be scheduled
    deadline = time.time() + WAIT_TIMEOUT
    while time.time() < deadline:
        p = core_v1.read_namespaced_pod(name=pod_name, namespace=test_namespace)
        if p.status.phase in ("Running", "Pending"):
            break
        time.sleep(POLL_INTERVAL)

    r = api.post("/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["anomalies_found"] > 0

    r = api.get("/anomalies", params={"namespace": test_namespace, "limit": 50})
    assert r.status_code == 200
    descriptions = [a["data"]["description"] for a in r.json()["anomalies"]]
    assert any(
        "memory limit" in d.lower() or "OOM" in d for d in descriptions
    ), f"No memory limit policy anomaly found. Got: {descriptions}"

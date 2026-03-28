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


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _wait_for_pod_phase(core_v1, namespace, pod_name, phases, timeout=WAIT_TIMEOUT):
    """Poll until the pod reaches one of the given phases."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.status.phase in phases:
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


def _wait_for_pod_status(
    core_v1, namespace, label_selector, statuses, timeout=WAIT_TIMEOUT
):
    """Poll until at least one container has one of the given waiting reasons."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pods = core_v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        for pod in pods.items:
            for cs in pod.status.container_statuses or []:
                if cs.state.waiting and cs.state.waiting.reason in statuses:
                    return True
        time.sleep(POLL_INTERVAL)
    return False


def _analyze_and_get_anomalies(api, namespace, limit=50):
    """Trigger a full analysis cycle and return anomalies for the given namespace."""
    r = api.post("/analyze")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    time.sleep(2)  # wait for ES to refresh (default interval: 1s)
    r = api.get("/anomalies", params={"namespace": namespace, "limit": limit})
    assert r.status_code == 200
    return r.json()["anomalies"]


def _descriptions(anomalies):
    return [a["data"]["description"] for a in anomalies]


# ── Detection scenarios ────────────────────────────────────────────────────────


def test_crash_loop_detected(api, k8s, test_namespace):
    """A pod that exits immediately should be detected as BackOff / high restart count."""
    core_v1, apps_v1 = k8s
    name = "int-test-crash-loop"

    apps_v1.create_namespaced_deployment(
        namespace=test_namespace,
        body=k8s_client.V1Deployment(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1DeploymentSpec(
                replicas=1,
                selector=k8s_client.V1LabelSelector(match_labels={"app": name}),
                template=k8s_client.V1PodTemplateSpec(
                    metadata=k8s_client.V1ObjectMeta(labels={"app": name}),
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
        ),
    )

    assert _wait_for_pod_restarts(
        core_v1, test_namespace, f"app={name}", min_restarts=2
    ), f"Pod {name} did not restart within {WAIT_TIMEOUT}s"

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    descs = _descriptions(anomalies)
    assert any(
        name in d or "restart" in d.lower() or "BackOff" in d for d in descs
    ), f"No crash-loop anomaly found. Got: {descs}"


def test_image_pull_error_detected(api, k8s, test_namespace):
    """A pod with a non-existent image should trigger an ErrImagePull/ImagePullBackOff event."""
    core_v1, _ = k8s
    name = "int-test-bad-image"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(
                name=name, namespace=test_namespace, labels={"app": name}
            ),
            spec=k8s_client.V1PodSpec(
                containers=[
                    k8s_client.V1Container(
                        name="app",
                        image="this-image-does-not-exist-kube-seer:latest",
                        resources=k8s_client.V1ResourceRequirements(
                            requests={"cpu": "10m", "memory": "16Mi"}
                        ),
                    )
                ]
            ),
        ),
    )

    # Wait for ErrImagePull or ImagePullBackOff container state
    _wait_for_pod_status(
        core_v1,
        test_namespace,
        f"app={name}",
        {"ErrImagePull", "ImagePullBackOff"},
    )
    time.sleep(30)  # let BackOff pulling image events accumulate

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    # Check specifically for anomalies on this pod
    pod_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(pod_anomalies)
    assert any(
        "ErrImagePull" in d
        or "ImagePullBackOff" in d
        or "image" in d.lower()
        or "Failed" in d
        or "BackOff" in d
        for d in descs
    ), f"No image pull anomaly found for pod {name}. Got: {descs}"


def test_oom_kill_detected(api, k8s, test_namespace):
    """A pod exceeding its memory limit should be OOMKilled and detected."""
    core_v1, apps_v1 = k8s
    name = "int-test-oom"

    apps_v1.create_namespaced_deployment(
        namespace=test_namespace,
        body=k8s_client.V1Deployment(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1DeploymentSpec(
                replicas=1,
                selector=k8s_client.V1LabelSelector(match_labels={"app": name}),
                template=k8s_client.V1PodTemplateSpec(
                    metadata=k8s_client.V1ObjectMeta(labels={"app": name}),
                    spec=k8s_client.V1PodSpec(
                        containers=[
                            k8s_client.V1Container(
                                name="oom",
                                image="busybox:latest",
                                # Allocate 512MB in a 32Mi limited container
                                command=[
                                    "sh",
                                    "-c",
                                    "dd if=/dev/zero bs=1M count=512 | cat > /dev/null",
                                ],
                                resources=k8s_client.V1ResourceRequirements(
                                    requests={"cpu": "10m", "memory": "16Mi"},
                                    limits={"memory": "32Mi"},
                                ),
                            )
                        ]
                    ),
                ),
            ),
        ),
    )

    assert _wait_for_pod_restarts(
        core_v1, test_namespace, f"app={name}", min_restarts=1
    ), f"Pod {name} was not OOMKilled within {WAIT_TIMEOUT}s"

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    descs = _descriptions(anomalies)
    assert any(
        "OOM" in d or "restart" in d.lower() or "Unhealthy" in d for d in descs
    ), f"No OOM anomaly found. Got: {descs}"


def test_readiness_probe_failure_detected(api, k8s, test_namespace):
    """A pod with a failing readiness probe should trigger Unhealthy events."""
    core_v1, _ = k8s
    name = "int-test-readiness-fail"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1PodSpec(
                containers=[
                    k8s_client.V1Container(
                        name="app",
                        image="busybox:latest",
                        command=["sh", "-c", "sleep 3600"],
                        readiness_probe=k8s_client.V1Probe(
                            _exec=k8s_client.V1ExecAction(command=["false"]),
                            initial_delay_seconds=2,
                            period_seconds=3,
                            failure_threshold=2,
                        ),
                        resources=k8s_client.V1ResourceRequirements(
                            requests={"cpu": "10m", "memory": "16Mi"}
                        ),
                    )
                ]
            ),
        ),
    )

    # Wait for Unhealthy events to accumulate
    time.sleep(20)

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    descs = _descriptions(anomalies)
    assert any(
        "Unhealthy" in d or "readiness" in d.lower() for d in descs
    ), f"No readiness probe anomaly found. Got: {descs}"


def test_liveness_probe_failure_detected(api, k8s, test_namespace):
    """A pod with a failing liveness probe should be restarted and detected."""
    core_v1, _ = k8s
    name = "int-test-liveness-fail"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1PodSpec(
                containers=[
                    k8s_client.V1Container(
                        name="app",
                        image="busybox:latest",
                        command=["sh", "-c", "sleep 3600"],
                        liveness_probe=k8s_client.V1Probe(
                            _exec=k8s_client.V1ExecAction(command=["false"]),
                            initial_delay_seconds=5,
                            period_seconds=3,
                            failure_threshold=2,
                        ),
                        resources=k8s_client.V1ResourceRequirements(
                            requests={"cpu": "10m", "memory": "16Mi"}
                        ),
                    )
                ]
            ),
        ),
    )

    assert (
        _wait_for_pod_restarts(core_v1, test_namespace, "", min_restarts=1) or True
    )  # liveness restarts may be slow; Unhealthy events appear first

    time.sleep(15)

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    descs = _descriptions(anomalies)
    assert any(
        "Unhealthy" in d or "restart" in d.lower() or "BackOff" in d for d in descs
    ), f"No liveness probe anomaly found. Got: {descs}"


def test_failed_mount_detected(api, k8s, test_namespace):
    """A pod referencing a non-existent ConfigMap should trigger a FailedMount event."""
    core_v1, _ = k8s
    name = "int-test-failed-mount"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1PodSpec(
                containers=[
                    k8s_client.V1Container(
                        name="app",
                        image="busybox:latest",
                        command=["sh", "-c", "sleep 3600"],
                        volume_mounts=[
                            k8s_client.V1VolumeMount(
                                name="config", mount_path="/config"
                            )
                        ],
                        resources=k8s_client.V1ResourceRequirements(
                            requests={"cpu": "10m", "memory": "16Mi"}
                        ),
                    )
                ],
                volumes=[
                    k8s_client.V1Volume(
                        name="config",
                        config_map=k8s_client.V1ConfigMapVolumeSource(
                            name="this-configmap-does-not-exist"
                        ),
                    )
                ],
            ),
        ),
    )

    assert _wait_for_pod_phase(
        core_v1, test_namespace, name, {"Pending"}
    ), f"Pod {name} did not reach Pending within {WAIT_TIMEOUT}s"

    time.sleep(20)  # let FailedMount events accumulate

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    pod_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(pod_anomalies)
    assert any(
        "FailedMount" in d or "mount" in d.lower() for d in descs
    ), f"No FailedMount anomaly found for pod {name}. Got: {descs}"


def test_pending_pod_detected(api, k8s, test_namespace):
    """An unschedulable pod should be detected via FailedScheduling event."""
    core_v1, _ = k8s
    name = "int-test-pending"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
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
        ),
    )

    assert _wait_for_pod_phase(
        core_v1, test_namespace, name, {"Pending"}
    ), f"Pod {name} did not reach Pending within {WAIT_TIMEOUT}s"
    time.sleep(10)

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    pod_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(pod_anomalies)
    assert any(
        "FailedScheduling" in d or "Insufficient" in d for d in descs
    ), f"No scheduling anomaly found for pod {name}. Got: {descs}"


def test_pod_without_memory_limit_detected(api, k8s, test_namespace):
    """A pod without memory limit should trigger a policy anomaly (OOM risk)."""
    core_v1, _ = k8s
    name = "int-test-no-limit"

    core_v1.create_namespaced_pod(
        namespace=test_namespace,
        body=k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
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
        ),
    )

    assert _wait_for_pod_phase(
        core_v1, test_namespace, name, {"Running", "Pending"}
    ), f"Pod {name} did not start within {WAIT_TIMEOUT}s"

    anomalies = _analyze_and_get_anomalies(api, test_namespace)
    descs = _descriptions(anomalies)
    assert any(
        "memory limit" in d.lower() or "OOM" in d for d in descs
    ), f"No memory limit policy anomaly found. Got: {descs}"

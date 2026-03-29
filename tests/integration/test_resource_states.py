"""Integration tests for ResourceStateAnalyzer.

Each test creates a specific K8s resource in a failing/degraded state,
triggers an analysis cycle, and asserts that `source=resources` anomalies
are detected.

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


def _wait_for_deployment_state(apps_v1, namespace, name, timeout=WAIT_TIMEOUT):
    """Poll until the deployment has been processed (desired replicas set)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            if d.spec.replicas is not None:
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


def _wait_for_pvc(core_v1, namespace, name, timeout=WAIT_TIMEOUT):
    """Poll until the PVC exists."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            core_v1.read_namespaced_persistent_volume_claim(
                name=name, namespace=namespace
            )
            return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


def _analyze_and_get_resource_anomalies(api, namespace, limit=50):
    """Trigger analysis and return source=resources anomalies for the namespace."""
    r = api.post("/analyze")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    time.sleep(2)  # wait for ES refresh
    r = api.get("/anomalies", params={"namespace": namespace, "limit": limit})
    assert r.status_code == 200
    return [a for a in r.json()["anomalies"] if a["data"]["source"] == "resources"]


def _descriptions(anomalies):
    return [a["data"]["description"] for a in anomalies]


# ── Scenarios ─────────────────────────────────────────────────────────────────


def test_degraded_deployment_detected(api, k8s, test_namespace):
    """A Deployment with a non-existent image should appear as 0/1 replicas ready (CRITICAL)."""
    core_v1, apps_v1 = k8s
    name = "rs-test-bad-deploy"

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
                                name="app",
                                image="this-image-does-not-exist-kube-seer:v999",
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

    assert _wait_for_deployment_state(
        apps_v1, test_namespace, name
    ), f"Deployment {name} not created within {WAIT_TIMEOUT}s"
    time.sleep(5)  # let the controller update ready replicas

    anomalies = _analyze_and_get_resource_anomalies(api, test_namespace)
    deploy_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(deploy_anomalies)
    assert any(
        "0/1" in d or "replicas" in d.lower() for d in descs
    ), f"No degraded deployment anomaly for {name}. Got: {descs}"

    severities = [a["data"]["severity"] for a in deploy_anomalies]
    assert any(
        s == 2 for s in severities
    ), f"Expected CRITICAL severity. Got: {severities}"


def test_suspended_cronjob_detected(api, k8s, test_namespace):
    """A suspended CronJob should be flagged as WARNING."""
    core_v1, apps_v1 = k8s
    batch_v1 = k8s_client.BatchV1Api()
    name = "rs-test-suspended-cron"

    batch_v1.create_namespaced_cron_job(
        namespace=test_namespace,
        body=k8s_client.V1CronJob(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1CronJobSpec(
                schedule="0 * * * *",
                suspend=True,
                job_template=k8s_client.V1JobTemplateSpec(
                    spec=k8s_client.V1JobSpec(
                        template=k8s_client.V1PodTemplateSpec(
                            spec=k8s_client.V1PodSpec(
                                restart_policy="Never",
                                containers=[
                                    k8s_client.V1Container(
                                        name="job",
                                        image="busybox:latest",
                                        command=["echo", "hello"],
                                        resources=k8s_client.V1ResourceRequirements(
                                            requests={"cpu": "10m", "memory": "16Mi"}
                                        ),
                                    )
                                ],
                            )
                        )
                    )
                ),
            ),
        ),
    )

    anomalies = _analyze_and_get_resource_anomalies(api, test_namespace)
    cron_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(cron_anomalies)
    assert any(
        "suspended" in d.lower() for d in descs
    ), f"No suspended CronJob anomaly for {name}. Got: {descs}"

    severities = [a["data"]["severity"] for a in cron_anomalies]
    assert any(
        s == 1 for s in severities
    ), f"Expected WARNING severity. Got: {severities}"


def test_unbound_pvc_detected(api, k8s, test_namespace):
    """A PVC referencing a non-existent StorageClass should stay Pending (WARNING)."""
    core_v1, apps_v1 = k8s
    name = "rs-test-unbound-pvc"

    core_v1.create_namespaced_persistent_volume_claim(
        namespace=test_namespace,
        body=k8s_client.V1PersistentVolumeClaim(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                storage_class_name="this-storage-class-does-not-exist",
                resources=k8s_client.V1VolumeResourceRequirements(
                    requests={"storage": "1Gi"}
                ),
            ),
        ),
    )

    assert _wait_for_pvc(
        core_v1, test_namespace, name
    ), f"PVC {name} not created within {WAIT_TIMEOUT}s"
    time.sleep(5)

    anomalies = _analyze_and_get_resource_anomalies(api, test_namespace)
    pvc_anomalies = [a for a in anomalies if a["data"]["resource_name"] == name]
    descs = _descriptions(pvc_anomalies)
    assert (
        any("Pending" in d or "Bound" not in d for d in descs)
        and len(pvc_anomalies) > 0
    ), f"No unbound PVC anomaly for {name}. Got: {descs}"

    severities = [a["data"]["severity"] for a in pvc_anomalies]
    assert any(
        s == 1 for s in severities
    ), f"Expected WARNING severity. Got: {severities}"


def test_cordoned_node_detected(api, k8s, test_namespace):
    """A cordoned node should be detected as unschedulable (WARNING)."""
    core_v1, apps_v1 = k8s
    # pick any node
    nodes = core_v1.list_node()
    assert nodes.items, "No nodes found in the cluster"
    node_name = nodes.items[0].metadata.name

    core_v1.patch_node(node_name, {"spec": {"unschedulable": True}})
    try:
        _analyze_and_get_resource_anomalies(api, test_namespace)
        # node anomalies are cluster-scoped (namespace=""), query without filter
        r = api.get("/anomalies", params={"limit": 100})
        all_anomalies = [
            a
            for a in r.json()["anomalies"]
            if a["data"]["source"] == "resources"
            and a["data"]["resource_type"] == "node"
            and a["data"]["resource_name"] == node_name
        ]
        descs = [a["data"]["description"] for a in all_anomalies]
        assert any(
            "unschedulable" in d.lower() or "cordoned" in d.lower() for d in descs
        ), f"No unschedulable anomaly for node {node_name}. Got: {descs}"
        severities = [a["data"]["severity"] for a in all_anomalies]
        assert any(s == 1 for s in severities), f"Expected WARNING. Got: {severities}"
    finally:
        core_v1.patch_node(node_name, {"spec": {"unschedulable": False}})


def test_service_without_endpoints_detected(api, k8s, test_namespace):
    """A Service with a selector matching no pods should be detected (CRITICAL)."""
    core_v1, apps_v1 = k8s
    name = "rs-test-dead-svc"

    core_v1.create_namespaced_service(
        namespace=test_namespace,
        body=k8s_client.V1Service(
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=test_namespace),
            spec=k8s_client.V1ServiceSpec(
                selector={"app": "this-pod-does-not-exist"},
                ports=[k8s_client.V1ServicePort(port=80, target_port=80)],
            ),
        ),
    )

    anomalies = _analyze_and_get_resource_anomalies(api, test_namespace)
    svc_anomalies = [
        a
        for a in anomalies
        if a["data"]["resource_name"] == name
        and a["data"]["resource_type"] == "service"
    ]
    descs = [a["data"]["description"] for a in svc_anomalies]
    assert any(
        "0 ready endpoints" in d for d in descs
    ), f"No dead-service anomaly for {name}. Got: {descs}"

    severities = [a["data"]["severity"] for a in svc_anomalies]
    assert any(s == 2 for s in severities), f"Expected CRITICAL. Got: {severities}"

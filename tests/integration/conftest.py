import petname
import pytest
import httpx
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

KUBE_SEER_URL = "http://localhost:8080"
KIND_CONTEXT = "kind-kube-seer"


@pytest.fixture(scope="session")
def api():
    try:
        httpx.get(f"{KUBE_SEER_URL}/health", timeout=5).raise_for_status()
    except Exception:
        pytest.skip(
            "kube-seer not reachable at localhost:8080 — run 'make kind-up' first"
        )
    client = httpx.Client(base_url=KUBE_SEER_URL, timeout=30)
    yield client
    client.close()


@pytest.fixture(scope="session")
def k8s():
    try:
        k8s_config.load_kube_config(context=KIND_CONTEXT)
    except Exception:
        pytest.skip(f"Kind cluster not available (context: {KIND_CONTEXT})")
    return k8s_client.CoreV1Api(), k8s_client.AppsV1Api()


@pytest.fixture(scope="session")
def test_namespace(k8s):
    core_v1, _ = k8s
    name = f"ks-test-{petname.generate(2, '-')}"
    core_v1.create_namespace(
        k8s_client.V1Namespace(metadata=k8s_client.V1ObjectMeta(name=name))
    )
    yield name
    try:
        core_v1.delete_namespace(name=name)
    except Exception:
        pass

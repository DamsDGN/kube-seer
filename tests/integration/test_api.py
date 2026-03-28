"""Integration tests for the kube-seer REST API.

Requires a running Kind cluster: make kind-up
Run with: make test-integration
"""

import pytest

pytestmark = pytest.mark.integration


def test_health(api):
    r = api.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["uptime_seconds"] > 0


def test_ready(api):
    r = api.get("/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["elasticsearch"] is True
    assert data["prometheus"] is True


def test_status_all_components(api):
    r = api.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_running"] is True
    assert data["elasticsearch"] is True
    assert data["prometheus"] is True
    assert data["metrics_server"] is True
    assert data["kubernetes_api"] is True
    assert data["uptime_seconds"] > 0


def test_config_no_secrets(api):
    r = api.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "elasticsearch_url" in data
    # Secrets must never be exposed
    assert "elasticsearch_password" not in data
    assert "elasticsearch_secret_ref" not in data
    assert "intelligence_api_key" not in data
    assert "intelligence_api_key_secret_ref" not in data


def test_anomalies_returns_list(api):
    r = api.get("/anomalies")
    assert r.status_code == 200
    data = r.json()
    assert "anomalies" in data
    assert "count" in data
    assert isinstance(data["anomalies"], list)
    assert data["count"] == len(data["anomalies"])


def test_anomalies_severity_filter(api):
    severity_map = {"info": 0, "warning": 1, "critical": 2}
    for severity, expected_val in severity_map.items():
        r = api.get("/anomalies", params={"severity": severity})
        assert r.status_code == 200
        for anomaly in r.json()["anomalies"]:
            assert anomaly["data"]["severity"] == expected_val, (
                f"Expected severity {expected_val} for filter '{severity}', "
                f"got {anomaly['data']['severity']}"
            )


def test_anomalies_namespace_filter(api):
    r = api.get("/anomalies", params={"namespace": "kube-system"})
    assert r.status_code == 200
    for anomaly in r.json()["anomalies"]:
        assert anomaly["data"]["namespace"] == "kube-system"


def test_anomalies_limit(api):
    r = api.get("/anomalies", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()["anomalies"]) <= 2


def test_incidents_returns_list(api):
    r = api.get("/incidents")
    assert r.status_code == 200
    data = r.json()
    assert "incidents" in data
    assert "count" in data
    assert isinstance(data["incidents"], list)
    assert data["count"] == len(data["incidents"])


def test_predictions_returns_list(api):
    r = api.get("/predictions")
    assert r.status_code == 200
    data = r.json()
    assert "predictions" in data
    assert "count" in data
    assert isinstance(data["predictions"], list)


def test_alerts_stats(api):
    r = api.get("/alerts/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_sent" in data
    assert "alertmanager_sent" in data
    assert "deduped" in data
    assert data["total_sent"] >= 0


def test_anomalies_unknown_severity_ignored(api):
    """An unknown severity value should be ignored and return all anomalies."""
    r_all = api.get("/anomalies")
    r_unknown = api.get("/anomalies", params={"severity": "unknown"})
    assert r_unknown.status_code == 200
    assert r_unknown.json()["count"] == r_all.json()["count"]


def test_anomalies_nonexistent_namespace_returns_empty(api):
    """Filtering by a namespace that has no anomalies should return an empty list."""
    r = api.get("/anomalies", params={"namespace": "this-namespace-does-not-exist"})
    assert r.status_code == 200
    assert r.json()["anomalies"] == []
    assert r.json()["count"] == 0


def test_analyze_returns_positive_metrics(api):
    """After analysis, metrics_analyzed should reflect live cluster pods and nodes."""
    r = api.post("/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["metrics_analyzed"] > 0


def test_analyze_trigger(api):
    r = api.post("/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert isinstance(data["anomalies_found"], int)
    assert isinstance(data["metrics_analyzed"], int)
    assert isinstance(data["events_analyzed"], int)
    assert "timestamp" in data

# kube-seer Helm Chart

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Helm chart for deploying kube-seer — an intelligent SRE agent for Kubernetes that collects metrics, detects anomalies, correlates incidents, and predicts resource saturation.

## Prerequisites

- Kubernetes 1.20+
- Helm 3.0+
- Elasticsearch (external, e.g. via ECK)
- Prometheus (optional but recommended)

## Installation

### Minimal install (no authentication)

```bash
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring \
  --create-namespace \
  --set elasticsearch.url=http://elasticsearch:9200
```

### With Elasticsearch authentication

```bash
# Inline password (chart creates a Secret)
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring \
  --create-namespace \
  --set elasticsearch.url=http://elasticsearch:9200 \
  --set elasticsearch.username=elastic \
  --set elasticsearch.password=your-password

# Reference an existing Kubernetes Secret
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring \
  --create-namespace \
  --set elasticsearch.url=http://elasticsearch:9200 \
  --set elasticsearch.secretRef=my-existing-secret
```

### Kind local environment

```bash
# Spin up a full local stack automatically
make kind-up
```

## Key Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `elasticsearch.url` | Elasticsearch URL (required) | `""` |
| `elasticsearch.username` | Username (optional) | `""` |
| `elasticsearch.password` | Password — creates a Secret (optional) | `""` |
| `elasticsearch.secretRef` | Name of an existing K8s Secret with credentials (optional) | `""` |
| `collectors.prometheus.url` | Prometheus URL | `http://prometheus-server:9090` |
| `alerter.alertmanager.url` | Alertmanager URL | `http://alertmanager:9093` |
| `agent.analysisInterval` | Analysis cycle in seconds | `300` |
| `service.type` | Service type (`ClusterIP` or `NodePort`) | `ClusterIP` |
| `service.nodePort` | NodePort number (only when type=NodePort) | `""` |
| `serviceMonitor.enabled` | Enable Prometheus ServiceMonitor | `false` |

See [values.yaml](values.yaml) for the full list of options.

## Elasticsearch Authentication

Authentication is **optional**. Three modes are supported:

**No auth** (open Elasticsearch):
```yaml
elasticsearch:
  url: http://elasticsearch:9200
```

**Inline credentials** (chart manages the Secret):
```yaml
elasticsearch:
  url: http://elasticsearch:9200
  username: elastic
  password: your-password
```

**External secret** (you manage the Secret):
```yaml
elasticsearch:
  url: http://elasticsearch:9200
  secretRef: my-existing-secret   # must contain ELASTICSEARCH_PASSWORD
```

## Useful Commands

```bash
# Check deployment status
helm status kube-seer -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=kube-seer

# View logs
kubectl logs -f deployment/kube-seer -n monitoring

# Access the API locally
kubectl port-forward svc/kube-seer 8080:8080 -n monitoring
curl http://localhost:8080/health

# Upgrade
helm upgrade kube-seer ./helm/kube-seer -n monitoring --reuse-values

# Uninstall
helm uninstall kube-seer -n monitoring
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Agent health |
| `GET /ready` | Readiness (checks ES, Prometheus) |
| `GET /status` | Full system status |
| `GET /anomalies` | Detected anomalies |
| `GET /incidents` | Correlated incidents |
| `GET /predictions` | Resource saturation predictions |
| `POST /analyze` | Trigger a manual analysis cycle |

## License

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0](../../LICENSE) — free for personal and educational use, commercial use requires authorization.

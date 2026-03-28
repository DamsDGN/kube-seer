# kube-seer

[![CI/CD Pipeline](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Intelligent SRE agent for Kubernetes — collects metrics, detects anomalies, correlates incidents, and predicts resource saturation before it happens.

## Features

- **Multi-source collection**: Prometheus, Kubernetes Metrics Server, K8s API (nodes, pods, events, PVC, HPA, NetworkPolicy, ResourceQuota, Ingress)
- **Anomaly detection**: Statistical analysis (Z-score, IQR) on CPU, memory, disk
- **Incident correlation**: Groups related anomalies into coherent incidents
- **Saturation prediction**: Linear regression with configurable horizon — predicts when a resource will reach its critical threshold
- **Pod without memory limit alerts**: Detects pods at OOM risk (no `resources.limits.memory`)
- **Multi-channel alerting**: Generic webhook, Alertmanager, Slack, Email
- **REST API**: Real-time access to anomalies, incidents, and predictions
- **Storage**: Data persistence in Elasticsearch

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        SREAgent                             │
│                                                             │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐  ┌────────┐  │
│  │Collectors│──►│ Analyzers │──►│Correlator│─►│Alerter │  │
│  └──────────┘   └───────────┘   └──────────┘  └────────┘  │
│       │              │                │                      │
│  Prometheus      Metrics         Incidents              Slack│
│  MetricsSrv      Events          AnalysisResult        Email│
│  K8s API         Logs                                  Hook │
│                  Predictor                                   │
└─────────────────────────────────────────────────────────────┘
         │                                    │
    Elasticsearch                          API REST
    (stockage)                          /anomalies
                                        /incidents
                                        /predictions
```

## Project structure

```
src/
├── agent.py              # Main orchestrator (collect → analyze → alert cycle)
├── config.py             # Configuration via environment variables
├── models.py             # Pydantic data models (NodeMetrics, PodMetrics, Anomaly...)
├── main.py               # FastAPI entry point
├── analyzer/
│   ├── metrics.py        # Anomaly detection (Z-score, IQR, thresholds)
│   ├── events.py         # Kubernetes event analysis
│   ├── logs.py           # Elasticsearch log analysis
│   ├── correlator.py     # Anomaly → incident correlation
│   └── predictor.py      # Saturation prediction (linear regression)
├── alerter/
│   ├── webhook.py        # Generic webhook
│   ├── alertmanager.py   # Prometheus Alertmanager
│   ├── slack.py          # Slack
│   └── email.py          # SMTP Email
├── collector/
│   ├── prometheus.py     # Prometheus metrics
│   ├── metrics_server.py # Kubernetes Metrics Server
│   └── k8s_api.py        # K8s API (events, states, pod limits, PVC, HPA...)
├── storage/
│   └── elasticsearch.py  # Elasticsearch persistence
└── api/
    └── routes.py         # REST endpoints (FastAPI)

tests/                    # 154 unit tests (pytest)
helm/kube-seer/           # Helm chart for Kubernetes deployment
k8s/                      # Kubernetes manifests (legacy)
```

## Installation

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Kubernetes + Helm 3.x (for deployment)

### Local development

```bash
git clone https://github.com/DamsDGN/kube-seer.git
cd kube-seer
make setup-dev          # create venv + install dependencies
source .venv/bin/activate
make test               # run 154 unit tests
```

### Local Kind environment (recommended for testing)

```bash
make kind-up            # spin up cluster + ES + Prometheus + kube-seer
# kube-seer API  → http://localhost:8080
# Prometheus     → http://localhost:9090
# Grafana        → http://localhost:3000  (admin / prom-operator)
# Alertmanager   → http://localhost:9093

make kind-reload        # rebuild and redeploy kube-seer without recreating the cluster
make kind-down          # delete the cluster
```

### Helm deployment

The namespace name is free — use whatever fits your environment (`monitoring`, `kube-seer`, `observability`, etc.).

```bash
# Minimal install — chart creates the namespace
helm install kube-seer ./helm/kube-seer \
  --namespace <your-namespace> \
  --set createNamespace=true \
  --set elasticsearch.url=http://elasticsearch:9200

# Or let Helm create the namespace
helm install kube-seer ./helm/kube-seer \
  --namespace <your-namespace> \
  --create-namespace \
  --set elasticsearch.url=http://elasticsearch:9200

# With Elasticsearch authentication (HTTPS + self-signed certificate)
helm install kube-seer ./helm/kube-seer \
  --namespace <your-namespace> \
  --create-namespace \
  --set elasticsearch.url=https://elasticsearch:9200 \
  --set elasticsearch.username=elastic \
  --set elasticsearch.password=your-password \
  --set elasticsearch.verifyTls=false
```

## REST API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Agent health |
| `GET /ready` | Readiness (checks ES, Prometheus) |
| `GET /status` | Full system status |
| `GET /config` | Active configuration (without secrets) |
| `GET /anomalies` | Detected anomalies (filterable by severity/namespace) |
| `GET /incidents` | Correlated incidents |
| `GET /predictions` | Saturation predictions |
| `GET /alerts/stats` | Alert statistics |
| `POST /analyze` | Trigger a manual analysis |

## Configuration

The main parameters are configurable via environment variables:

```yaml
# Connections
ELASTICSEARCH_URL: http://elasticsearch:9200
PROMETHEUS_URL: http://prometheus:9090

# Alert thresholds
THRESHOLDS_CPU_WARNING: 70.0
THRESHOLDS_CPU_CRITICAL: 85.0
THRESHOLDS_MEMORY_WARNING: 70.0
THRESHOLDS_MEMORY_CRITICAL: 85.0
THRESHOLDS_DISK_CRITICAL: 90.0

# Prediction
PREDICTION_HORIZON_HOURS: 168   # Prediction horizon (7 days by default)

# ML
ANOMALY_THRESHOLD: 0.05
MODEL_RETRAIN_INTERVAL: 3600

# Alerting
WEBHOOK_URL: https://your-webhook-url
SLACK_WEBHOOK: https://hooks.slack.com/services/...
```

## Tests

```bash
# Unit tests (154 tests, Python 3.11/3.12/3.13)
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## CI/CD

GitHub Actions pipeline on every push and PR:

- Black + flake8 + mypy
- 154 unit tests on Python 3.11, 3.12, 3.13
- Bandit security scan
- Helm chart validation
- Multi-platform Docker build (AMD64/ARM64)
- Push to Docker Hub
- Trivy vulnerability scan

See [docs/CI-CD.md](docs/CI-CD.md) for details.

## Security

- Non-root user in the container
- Kubernetes RBAC with minimal permissions
- Secrets via environment variables (never committed)
- Automated vulnerability scanning (Trivy + Bandit)

## License

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0](LICENSE) — free for personal and educational use, commercial use upon request.

## Support

- Issues: [GitHub Issues](https://github.com/DamsDGN/kube-seer/issues)
- Discussions: [GitHub Discussions](https://github.com/DamsDGN/kube-seer/discussions)

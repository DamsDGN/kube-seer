# kube-seer

[![CI/CD Pipeline](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Intelligent SRE agent for Kubernetes — collects metrics, detects anomalies, correlates incidents, predicts resource saturation, and surfaces ML-based log insights before incidents escalate.

## Features

- **Multi-source collection**: Prometheus, Kubernetes Metrics Server, K8s API (14 resource types)
- **Resource state detection**: Static rules for Deployments, StatefulSets, DaemonSets, CronJobs, HPA, PVC, ResourceQuota, NetworkPolicy, Ingress, Node, Service, PDB, PersistentVolume, Namespace
- **Metrics anomaly detection**: Threshold rules + IsolationForest ML on CPU, memory, disk
- **Log collection**: Fluent Bit DaemonSet ships container logs to Elasticsearch (`sre-logs` index)
- **Log pattern detection**: ERROR/FATAL/WARN/OOM/crash pattern matching per pod (`source=logs`)
- **Log ML analysis**: Deployment-level error spike detection (two 5-min windows) + IsolationForest outlier detection per pod (`source=logs_ml`)
- **Incident correlation**: Groups related anomalies into coherent incidents
- **Saturation prediction**: Linear regression with configurable horizon
- **LLM intelligence**: Optional LLM analysis of detected anomalies — root cause suggestions and remediation steps. Works with any OpenAI-compatible API (OpenAI, Mistral, vLLM, LM Studio) or Anthropic. Supports **self-hosted models via Ollama** — your data never leaves the cluster.
- **Multi-channel alerting**: Alertmanager (primary) + Slack via `AlertmanagerConfig` + fallback webhook
- **Configurable exclusions**: Skip namespaces, deployments, statefulsets, daemonsets or pods from anomaly detection via Helm values
- **REST API**: Real-time access to anomalies, incidents, and predictions

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              SREAgent                                    │
│                                                                          │
│  ┌─────────────┐   ┌──────────────────────┐   ┌──────────────────────┐  │
│  │  Collectors │──►│      Analyzers       │──►│       Alerter        │  │
│  └─────────────┘   └──────────────────────┘   └──────────────────────┘  │
│        │                      │                          │               │
│   Prometheus          MetricsAnalyzer             Alertmanager           │
│   MetricsSrv          EventAnalyzer                  + Slack             │
│   K8s API (14)        LogAnalyzer               FallbackWebhook          │
│                       LogInsightAnalyzer                                 │
│                       ResourceStateAnalyzer    ┌──────────────────────┐  │
│                       Predictor               │  IntelligenceService  │  │
│                       Correlator              │  (optional LLM layer) │  │
└──────────────────────────────────────────────┴──────────────────────┴──┘
         │                                       │              │
   Elasticsearch                             REST API      LLM Provider
   sre-metrics                            /anomalies    (OpenAI / Mistral /
   sre-anomalies                          /incidents     Ollama / Anthropic)
   sre-logs (Fluent Bit)                  /predictions
```

## Collected resource types

| Category | Types |
|---|---|
| Workloads | Deployment, StatefulSet, DaemonSet, CronJob |
| Scaling | HPA |
| Storage | PVC, PersistentVolume |
| Networking | Service, Ingress, NetworkPolicy |
| Cluster | Node, Namespace, PodDisruptionBudget, ResourceQuota |

## Anomaly sources

| Source | Description | Severity |
|---|---|---|
| `metrics` | CPU/memory/disk thresholds exceeded | WARNING / CRITICAL |
| `metrics_ml` | IsolationForest on node/pod resource usage | WARNING |
| `events` | Kubernetes warning events (OOMKilled, BackOff…) | WARNING / CRITICAL |
| `logs` | ERROR_PATTERNS matched in pod logs | WARNING / CRITICAL |
| `logs_ml` | Error spike by Deployment or outlier pod log | WARNING / CRITICAL |
| `resources` | Resource state rules (NotReady, Pending, Terminating…) | WARNING / CRITICAL |

## Project structure

```
src/
├── agent.py              # Main orchestrator (collect → analyze → alert cycle)
├── config.py             # Configuration via environment variables
├── models.py             # Pydantic data models
├── main.py               # FastAPI entry point
├── analyzer/
│   ├── metrics.py        # Threshold + IsolationForest on CPU/memory/disk
│   ├── events.py         # Kubernetes event analysis
│   ├── logs.py           # ERROR_PATTERNS log detection (source=logs)
│   ├── log_insights.py   # Spike detection + outlier ML (source=logs_ml)
│   ├── resources.py      # Resource state rules for 14 K8s types
│   ├── correlator.py     # Anomaly → incident correlation
│   └── predictor.py      # Saturation prediction (linear regression)
├── alerter/
│   ├── alertmanager.py   # Prometheus Alertmanager
│   └── webhook.py        # Fallback generic webhook
├── collector/
│   ├── prometheus.py     # Prometheus metrics
│   ├── metrics_server.py # Kubernetes Metrics Server
│   └── k8s_api.py        # K8s API — 14 resource types + events + pod limits
├── storage/
│   └── elasticsearch.py  # Elasticsearch persistence (query + aggregate)
└── api/
    └── routes.py         # REST endpoints (FastAPI)

tests/
├── analyzer/             # Unit tests (metrics, events, logs, log_insights, resources…)
├── collector/            # Unit tests (k8s_api, prometheus, metrics_server)
├── alerter/              # Unit tests (alertmanager, webhook, service)
├── storage/              # Unit tests (elasticsearch)
├── integration/          # Integration tests against a live Kind cluster
│   ├── test_detection.py       # Full pipeline: collect → analyze → anomaly
│   ├── test_resource_states.py # Resource state scenarios (cordoned node, bad PVC…)
│   └── test_api.py             # REST API endpoints
└── ...                   # 259 unit tests + 29 integration tests

helm/kube-seer/           # Helm chart (Deployment, RBAC, AlertmanagerConfig…)
scripts/
├── kind-up.sh            # Local Kind cluster bootstrap (ES + Prometheus + Fluent Bit + kube-seer)
└── fluentbit-values.yaml # Fluent Bit Helm values for local log collection
docs/superpowers/         # Design specs and implementation plans
```

## Installation

### Prerequisites

- Python 3.11+
- Docker + Kind (for local testing)
- Helm 3.x

### External dependencies

kube-seer relies on the following infrastructure components — it does not deploy them itself:

| Component | Role | Required |
|---|---|---|
| **Elasticsearch 8.x** | Stores metrics, anomalies, and logs | Yes |
| **Prometheus** | Node and pod metrics collection | Recommended (falls back to Metrics Server) |
| **Kubernetes Metrics Server** | Pod/node resource usage | Recommended |
| **Alertmanager** | Alert routing (primary channel) | Yes, for alerting |
| **Prometheus Operator** | Provides the `AlertmanagerConfig` CRD used for Slack routing | Yes, if `alerter.slack.enabled=true` |
| **Fluent Bit** | Ships container logs to Elasticsearch (`sre-logs`) | Yes, for log analysis features |

> **Slack alerting** requires both Alertmanager and Prometheus Operator. The Helm chart creates an `AlertmanagerConfig` resource (a Prometheus Operator CRD) that routes `agent=kube-seer` alerts to your Slack channel. Without Prometheus Operator, set `alerter.slack.enabled=false` and configure your webhook directly in Alertmanager.

> **Log features** (`logs` and `logs_ml` anomaly sources) require Fluent Bit (or any compatible log shipper) to populate the `sre-logs` Elasticsearch index. Without logs, kube-seer still operates on metrics and resource states.

### Local development

```bash
git clone https://github.com/DamsDGN/kube-seer.git
cd kube-seer
make setup-dev          # create venv + install dependencies
source .venv/bin/activate
make test               # 259 unit tests
```

### Local Kind environment

Spins up a full local cluster: Elasticsearch, Prometheus, Grafana, Alertmanager, Fluent Bit, and kube-seer.

```bash
make kind-up            # bootstrap everything (~5 min)
make kind-reload        # rebuild and redeploy kube-seer only
make kind-down          # tear down the cluster
```

Optional features are enabled via environment variables — no interactive prompts:

```bash
# With Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... make kind-up

# With LLM intelligence (any OpenAI-compatible provider)
INTELLIGENCE_API_KEY=sk-...       \
INTELLIGENCE_API_URL=https://api.mistral.ai/v1 \
INTELLIGENCE_PROVIDER=openai      \
INTELLIGENCE_MODEL=mistral-small-latest \
make kind-up

# Self-hosted with Ollama (data stays on-cluster)
INTELLIGENCE_API_KEY=ollama       \
INTELLIGENCE_API_URL=http://ollama.ollama.svc:11434/v1 \
INTELLIGENCE_PROVIDER=openai      \
INTELLIGENCE_MODEL=llama3.2       \
make kind-up
```

| Service | URL | Credentials |
|---|---|---|
| kube-seer API | http://localhost:8080 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / prom-operator |
| Alertmanager | http://localhost:9093 | — |
| Kibana | http://localhost:5601 | elastic / \<from secret\> |

### Integration tests

Requires a running Kind cluster (`make kind-up`):

```bash
pytest tests/integration/ -v
```

### Helm deployment

```bash
# Minimal install
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring --create-namespace \
  --set elasticsearch.url=https://elasticsearch:9200 \
  --set elasticsearch.username=elastic \
  --set elasticsearch.password=your-password \
  --set elasticsearch.verifyTls=false

# With Slack notifications
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring --create-namespace \
  --set elasticsearch.url=https://elasticsearch:9200 \
  --set elasticsearch.username=elastic \
  --set elasticsearch.password=your-password \
  --set elasticsearch.verifyTls=false \
  --set alerter.slack.enabled=true \
  --set alerter.slack.webhookUrl=https://hooks.slack.com/services/... \
  --set alerter.slack.channel='#alerts'
```

> **Log collection:** Fluent Bit is not bundled in the Helm chart — it is an optional infrastructure component. Deploy it separately and point it at your Elasticsearch instance. Set `elasticsearch.indices.logs` to match your log index name (default: `sre-logs`).

## LLM Intelligence

kube-seer can optionally call an LLM to analyze detected anomalies and suggest root causes and remediation steps. The analysis runs once per detection cycle, deduplicated by anomaly fingerprint so the LLM is only called when the anomaly set changes.

### Supported providers

| Provider | `intelligence.provider` | `intelligence.apiUrl` example |
|---|---|---|
| **Ollama** (self-hosted) | `openai` | `http://ollama.ollama.svc:11434/v1` |
| **OpenAI** | `openai` | `https://api.openai.com/v1` |
| **Mistral** | `openai` | `https://api.mistral.ai/v1` |
| **vLLM / LM Studio** | `openai` | `http://vllm.svc:8000/v1` |
| **Anthropic** | `anthropic` | *(not required)* |

> **Self-hosted first**: Ollama lets you run models like `llama3.2`, `mistral`, or `qwen2.5` entirely on-cluster. Your metrics and log data never leave your infrastructure.

### Helm values

```bash
helm install kube-seer ./helm/kube-seer \
  --set intelligence.enabled=true \
  --set intelligence.provider=openai \
  --set intelligence.apiKey=sk-... \
  --set intelligence.apiUrl=https://api.mistral.ai/v1 \
  --set intelligence.model=mistral-small-latest
```

| Value | Default | Description |
|---|---|---|
| `intelligence.enabled` | `false` | Enable LLM analysis |
| `intelligence.provider` | `""` | `openai` or `anthropic` |
| `intelligence.apiKey` | `""` | API key (stored in a Kubernetes Secret) |
| `intelligence.apiUrl` | `""` | Base URL up to `/v1` (e.g. `https://api.mistral.ai/v1`) |
| `intelligence.model` | `""` | Model name (e.g. `mistral-small-latest`, `gpt-4o-mini`, `llama3.2`) |
| `intelligence.timeoutSeconds` | `60` | LLM request timeout |

## REST API

| Endpoint | Description |
|---|---|
| `GET /health` | Agent health |
| `GET /ready` | Readiness (checks ES, Prometheus) |
| `GET /status` | Full system status |
| `GET /anomalies` | Detected anomalies (filterable by severity/namespace/source) |
| `GET /incidents` | Correlated incidents |
| `GET /predictions` | Saturation predictions |
| `GET /alerts/stats` | Alert statistics |
| `POST /analyze` | Trigger a manual analysis cycle |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ELASTICSEARCH_URL` | — | **Required** |
| `ELASTICSEARCH_USERNAME` | `""` | |
| `ELASTICSEARCH_PASSWORD` | `""` | |
| `ELASTICSEARCH_INDICES_LOGS` | `sre-logs` | Log index name or pattern |
| `AGENT_ANALYSIS_INTERVAL` | `300` | Cycle interval in seconds |
| `THRESHOLDS_CPU_WARNING` | `70.0` | |
| `THRESHOLDS_CPU_CRITICAL` | `85.0` | |
| `THRESHOLDS_MEMORY_WARNING` | `70.0` | |
| `THRESHOLDS_MEMORY_CRITICAL` | `85.0` | |
| `THRESHOLDS_DISK_CRITICAL` | `90.0` | |
| `ML_ANOMALY_THRESHOLD` | `0.05` | IsolationForest contamination ratio |
| `ML_WINDOW_SIZE` | `100` | Rolling buffer size for ML training |
| `PREDICTION_HORIZON_HOURS` | `168` | Saturation prediction horizon (7 days) |
| `ALERTER_ALERTMANAGER_ENABLED` | `true` | |
| `ALERTER_ALERTMANAGER_URL` | `http://alertmanager:9093` | |
| `EXCLUSIONS_NAMESPACES` | `""` | Comma-separated namespaces to skip |
| `EXCLUSIONS_DEPLOYMENTS` | `""` | Comma-separated deployments (`name` or `namespace/name`) |
| `EXCLUSIONS_STATEFULSETS` | `""` | Comma-separated statefulsets |
| `EXCLUSIONS_DAEMONSETS` | `""` | Comma-separated daemonsets |
| `EXCLUSIONS_PODS` | `""` | Comma-separated pods |
| `INTELLIGENCE_ENABLED` | `false` | Enable LLM analysis |
| `INTELLIGENCE_PROVIDER` | `""` | `openai` or `anthropic` |
| `INTELLIGENCE_API_KEY` | `""` | LLM API key |
| `INTELLIGENCE_API_URL` | `""` | Base URL up to `/v1` |
| `INTELLIGENCE_MODEL` | `""` | Model name |
| `INTELLIGENCE_TIMEOUT_SECONDS` | `60` | LLM request timeout |

## Tests

```bash
# Unit tests (249 tests)
pytest tests/ --ignore=tests/integration -v

# Integration tests (29 tests — requires Kind cluster)
pytest tests/integration/ -v

# With coverage
pytest tests/ --ignore=tests/integration --cov=src --cov-report=html
```

## CI/CD

GitHub Actions pipeline on every push and PR:

- Black + flake8
- 259 unit tests on Python 3.11, 3.12, 3.13
- Bandit security scan
- Helm chart validation
- Multi-platform Docker build (AMD64/ARM64)
- Push to Docker Hub
- Trivy vulnerability scan

## Security

- Non-root container (UID 1001)
- Kubernetes RBAC with minimal permissions (get/list/watch only)
- Secrets via environment variables (never committed)
- Automated vulnerability scanning (Trivy + Bandit)

## License

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0](LICENSE) — free for personal and educational use, commercial use upon request.

## Support

- Issues: [GitHub Issues](https://github.com/DamsDGN/kube-seer/issues)
- Discussions: [GitHub Discussions](https://github.com/DamsDGN/kube-seer/discussions)

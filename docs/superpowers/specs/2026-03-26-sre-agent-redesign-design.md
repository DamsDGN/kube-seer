# EFK SRE Agent — Redesign Specification

## Overview

Redesign of the kube-seer from an EFK-stack monitoring tool into a **full Kubernetes cluster SRE agent** with intelligent monitoring capabilities. Elasticsearch serves solely as a storage backend for metrics, logs, and analysis results. The agent ensures **data sovereignty** by keeping all data under the client's control.

## Goals

- Monitor all Kubernetes cluster resources (nodes, pods, deployments, statefulsets, daemonsets, jobs, PV/PVC, HPA, events, RBAC, network policies, quotas, ingresses)
- Detect anomalies via ML (classical), correlate events, predict resource exhaustion
- Optional LLM integration for root cause analysis and natural language reports
- Deploy as a single lightweight agent per cluster via Helm
- Minimal performance impact on the monitored cluster

## Non-Goals

- Provisioning or managing Elasticsearch clusters
- Deploying Fluentd/Fluent Bit, Prometheus, or Alertmanager
- Providing a web UI or dashboard (clients use Kibana/Grafana as they see fit)
- Data anonymization before LLM calls (client responsibility to choose a compliant provider)
- Multi-cluster agent (one agent per cluster; clients aggregate via Elasticsearch/Kibana)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  kube-seer                   │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│  │ collector/ │  │ collector/ │  │ collector/ │  │
│  │ prometheus │  │ k8s_api    │  │ metrics_   │  │
│  │            │  │ (events,   │  │ server     │  │
│  │ (historical│  │  states,   │  │            │  │
│  │  metrics)  │  │  RBAC...)  │  │ (realtime) │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  │
│        └───────┬───────┴───────────────┘         │
│                ▼                                  │
│        ┌──────────────┐                          │
│        │   storage/   │◄──── Fluentd/FluentBit   │
│        │ elasticsearch│      (external logs)     │
│        └──────┬───────┘                          │
│               │                                  │
│        ┌──────▼───────┐    ┌──────────────────┐  │
│        │  analyzer/   │───►│  intelligence/   │  │
│        │  (classical  │    │  (optional LLM)  │  │
│        │   ML)        │◄───│                  │  │
│        └──────┬───────┘    └──────────────────┘  │
│               │                                  │
│        ┌──────▼───────┐                          │
│        │   alerter/   │                          │
│        │ Alertmanager │                          │
│        │ + fallback   │                          │
│        └──────────────┘                          │
│                                                  │
│        ┌──────────────┐                          │
│        │    api/      │  (FastAPI, /health,      │
│        │              │   /analyze, /config...)   │
│        └──────────────┘                          │
└─────────────────────────────────────────────────┘
```

### Data Flow

1. **Collectors** retrieve metrics (Prometheus, metrics-server) and states/events (Kubernetes API)
2. Fluentd/Fluent Bit pushes logs directly into Elasticsearch
3. **Storage** module reads/writes Elasticsearch (metrics, logs, analysis results)
4. **Analyzer** detects anomalies via classical ML
5. **Intelligence** (when enabled) enriches analysis: advanced correlation, root cause, reports
6. **Alerter** pushes to Alertmanager or falls back to webhooks
7. **API** exposes endpoints for querying and manual actions

### Design Principles

- **Lightweight**: single Deployment, no DaemonSet or sidecar. Passive collection via existing APIs.
- **Configurable polling**: analysis interval adjustable (default 300s).
- **Lightweight ML models**: Isolation Forest, DBSCAN — no deep learning, no GPU.
- **Strict resource limits**: low requests (100m CPU, 128Mi memory), memory limit 256Mi, no CPU limit.
- **Batch processing**: data processed in cycles, not streaming, to limit API server pressure.

---

## Module Structure

```
src/
├── collector/
│   ├── base.py              # Common Collector interface
│   ├── prometheus.py         # Metrics via PromQL
│   ├── k8s_api.py           # Events, states, RBAC, NetworkPolicies...
│   └── metrics_server.py    # Realtime metrics (CPU/mem per pod)
│
├── storage/
│   ├── base.py              # Storage interface
│   └── elasticsearch.py     # ES read/write (metrics, results)
│
├── analyzer/
│   ├── base.py              # Analyzer interface
│   ├── metrics.py           # Isolation Forest, anomaly detection
│   ├── logs.py              # TF-IDF + DBSCAN, pattern matching
│   └── correlator.py        # Metrics/logs/events correlation
│
├── intelligence/
│   ├── base.py              # LLMProvider interface (optional)
│   ├── providers/
│   │   ├── claude.py
│   │   ├── openai.py
│   │   └── ollama.py
│   └── engine.py            # LLM orchestration (correlation, RCA, reports)
│
├── alerter/
│   ├── base.py              # Alerter interface
│   ├── alertmanager.py      # Push to Alertmanager
│   └── webhook.py           # Fallback webhooks
│
├── api/
│   └── routes.py            # FastAPI endpoints
│
├── config.py                # Centralized configuration
├── models.py                # Dataclasses / Pydantic models
├── agent.py                 # Main orchestrator (analysis cycles)
└── main.py                  # Entrypoint
```

Each module exposes a base interface (`base.py`) enabling clean mocking in tests, swappable implementations, and clear contracts between modules.

---

## Data Collection

### Metrics (Prometheus + metrics-server)

- **Nodes**: CPU, memory, disk, network, pressure conditions (DiskPressure, MemoryPressure)
- **Pods**: CPU/memory per container, restarts, status (Pending, CrashLoopBackOff...)
- **HPA**: current utilization vs targets, scaling events
- **PV/PVC**: capacity, usage, binding state

### States and Events (Kubernetes API)

- Deployments, StatefulSets, DaemonSets: desired vs ready replicas, conditions
- Jobs/CronJobs: success, failures, duration
- Ingress: backend health
- NetworkPolicies: inventory (detect missing policies)
- RBAC: sensitive ClusterRoleBindings inventory
- Quotas: ResourceQuotas, LimitRanges, usage vs limits
- Kubernetes events: Warning events (FailedScheduling, OOMKilled, FailedMount...)

### Logs (via Elasticsearch, pushed by Fluentd)

- Application logs from pods
- System logs (kubelet, kube-apiserver, etc. if collected by Fluentd)

### Collection Cycle

- Configurable interval (default: 300s)
- Prometheus: PromQL queries over a sliding window
- metrics-server: realtime snapshot
- Kubernetes API: watch for events, periodic list for states
- Logs: ES query over the window since last cycle

---

## Intelligent Analysis Pipeline

### Layer 1 — Anomaly Detection (classical ML, always active)

- **Metrics**: Isolation Forest with extracted features (value, trend, seasonality, rolling std deviation). One model per resource type (node, pod, PV).
- **Logs**: TF-IDF + DBSCAN to detect unusual log clusters. Pattern matching for known errors (OOM, CrashLoop, FailedMount...).
- **Kubernetes events**: abnormal frequency detection (e.g., burst of Warning events).
- Auto-retraining on configurable sliding window.

### Layer 2 — Correlation (classical ML)

- Temporal correlation: anomalies close in time on related resources (e.g., pod OOM + node memory spike).
- Topological correlation: resource relationships (pod → node, pod → PVC, deployment → HPA).
- Aggregated severity score per incident.

### Layer 3 — Prediction (classical ML)

- Trend regression: disk saturation, memory growth, replica scaling.
- Predictive alerts: "PVC at 85%, estimated saturation in 48h".

### Layer 4 — Root Cause Analysis (LLM, optional)

- Receives structured context from layers 1-3 (anomalies, correlations, trends).
- Generates natural language analysis: probable cause, impact, recommendations.
- Prompt engineered with K8s context (topology, recent events).
- **Disabled by default.** Enabled via config (`intelligence.enabled: true` + provider + API key).

When LLM is disabled, layers 1-3 operate autonomously with structured reports (JSON) without natural language.

---

## Alerting

### Primary Mode — Alertmanager

- Agent pushes alerts in Prometheus format (labels, annotations, severity) to Alertmanager API (`/api/v2/alerts`).
- Client manages routing and notifications in their existing Alertmanager config.
- Standard labels: `agent=kube-seer`, `cluster=<name>`, `namespace`, `resource_type`, `severity` (critical, warning, info).

### Fallback Mode — Webhooks

- When Alertmanager is not configured or unreachable, agent sends alerts via generic webhook (POST JSON).
- Configurable in `values.yaml`: webhook URL.
- Built-in rate-limiting to prevent spam.

### Severities

- **Critical**: confirmed anomaly with immediate impact (OOM, node NotReady, CrashLoop)
- **Warning**: anomaly detected, needs monitoring (memory trend, CPU spike)
- **Info**: predictions, recommendations (estimated saturation, suggested scaling)

### Deduplication

- Alertmanager mode: handled natively by Alertmanager (grouping, inhibition).
- Fallback mode: local deduplication via hash (type + resource + severity), configurable cooldown (default: 5min).

---

## REST API

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (ES + Prometheus connectivity) |
| GET | `/status` | Agent state (last cycle, loaded models, LLM active/inactive) |
| GET | `/metrics` | Prometheus metrics of the agent itself |
| GET | `/anomalies` | Detected anomalies (filterable by namespace, severity, period) |
| GET | `/anomalies/{id}` | Anomaly detail + correlations |
| GET | `/predictions` | Active predictions (saturation, trends) |
| POST | `/analyze` | Trigger immediate manual analysis |
| POST | `/models/retrain` | Force ML model retraining |
| GET | `/config` | Active configuration (secrets excluded) |

- Readiness probe separated from health: agent is "ready" only if it can reach ES and at least one metrics source.
- `/anomalies` endpoint is paginated.
- When LLM is active, `/anomalies/{id}` includes natural language analysis if available.

---

## Helm Chart

### Deployed Resources

| K8s Resource | Role |
|--------------|------|
| Deployment | Agent pod (single replica) |
| ServiceAccount | Agent identity |
| ClusterRole + ClusterRoleBinding | Read-only RBAC (pods, nodes, events, deployments, statefulsets, daemonsets, jobs, pv/pvc, hpa, networkpolicies, resourcequotas, ingresses) |
| ConfigMap | Non-sensitive configuration |
| Secret | ES + LLM credentials (optional, or `secretRef` to existing Secret) |
| Service | Exposes the API (ClusterIP) |
| ServiceMonitor | Optional, if Prometheus Operator is present |
| PodDisruptionBudget | Eviction protection |

### Prerequisites (not managed by the chart)

- Elasticsearch accessible with indices created
- Fluentd/Fluent Bit configured to push logs to ES
- Prometheus and/or metrics-server available in the cluster
- Alertmanager (optional, webhook fallback otherwise)

### Configuration (`values.yaml`)

```yaml
# Agent
agent:
  analysisInterval: 300        # seconds between analysis cycles
  logLevel: INFO

# Elasticsearch (external prerequisite)
elasticsearch:
  url: ""                       # required
  username: ""
  password: ""
  secretRef: ""                 # alternative: reference to existing Secret
  indices:
    metrics: "sre-metrics"
    logs: "sre-logs"
    anomalies: "sre-anomalies"

# Collectors
collectors:
  prometheus:
    enabled: true
    url: "http://prometheus-server:9090"
  metricsServer:
    enabled: true
  kubernetesApi:
    enabled: true
    watchEvents: true

# Detection thresholds
thresholds:
  cpu:
    warning: 70
    critical: 85
  memory:
    warning: 70
    critical: 85
  disk:
    warning: 80
    critical: 90

# ML
ml:
  retrainInterval: 3600
  windowSize: 100
  anomalyThreshold: 0.05

# Intelligence (optional LLM)
intelligence:
  enabled: false
  provider: ""                  # claude, openai, ollama
  apiUrl: ""                    # for ollama/custom
  apiKey: ""
  apiKeySecretRef: ""           # alternative: reference to existing Secret
  model: ""                     # e.g. claude-sonnet-4-6, gpt-4o, llama3

# Alerting
alerter:
  alertmanager:
    enabled: true
    url: "http://alertmanager:9093"
  fallback:
    webhook:
      enabled: false
      url: ""

# Resources
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    memory: 256Mi
```

---

## Testing Strategy

### Unit Tests

- Each module tested via its base interface with mocks
- `collector/`: mock Prometheus, metrics-server, K8s API responses
- `storage/`: mock Elasticsearch client
- `analyzer/`: synthetic data, detection verification
- `intelligence/`: mock LLM responses, verify behavior when disabled
- `alerter/`: mock Alertmanager, verify webhook fallback

### Integration Tests

- Full agent with mocked external sources
- End-to-end analysis cycle: collect → analyze → alert
- Degraded mode verification (ES unreachable, Prometheus absent, LLM timeout)

### Not Tested in CI

- Real connections to ES, Prometheus, K8s (external prerequisites)
- Documented for manual execution on a dev cluster

---

## Incremental Delivery

| Phase | Content | Dependencies |
|-------|---------|--------------|
| **1 — Foundations** | Modular architecture, collectors (Prometheus, metrics-server, K8s API), ES storage, Helm chart, base API (`/health`, `/ready`, `/status`, `/config`) | — |
| **2 — Anomaly Detection** | Metrics analyzer (Isolation Forest), log analyzer (TF-IDF + DBSCAN), K8s event pattern matching, `/anomalies` endpoint | Phase 1 |
| **3 — Alerting** | Alertmanager + webhook fallback, severities, deduplication | Phase 2 |
| **4 — Correlation** | Temporal + topological correlation, aggregated severity score | Phase 2 |
| **5 — Prediction** | Trend regression, predictive alerts, `/predictions` endpoint | Phase 2 |
| **6 — Intelligence LLM** | Optional module, provider interface, root cause analysis, natural language reports | Phase 4 |

Each phase is a deliverable, testable increment. The product is functional from phase 3 onward.

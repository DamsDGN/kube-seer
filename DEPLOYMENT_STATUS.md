# kube-seer — Statut du projet

## État actuel

| Élément | Statut |
|---------|--------|
| Phases d'implémentation | 6/6 complètes |
| Tests unitaires | 154/154 (Python 3.11, 3.12, 3.13) |
| CI/CD | Opérationnel |
| Image Docker | `damsdgn29/kube-seer` |
| Chart Helm | `helm/kube-seer/` |

## Composants implémentés

### Collecte
- `collector/prometheus.py` — métriques nodes et pods via Prometheus
- `collector/metrics_server.py` — Kubernetes Metrics Server
- `collector/k8s_api.py` — events, resource states, pod limits, PVC, HPA, NetworkPolicy, ResourceQuota, Ingress

### Analyse
- `analyzer/metrics.py` — anomalies CPU/mémoire/disque (Z-score, IQR, seuils)
- `analyzer/events.py` — événements Kubernetes
- `analyzer/logs.py` — logs Elasticsearch
- `analyzer/correlator.py` — corrélation anomalies → incidents
- `analyzer/predictor.py` — prédiction de saturation (régression linéaire)

### Alerting
- `alerter/webhook.py` — webhook générique
- `alerter/alertmanager.py` — Prometheus Alertmanager
- `alerter/slack.py` — Slack
- `alerter/email.py` — Email SMTP

### API REST
- `GET /health` — santé
- `GET /ready` — disponibilité
- `GET /status` — statut complet
- `GET /anomalies` — anomalies détectées
- `GET /incidents` — incidents corrélés
- `GET /predictions` — prédictions de saturation
- `POST /analyze` — analyse manuelle

## Déploiement

### Helm (recommandé)

```bash
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring \
  --set elasticsearch.url=http://elasticsearch:9200 \
  --set prometheus.url=http://prometheus:9090
```

### Prérequis en production
- Elasticsearch (stockage des anomalies et prédictions)
- Prometheus (métriques nodes/pods)
- Kubernetes avec accès à l'API (RBAC configuré dans le chart)

## CI/CD

Pipeline GitHub Actions sur chaque PR vers `main` :

1. Tests unitaires (Python 3.11/3.12/3.13)
2. Black + flake8 + mypy
3. Bandit (scan sécurité code)
4. Helm lint + template
5. Build Docker (test sans push sur PR)
6. Push Docker Hub + scan Trivy (sur merge main)

---
*Mis à jour le 28 mars 2026*

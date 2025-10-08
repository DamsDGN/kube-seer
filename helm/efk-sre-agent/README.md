# Agent IA SRE EFK - Chart Helm

Ce chart Helm déploie l'Agent IA SRE pour l'analyse automatisée des métriques et logs de la stack EFK (Elasticsearch, Fluentd, Kibana).

## Prérequis

- Kubernetes 1.20+
- Helm 3.0+
- Cluster avec stack EFK déployée (ou du moins Elasticsearch)

## Installation

### Installation simple

```bash
# Ajouter le repo (si disponible)
helm repo add efk-sre https://damsdgn.github.io/efk-sre/

# Installer avec la configuration par défaut
helm install my-sre-agent efk-sre/efk-sre-agent
```

### Installation locale (développement)

```bash
# Depuis le répertoire du projet
helm install my-sre-agent ./helm/efk-sre-agent/
```

### Installation avec configuration personnalisée

```bash
# Créer un fichier values-custom.yaml
cat > values-custom.yaml << EOF
config:
  elasticsearch:
    url: "https://my-elasticsearch.example.com:9200"
    user: "my-user"
  analysis:
    interval: 180  # 3 minutes
  thresholds:
    cpu:
      warning: 60.0
      critical: 80.0

alerting:
  slack:
    enabled: true
    webhook: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"

ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: sre-agent.mydomain.com
      paths:
        - path: /
          pathType: Prefix

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 500m
    memory: 512Mi
EOF

# Installer avec la configuration personnalisée
helm install my-sre-agent ./helm/efk-sre-agent/ -f values-custom.yaml
```

## Configuration

### Elasticsearch

L'agent nécessite une connexion à Elasticsearch. Configurez l'URL et les credentials :

```yaml
config:
  elasticsearch:
    url: "http://elasticsearch.elastic-system.svc.cluster.local:9200"
    user: "elastic"
    passwordSecret: "elasticsearch-credentials"  # Secret contenant le mot de passe
    passwordKey: "password"
```

### Secrets

Après installation, configurez les secrets :

```bash
# Mot de passe Elasticsearch
kubectl create secret generic elasticsearch-credentials \
  --from-literal=password="your-elasticsearch-password"

# Webhook Slack (optionnel)
kubectl patch secret my-sre-agent-efk-sre-agent-secrets \
  -p='{"data":{"SLACK_WEBHOOK":"'$(echo -n "https://hooks.slack.com/your/webhook" | base64)'"}}'
```

### Monitoring

Pour activer le monitoring Prometheus :

```yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true  # Nécessite Prometheus Operator
  prometheusRule:
    enabled: true  # Crée des règles d'alerte
```

### Persistence

L'agent peut persister ses modèles ML :

```yaml
persistence:
  enabled: true
  size: 5Gi
  storageClass: "fast-ssd"
```

### Autoscaling

Pour l'autoscaling automatique :

```yaml
autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70
```

## Commandes utiles

```bash
# Voir le status
helm status my-sre-agent

# Mettre à jour
helm upgrade my-sre-agent ./helm/efk-sre-agent/ -f values-custom.yaml

# Désinstaller
helm uninstall my-sre-agent

# Voir les logs
kubectl logs -f deployment/my-sre-agent-efk-sre-agent

# Port-forward pour accéder à l'API
kubectl port-forward svc/my-sre-agent-efk-sre-agent 8080:8080
```

## API

Une fois déployé, l'agent expose une API REST sur le port 8080 :

- `GET /health` - Status de l'agent
- `GET /metrics` - Métriques Prometheus
- `POST /analyze/metrics` - Déclencher une analyse de métriques
- `POST /analyze/logs` - Déclencher une analyse de logs
- `GET /alerts` - Liste des alertes actives

## Troubleshooting

### L'agent ne se connecte pas à Elasticsearch

1. Vérifiez l'URL Elasticsearch :
   ```bash
   kubectl exec deployment/my-sre-agent-efk-sre-agent -- curl -I http://elasticsearch:9200
   ```

2. Vérifiez les credentials :
   ```bash
   kubectl get secret elasticsearch-credentials -o yaml
   ```

### Les modèles ML ne se sauvegardent pas

Vérifiez que la PVC est bien montée :
```bash
kubectl describe pod -l app.kubernetes.io/name=efk-sre-agent
```

### Pas d'alertes reçues

1. Vérifiez la configuration des webhooks
2. Consultez les logs pour les erreurs d'envoi
3. Testez manuellement l'endpoint d'alerte

## Values.yaml complet

Voir le fichier [values.yaml](values.yaml) pour toutes les options de configuration disponibles.
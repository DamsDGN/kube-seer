# Kind Local Environment — Design Spec

**Date:** 2026-03-28
**Scope:** Script de setup d'un environnement Kind complet pour tester kube-seer en local

---

## Objectif

Fournir un script unique `scripts/kind-up.sh` (+ cible `make kind-up` / `make kind-down`) permettant à n'importe quel contributeur de démarrer un cluster Kind complet avec toutes les dépendances nécessaires à kube-seer, sans aucune configuration manuelle.

---

## Composants déployés

| Composant | Namespace | Rôle |
|-----------|-----------|------|
| cert-manager | cert-manager | Requis par ECK pour les certificats TLS |
| ECK Operator | elastic-system | Opérateur Elasticsearch |
| Elasticsearch (single-node) | elastic-system | Stockage des anomalies et prédictions |
| kube-prometheus-stack | monitoring | Prometheus + Grafana + Alertmanager + node-exporter + kube-state-metrics |
| kube-seer | monitoring | L'agent (image buildée localement) |

---

## Architecture du cluster Kind

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kube-seer
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080   # kube-seer API
    hostPort: 8080
  - containerPort: 30090   # Prometheus
    hostPort: 9090
  - containerPort: 30300   # Grafana
    hostPort: 3000
  - containerPort: 30093   # Alertmanager
    hostPort: 9093
```

Les ports locaux exposés :
- `http://localhost:8080` — kube-seer API
- `http://localhost:9090` — Prometheus
- `http://localhost:3000` — Grafana (admin/admin)
- `http://localhost:9093` — Alertmanager

---

## Ressources allouées

Dimensionnement pour une machine avec 32 Go de RAM :

| Composant | CPU request | CPU limit | RAM request | RAM limit |
|-----------|-------------|-----------|-------------|-----------|
| Elasticsearch | 500m | 1 | 1Gi | 2Gi |
| Prometheus | 200m | 500m | 512Mi | 1Gi |
| Grafana | 100m | 200m | 128Mi | 256Mi |
| Alertmanager | 50m | 100m | 64Mi | 128Mi |
| kube-seer | 100m | 500m | 128Mi | 256Mi |

---

## Séquence de déploiement

`kind-up.sh` exécute les étapes suivantes dans l'ordre, avec attente de disponibilité entre chaque :

1. **Vérification des prérequis** — `kind`, `kubectl`, `helm`, `docker` installés
2. **Création du cluster Kind** — si le cluster `kube-seer` n'existe pas déjà
3. **Installation cert-manager** — attend `cert-manager` webhook disponible
4. **Installation ECK operator** — attend CRDs prêts
5. **Déploiement Elasticsearch** — attend `status.health: green`
6. **Installation kube-prometheus-stack** — attend Prometheus et Grafana disponibles
7. **Build de l'image kube-seer** — `docker build -t kube-seer:local .`
8. **Chargement de l'image dans Kind** — `kind load docker-image kube-seer:local`
9. **Déploiement kube-seer via Helm** — avec les URLs des dépendances
10. **Affichage du récapitulatif** — URLs d'accès, credentials

---

## Configuration kube-seer dans Kind

kube-seer est déployé avec les variables suivantes pointant vers les services internes :

```yaml
elasticsearch:
  url: http://elasticsearch-es-http.elastic-system.svc:9200
  username: elastic
  password: <récupéré depuis le secret ECK>

prometheus:
  url: http://kube-prometheus-stack-prometheus.monitoring.svc:9090

alertmanager:
  url: http://kube-prometheus-stack-alertmanager.monitoring.svc:9093
```

---

## Fichiers créés

```
scripts/
├── kind-up.sh      # Setup complet (cluster + stacks + kube-seer)
└── kind-down.sh    # Suppression du cluster

Makefile            # Ajout des cibles kind-up et kind-down
kind-config.yaml    # Mise à jour avec les port-mappings supplémentaires
```

Aucun fichier de values Helm n'est commité — les valeurs sont intégrées directement dans `kind-up.sh` via `--set` et here-docs inline.

---

## Stratégie de wait

Chaque étape utilise `kubectl wait` ou une boucle de polling :

```bash
# Exemple pour Elasticsearch
kubectl wait --for=jsonpath='{.status.health}'=green \
  elasticsearch/elasticsearch \
  -n elastic-system \
  --timeout=300s
```

En cas de timeout (300s par défaut), le script affiche l'état courant et s'arrête avec un message d'erreur explicite.

---

## `make kind-down`

Supprime le cluster Kind :
```bash
kind delete cluster --name kube-seer
```

---

## Non inclus dans cette version

- Fluentbit / Kibana (non requis par kube-seer)
- Multi-node Kind cluster
- Persistent volumes (données perdues à `kind-down`)
- Tests d'intégration automatisés (étape suivante)

# Kind Local Environment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fournir un script `scripts/kind-up.sh` et une cible `make kind-up` qui créent un cluster Kind complet avec Elasticsearch (ECK), kube-prometheus-stack et kube-seer déployés et fonctionnels.

**Architecture:** Un script bash unique orchestre la création du cluster Kind, l'installation des dépendances Helm dans l'ordre (cert-manager → ECK → Elasticsearch → kube-prometheus-stack → kube-seer), avec attente de disponibilité entre chaque étape. Les services sont exposés via NodePort sur des ports locaux fixes. Le chart Helm kube-seer est mis à jour pour supporter `nodePort` configurable.

**Tech Stack:** bash, kind, helm, kubectl, docker, cert-manager v1.14.5, ECK 2.11.1, Elasticsearch 8.13.0, kube-prometheus-stack (prometheus-community), kube-seer:local

---

## File Structure

```
kind-config.yaml                          # Mise à jour : port-mappings Prometheus/Grafana/Alertmanager
scripts/
├── kind-up.sh                            # Création : script setup complet
└── kind-down.sh                          # Création : suppression cluster
helm/kube-seer/
├── values.yaml                           # Mise à jour : ajout nodePort
└── templates/service.yaml               # Mise à jour : support nodePort
Makefile                                  # Mise à jour : cibles kind-up, kind-down, fix CLUSTER_NAME
Dockerfile                                # Mise à jour : labels (URLs obsolètes)
```

---

## Task 1 : kind-config.yaml — port-mappings complets

**Files:**
- Modify: `kind-config.yaml`

- [ ] **Step 1 : Remplacer le contenu de `kind-config.yaml`**

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kube-seer
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
  - containerPort: 30090
    hostPort: 9090
    protocol: TCP
  - containerPort: 30300
    hostPort: 3000
    protocol: TCP
  - containerPort: 30093
    hostPort: 9093
    protocol: TCP
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
```

- [ ] **Step 2 : Commit**

```bash
git add kind-config.yaml
git commit -m "feat(kind): add port-mappings for Prometheus, Grafana, Alertmanager"
```

---

## Task 2 : Helm chart kube-seer — support NodePort

**Files:**
- Modify: `helm/kube-seer/values.yaml`
- Modify: `helm/kube-seer/templates/service.yaml`

- [ ] **Step 1 : Mettre à jour `values.yaml`** — remplacer la section `service`:

```yaml
service:
  type: ClusterIP
  port: 8080
  nodePort: ""
```

- [ ] **Step 2 : Mettre à jour `helm/kube-seer/templates/service.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "kube-seer.fullname" . }}
  labels:
    {{- include "kube-seer.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
      {{- if and (eq .Values.service.type "NodePort") .Values.service.nodePort }}
      nodePort: {{ .Values.service.nodePort }}
      {{- end }}
  selector:
    {{- include "kube-seer.selectorLabels" . | nindent 4 }}
```

- [ ] **Step 3 : Vérifier que le template Helm est valide**

```bash
helm template test ./helm/kube-seer/ \
  --set service.type=NodePort \
  --set service.nodePort=30080 \
  --set elasticsearch.url=http://es:9200 | grep -A 10 "kind: Service"
```

Attendu : la section `nodePort: 30080` apparaît dans la sortie.

- [ ] **Step 4 : Commit**

```bash
git add helm/kube-seer/values.yaml helm/kube-seer/templates/service.yaml
git commit -m "feat(helm): add configurable nodePort to kube-seer service"
```

---

## Task 3 : Dockerfile — corriger les labels obsolètes

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1 : Mettre à jour les labels OCI dans `Dockerfile`**

Remplacer les lignes `LABEL` au début du fichier :

```dockerfile
LABEL org.opencontainers.image.title="kube-seer"
LABEL org.opencontainers.image.description="Agent SRE intelligent pour Kubernetes — détection d'anomalies, corrélation d'incidents, prédiction de saturation"
LABEL org.opencontainers.image.source="https://github.com/DamsDGN/kube-seer"
LABEL org.opencontainers.image.licenses="CC-BY-NC-SA-4.0"
```

- [ ] **Step 2 : Vérifier que l'image se build**

```bash
docker build -t kube-seer:test . --quiet
echo "Exit code: $?"
```

Attendu : `Exit code: 0`

- [ ] **Step 3 : Commit**

```bash
git add Dockerfile
git commit -m "chore: update Dockerfile labels for kube-seer"
```

---

## Task 4 : scripts/kind-up.sh — squelette et vérification des prérequis

**Files:**
- Create: `scripts/kind-up.sh`

- [ ] **Step 1 : Créer `scripts/kind-up.sh`** avec le squelette et la vérification des prérequis

```bash
#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# kube-seer — Kind local environment setup
# Usage: ./scripts/kind-up.sh
# ============================================================

CLUSTER_NAME="kube-seer"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_ELASTIC="elastic-system"
NAMESPACE_CERT_MANAGER="cert-manager"

CERT_MANAGER_VERSION="v1.14.5"
ECK_VERSION="2.11.1"
ES_VERSION="8.13.0"

COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[0;31m"
COLOR_RESET="\033[0m"

log_info()    { echo -e "${COLOR_GREEN}[INFO]${COLOR_RESET} $*"; }
log_warn()    { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
log_error()   { echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $*" >&2; }
log_section() { echo -e "\n${COLOR_GREEN}==== $* ====${COLOR_RESET}"; }

# ------------------------------------------------------------
check_prerequisites() {
    log_section "Vérification des prérequis"
    local missing=0

    for tool in kind kubectl helm docker; do
        if command -v "$tool" &>/dev/null; then
            log_info "$tool : $(${tool} version --short 2>/dev/null || ${tool} version 2>/dev/null | head -1)"
        else
            log_error "$tool n'est pas installé"
            missing=$((missing + 1))
        fi
    done

    if ! docker info &>/dev/null; then
        log_error "Docker daemon n'est pas démarré"
        missing=$((missing + 1))
    fi

    if [ "$missing" -gt 0 ]; then
        log_error "$missing prérequis manquants — abandon"
        exit 1
    fi

    log_info "Tous les prérequis sont satisfaits"
}

# ------------------------------------------------------------
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    log_info "Prêt à déployer (autres étapes à venir)"
}

main "$@"
```

- [ ] **Step 2 : Rendre le script exécutable et le tester**

```bash
chmod +x scripts/kind-up.sh
./scripts/kind-up.sh
```

Attendu : affichage des versions de kind, kubectl, helm, docker sans erreur.

- [ ] **Step 3 : Commit**

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add kind-up.sh skeleton with prerequisites check"
```

---

## Task 5 : kind-up.sh — création du cluster Kind

**Files:**
- Modify: `scripts/kind-up.sh`

- [ ] **Step 1 : Ajouter la fonction `setup_cluster`** dans `kind-up.sh`, avant `main()` :

```bash
# ------------------------------------------------------------
setup_cluster() {
    log_section "Cluster Kind"

    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_warn "Cluster '${CLUSTER_NAME}' existe déjà — réutilisation"
    else
        log_info "Création du cluster '${CLUSTER_NAME}'..."
        kind create cluster --name "${CLUSTER_NAME}" --config kind-config.yaml
        log_info "Cluster créé"
    fi

    kubectl cluster-info --context "kind-${CLUSTER_NAME}"
}
```

- [ ] **Step 2 : Appeler `setup_cluster` dans `main()`**

Remplacer le corps de `main()` :

```bash
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    log_info "Cluster prêt"
}
```

- [ ] **Step 3 : Tester la création du cluster**

```bash
./scripts/kind-up.sh
kubectl get nodes
```

Attendu : un nœud `kube-seer-control-plane` en état `Ready`.

- [ ] **Step 4 : Nettoyer pour la suite**

```bash
kind delete cluster --name kube-seer
```

- [ ] **Step 5 : Commit**

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add cluster creation to kind-up.sh"
```

---

## Task 6 : kind-up.sh — cert-manager + ECK + Elasticsearch

**Files:**
- Modify: `scripts/kind-up.sh`

- [ ] **Step 1 : Ajouter les fonctions `install_cert_manager`, `install_eck`, `install_elasticsearch`** avant `main()` :

```bash
# ------------------------------------------------------------
install_cert_manager() {
    log_section "cert-manager ${CERT_MANAGER_VERSION}"

    helm repo add jetstack https://charts.jetstack.io --force-update
    helm upgrade --install cert-manager jetstack/cert-manager \
        --namespace "${NAMESPACE_CERT_MANAGER}" \
        --create-namespace \
        --version "${CERT_MANAGER_VERSION}" \
        --set installCRDs=true \
        --wait \
        --timeout 120s

    log_info "cert-manager prêt"
}

# ------------------------------------------------------------
install_eck() {
    log_section "ECK Operator ${ECK_VERSION}"

    helm repo add elastic https://helm.elastic.co --force-update
    helm upgrade --install elastic-operator elastic/eck-operator \
        --namespace "${NAMESPACE_ELASTIC}" \
        --create-namespace \
        --version "${ECK_VERSION}" \
        --wait \
        --timeout 120s

    log_info "ECK operator prêt"
}

# ------------------------------------------------------------
install_elasticsearch() {
    log_section "Elasticsearch ${ES_VERSION}"

    kubectl apply -f - <<EOF
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: elasticsearch
  namespace: ${NAMESPACE_ELASTIC}
spec:
  version: ${ES_VERSION}
  nodeSets:
  - name: default
    count: 1
    config:
      node.store.allow_mmap: false
    podTemplate:
      spec:
        containers:
        - name: elasticsearch
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "1"
              memory: 2Gi
    volumeClaimTemplates:
    - metadata:
        name: elasticsearch-data
      spec:
        accessModes:
        - ReadWriteOnce
        resources:
          requests:
            storage: 10Gi
EOF

    log_info "Attente qu'Elasticsearch soit green (jusqu'à 5 minutes)..."
    local attempts=0
    until kubectl get elasticsearch elasticsearch -n "${NAMESPACE_ELASTIC}" \
        -o jsonpath='{.status.health}' 2>/dev/null | grep -q "green"; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 60 ]; then
            log_error "Timeout : Elasticsearch n'est pas green après 5 minutes"
            kubectl get elasticsearch -n "${NAMESPACE_ELASTIC}"
            exit 1
        fi
        sleep 5
    done

    log_info "Elasticsearch green"
}
```

- [ ] **Step 2 : Mettre à jour `main()`**

```bash
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    install_cert_manager
    install_eck
    install_elasticsearch
    log_info "Stack Elasticsearch prête"
}
```

- [ ] **Step 3 : Tester jusqu'à Elasticsearch**

```bash
./scripts/kind-up.sh
kubectl get elasticsearch -n elastic-system
```

Attendu : `elasticsearch` avec `HEALTH=green` et `PHASE=Ready`.

- [ ] **Step 4 : Commit** (garder le cluster pour la tâche suivante)

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add cert-manager, ECK and Elasticsearch to kind-up.sh"
```

---

## Task 7 : kind-up.sh — kube-prometheus-stack

**Files:**
- Modify: `scripts/kind-up.sh`

- [ ] **Step 1 : Ajouter la fonction `install_prometheus`** avant `main()` :

```bash
# ------------------------------------------------------------
install_prometheus() {
    log_section "kube-prometheus-stack"

    helm repo add prometheus-community \
        https://prometheus-community.github.io/helm-charts --force-update

    helm upgrade --install kube-prometheus-stack \
        prometheus-community/kube-prometheus-stack \
        --namespace "${NAMESPACE_MONITORING}" \
        --create-namespace \
        --set prometheus.service.type=NodePort \
        --set prometheus.service.nodePort=30090 \
        --set grafana.service.type=NodePort \
        --set grafana.service.nodePort=30300 \
        --set "alertmanager.service.type=NodePort" \
        --set "alertmanager.service.nodePort=30093" \
        --set prometheus.prometheusSpec.resources.requests.cpu=200m \
        --set prometheus.prometheusSpec.resources.requests.memory=512Mi \
        --set "prometheus.prometheusSpec.resources.limits.memory=1Gi" \
        --set grafana.resources.requests.cpu=100m \
        --set grafana.resources.requests.memory=128Mi \
        --set "grafana.resources.limits.memory=256Mi" \
        --set alertmanager.alertmanagerSpec.resources.requests.cpu=50m \
        --set alertmanager.alertmanagerSpec.resources.requests.memory=64Mi \
        --set "alertmanager.alertmanagerSpec.resources.limits.memory=128Mi" \
        --wait \
        --timeout 300s

    log_info "kube-prometheus-stack prêt"
}
```

- [ ] **Step 2 : Mettre à jour `main()`**

```bash
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    install_cert_manager
    install_eck
    install_elasticsearch
    install_prometheus
    log_info "Stack Prometheus prête"
}
```

- [ ] **Step 3 : Tester**

```bash
./scripts/kind-up.sh
kubectl get pods -n monitoring | grep -E "prometheus|grafana|alertmanager"
```

Attendu : tous les pods en état `Running`.

- [ ] **Step 4 : Vérifier les ports locaux**

```bash
curl -s http://localhost:9090/-/ready && echo "Prometheus OK"
curl -s http://localhost:3000/api/health | grep -q "ok" && echo "Grafana OK"
```

- [ ] **Step 5 : Commit**

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add kube-prometheus-stack to kind-up.sh"
```

---

## Task 8 : kind-up.sh — build, load et déploiement de kube-seer

**Files:**
- Modify: `scripts/kind-up.sh`

- [ ] **Step 1 : Ajouter la fonction `deploy_kube_seer`** avant `main()` :

```bash
# ------------------------------------------------------------
deploy_kube_seer() {
    log_section "kube-seer"

    # Récupérer le mot de passe Elasticsearch depuis le secret ECK
    local es_password
    es_password=$(kubectl get secret elasticsearch-es-elastic-user \
        -n "${NAMESPACE_ELASTIC}" \
        -o jsonpath='{.data.elastic}' | base64 -d)

    # Build de l'image locale
    log_info "Build de l'image kube-seer:local..."
    docker build -t kube-seer:local . --quiet

    # Chargement dans Kind
    log_info "Chargement de l'image dans Kind..."
    kind load docker-image kube-seer:local --name "${CLUSTER_NAME}"

    # Déploiement Helm
    log_info "Déploiement Helm kube-seer..."
    helm upgrade --install kube-seer ./helm/kube-seer \
        --namespace "${NAMESPACE_MONITORING}" \
        --create-namespace \
        --set image.repository=kube-seer \
        --set image.tag=local \
        --set image.pullPolicy=Never \
        --set elasticsearch.url="http://elasticsearch-es-http.${NAMESPACE_ELASTIC}.svc:9200" \
        --set elasticsearch.username=elastic \
        --set "elasticsearch.password=${es_password}" \
        --set collectors.prometheus.url="http://kube-prometheus-stack-prometheus.${NAMESPACE_MONITORING}.svc:9090" \
        --set alerter.alertmanager.url="http://kube-prometheus-stack-alertmanager.${NAMESPACE_MONITORING}.svc:9093" \
        --set service.type=NodePort \
        --set service.nodePort=30080 \
        --wait \
        --timeout 120s

    log_info "kube-seer déployé"
}
```

- [ ] **Step 2 : Mettre à jour `main()`**

```bash
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    install_cert_manager
    install_eck
    install_elasticsearch
    install_prometheus
    deploy_kube_seer
    log_info "Déploiement complet"
}
```

- [ ] **Step 3 : Tester**

```bash
./scripts/kind-up.sh
kubectl get pods -n monitoring -l app.kubernetes.io/name=kube-seer
```

Attendu : pod kube-seer en état `Running`.

- [ ] **Step 4 : Vérifier l'API**

```bash
curl -s http://localhost:8080/health | python3 -m json.tool
```

Attendu : `{"status": "healthy", ...}`

- [ ] **Step 5 : Commit**

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add kube-seer build, load and deploy to kind-up.sh"
```

---

## Task 9 : kind-up.sh — récapitulatif final

**Files:**
- Modify: `scripts/kind-up.sh`

- [ ] **Step 1 : Ajouter la fonction `print_summary`** avant `main()` :

```bash
# ------------------------------------------------------------
print_summary() {
    log_section "Environnement prêt"
    echo ""
    echo "  kube-seer API   : http://localhost:8080"
    echo "  Prometheus      : http://localhost:9090"
    echo "  Grafana         : http://localhost:3000  (admin / prom-operator)"
    echo "  Alertmanager    : http://localhost:9093"
    echo ""
    echo "  kubectl context : kind-${CLUSTER_NAME}"
    echo ""
    echo "  Pour supprimer : make kind-down"
    echo ""
}
```

- [ ] **Step 2 : Appeler `print_summary` à la fin de `main()`**

```bash
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    install_cert_manager
    install_eck
    install_elasticsearch
    install_prometheus
    deploy_kube_seer
    print_summary
}
```

- [ ] **Step 3 : Commit**

```bash
git add scripts/kind-up.sh
git commit -m "feat(kind): add summary output to kind-up.sh"
```

---

## Task 10 : scripts/kind-down.sh

**Files:**
- Create: `scripts/kind-down.sh`

- [ ] **Step 1 : Créer `scripts/kind-down.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="kube-seer"

echo "Suppression du cluster Kind '${CLUSTER_NAME}'..."

if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '${CLUSTER_NAME}' introuvable — rien à faire"
    exit 0
fi

kind delete cluster --name "${CLUSTER_NAME}"
echo "Cluster '${CLUSTER_NAME}' supprimé"
```

- [ ] **Step 2 : Rendre le script exécutable**

```bash
chmod +x scripts/kind-down.sh
```

- [ ] **Step 3 : Tester**

```bash
./scripts/kind-down.sh
kind get clusters
```

Attendu : `kube-seer` n'apparaît plus dans la liste.

- [ ] **Step 4 : Commit**

```bash
git add scripts/kind-down.sh
git commit -m "feat(kind): add kind-down.sh"
```

---

## Task 11 : Makefile — cibles kind-up et kind-down

**Files:**
- Modify: `Makefile`

- [ ] **Step 1 : Corriger `CLUSTER_NAME` et ajouter les cibles Kind**

Dans le `Makefile`, remplacer `CLUSTER_NAME := efk-sre-agent` par `CLUSTER_NAME := kube-seer`.

Puis ajouter les cibles suivantes (après les cibles `deploy-helm` existantes) :

```makefile
kind-up: ## Lance l'environnement Kind complet (cluster + ES + Prometheus + kube-seer)
	@chmod +x scripts/kind-up.sh
	./scripts/kind-up.sh

kind-down: ## Supprime le cluster Kind
	@chmod +x scripts/kind-down.sh
	./scripts/kind-down.sh

kind-reload: ## Rebuild et recharge kube-seer dans Kind sans recréer le cluster
	@echo "Rebuild et rechargement de kube-seer..."
	docker build -t kube-seer:local . --quiet
	kind load docker-image kube-seer:local --name kube-seer
	kubectl rollout restart deployment/kube-seer -n monitoring
	kubectl rollout status deployment/kube-seer -n monitoring
```

Ajouter aussi `kind-up kind-down kind-reload` à la ligne `.PHONY` en haut du fichier.

- [ ] **Step 2 : Vérifier que les cibles apparaissent dans l'aide**

```bash
make help | grep kind
```

Attendu : les 3 cibles `kind-up`, `kind-down`, `kind-reload` s'affichent.

- [ ] **Step 3 : Commit**

```bash
git add Makefile
git commit -m "feat(kind): add kind-up, kind-down, kind-reload to Makefile"
```

---

## Task 12 : Test end-to-end complet

- [ ] **Step 1 : Lancer le setup complet depuis zéro**

```bash
make kind-up
```

Attendu : script complet sans erreur, récapitulatif affiché.

- [ ] **Step 2 : Vérifier tous les pods**

```bash
kubectl get pods -A | grep -v "Running\|Completed"
```

Attendu : aucun pod en état `Error`, `CrashLoopBackOff` ou `Pending`.

- [ ] **Step 3 : Vérifier l'API kube-seer**

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/status
curl -s http://localhost:8080/anomalies
curl -s http://localhost:8080/predictions
```

Attendu : réponses JSON valides sur chaque endpoint.

- [ ] **Step 4 : Vérifier Prometheus scrape kube-seer**

```bash
curl -s "http://localhost:9090/api/v1/targets" | \
  python3 -c "import sys,json; targets=json.load(sys.stdin)['data']['activeTargets']; \
  [print(t['labels']['job'], t['health']) for t in targets if 'kube-seer' in str(t)]"
```

Attendu : kube-seer apparaît avec `health=up`.

- [ ] **Step 5 : Tester kind-down**

```bash
make kind-down
kind get clusters
```

Attendu : `kube-seer` absent de la liste.

- [ ] **Step 6 : Push et PR**

```bash
git push -u origin chore/kind-local-env
```

Ouvrir une PR vers `main`.

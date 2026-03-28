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

# ------------------------------------------------------------
main() {
    log_section "kube-seer — Setup environnement Kind"
    check_prerequisites
    setup_cluster
    install_cert_manager
    install_eck
    install_elasticsearch
    log_info "Stack Elasticsearch prête"
}

main "$@"

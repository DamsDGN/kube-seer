#!/bin/bash

set -euo pipefail

echo "🔧 Installation des CRDs Prometheus..."

# Vérifier si les CRDs existent déjà
if kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1 && \
   kubectl get crd prometheusrules.monitoring.coreos.com >/dev/null 2>&1; then
    echo "✅ CRDs Prometheus déjà installés"
    exit 0
fi

# Version plus ancienne et stable des CRDs
PROMETHEUS_OPERATOR_VERSION="v0.60.1"
CRDS_URL="https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/${PROMETHEUS_OPERATOR_VERSION}/example/prometheus-operator-crd"

echo "📦 Téléchargement et installation des CRDs essentiels..."

# Créer un répertoire temporaire
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

cd "$TEMP_DIR"

# Télécharger et installer seulement les CRDs nécessaires
echo "📋 Installation du CRD ServiceMonitor..."
if ! kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
    curl -sL "${CRDS_URL}/monitoring.coreos.com_servicemonitors.yaml" -o servicemonitors.yaml
    kubectl apply -f servicemonitors.yaml
    echo "✅ ServiceMonitor CRD installé"
else
    echo "✅ ServiceMonitor CRD déjà présent"
fi

echo "📋 Installation du CRD PrometheusRule..."
if ! kubectl get crd prometheusrules.monitoring.coreos.com >/dev/null 2>&1; then
    curl -sL "${CRDS_URL}/monitoring.coreos.com_prometheusrules.yaml" -o prometheusrules.yaml
    kubectl apply -f prometheusrules.yaml
    echo "✅ PrometheusRule CRD installé"
else
    echo "✅ PrometheusRule CRD déjà présent"
fi

# Ne pas installer les CRDs Prometheus et Alertmanager car ils ne sont pas nécessaires
# et peuvent avoir des annotations trop longues

echo "✅ CRDs essentiels installés avec succès"

# Attendre que les CRDs soient prêts
echo "⏳ Attente de la disponibilité des CRDs..."
kubectl wait --for condition=established --timeout=60s crd/servicemonitors.monitoring.coreos.com
kubectl wait --for condition=established --timeout=60s crd/prometheusrules.monitoring.coreos.com

echo "✅ CRDs Prometheus prêts pour l'utilisation"

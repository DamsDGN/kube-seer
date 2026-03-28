#!/bin/bash

set -euo pipefail

echo "🔍 Vérification de l'état du déploiement..."

# Vérifier que le namespace existe
if ! kubectl get namespace monitoring >/dev/null 2>&1; then
    echo "❌ Namespace 'monitoring' n'existe pas"
    exit 1
fi

# Vérifier les CRDs
echo "🔧 Vérification des CRDs Prometheus..."
if ! kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
    echo "❌ CRD ServiceMonitor manquant"
    exit 1
fi

if ! kubectl get crd prometheusrules.monitoring.coreos.com >/dev/null 2>&1; then
    echo "❌ CRD PrometheusRule manquant"
    exit 1
fi

echo "✅ CRDs Prometheus présents"

# Vérifier le déploiement
echo "📦 Vérification du déploiement..."
if ! kubectl get deployment kube-seer -n monitoring >/dev/null 2>&1; then
    echo "❌ Déploiement kube-seer non trouvé"
    exit 1
fi

# Vérifier que les pods sont en cours d'exécution
echo "🏃 Vérification des pods..."
kubectl wait --for=condition=available --timeout=300s deployment/kube-seer -n monitoring

echo "✅ Déploiement vérifié avec succès !"

# Afficher l'état final
kubectl get pods -n monitoring -l app=kube-seer

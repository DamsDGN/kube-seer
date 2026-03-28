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

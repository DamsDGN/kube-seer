#!/bin/bash

# Script d'aide pour le déploiement Helm de l'agent SRE EFK
# Usage: ./helm-deploy.sh [command] [options]

set -e

CHART_PATH="./helm/kube-seer"
RELEASE_NAME="kube-seer"
NAMESPACE="monitoring"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction d'aide
show_help() {
    echo -e "${BLUE}🚀 Agent IA SRE EFK - Déploiement Helm${NC}"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  install         Installe l'agent avec la configuration par défaut"
    echo "  install-dev     Installe l'agent en mode développement"
    echo "  install-prod    Installe l'agent en mode production"
    echo "  upgrade         Met à jour l'agent existant"
    echo "  uninstall       Désinstalle l'agent"
    echo "  status          Affiche le statut du déploiement"
    echo "  test            Teste la connectivité de l'agent"
    echo "  logs            Affiche les logs de l'agent"
    echo "  port-forward    Forward le port pour accès local"
    echo "  lint            Valide le chart Helm"
    echo "  template        Génère les manifests sans déployer"
    echo ""
    echo "Options:"
    echo "  -n, --namespace NAMESPACE    Namespace à utiliser (défaut: monitoring)"
    echo "  -r, --release RELEASE        Nom du release (défaut: kube-seer)"
    echo "  -f, --values FILE           Fichier values.yaml personnalisé"
    echo "  --dry-run                   Simulation sans déploiement réel"
    echo "  -h, --help                  Affiche cette aide"
    echo ""
    echo "Exemples:"
    echo "  $0 install                   # Installation basique"
    echo "  $0 install-dev               # Installation pour développement"
    echo "  $0 install -f my-values.yaml # Installation avec configuration personnalisée"
    echo "  $0 status                    # Vérifier le statut"
    echo "  $0 logs                      # Voir les logs"
}

# Vérification des prérequis
check_prereqs() {
    if ! command -v helm &> /dev/null; then
        echo -e "${RED}❌ Helm n'est pas installé${NC}"
        echo "Installation: https://helm.sh/docs/intro/install/"
        exit 1
    fi

    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ kubectl n'est pas installé${NC}"
        exit 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}❌ Impossible de se connecter au cluster Kubernetes${NC}"
        exit 1
    fi

    if [ ! -d "$CHART_PATH" ]; then
        echo -e "${RED}❌ Chart Helm non trouvé: $CHART_PATH${NC}"
        exit 1
    fi
}

# Installation
install_agent() {
    local values_file="$1"
    local dry_run="$2"

    echo -e "${BLUE}🚀 Installation de l'agent SRE EFK...${NC}"

    local cmd="helm upgrade --install $RELEASE_NAME $CHART_PATH"
    cmd="$cmd --create-namespace --namespace $NAMESPACE"
    cmd="$cmd --wait --timeout 10m"

    if [ -n "$values_file" ]; then
        cmd="$cmd --values $values_file"
    fi

    if [ "$dry_run" = "true" ]; then
        cmd="$cmd --dry-run"
    fi

    echo -e "${YELLOW}Commande: $cmd${NC}"
    eval $cmd

    if [ "$dry_run" != "true" ]; then
        echo -e "${GREEN}✅ Agent installé avec succès!${NC}"
        echo ""
        echo -e "${YELLOW}Commandes utiles:${NC}"
        echo "  Status:       $0 status"
        echo "  Logs:         $0 logs"
        echo "  Port-forward: $0 port-forward"
        echo "  API Health:   curl http://localhost:8080/health"
    fi
}

# Statut
show_status() {
    echo -e "${BLUE}📊 Statut du déploiement${NC}"
    echo ""

    if helm list -n $NAMESPACE | grep -q $RELEASE_NAME; then
        echo -e "${GREEN}✅ Release Helm trouvé${NC}"
        helm status $RELEASE_NAME -n $NAMESPACE
        echo ""
        echo -e "${BLUE}📋 Pods:${NC}"
        kubectl get pods -n $NAMESPACE -l app.kubernetes.io/instance=$RELEASE_NAME
        echo ""
        echo -e "${BLUE}🌐 Services:${NC}"
        kubectl get svc -n $NAMESPACE -l app.kubernetes.io/instance=$RELEASE_NAME
    else
        echo -e "${RED}❌ Release non trouvé${NC}"
        exit 1
    fi
}

# Logs
show_logs() {
    echo -e "${BLUE}📝 Logs de l'agent${NC}"
    kubectl logs -f -n $NAMESPACE -l app.kubernetes.io/instance=$RELEASE_NAME
}

# Port forward
port_forward() {
    echo -e "${BLUE}🌐 Port-forward vers l'agent${NC}"
    echo -e "${YELLOW}API accessible sur: http://localhost:8080${NC}"
    echo -e "${YELLOW}Appuyer Ctrl+C pour arrêter${NC}"
    kubectl port-forward -n $NAMESPACE svc/$RELEASE_NAME-kube-seer 8080:8080
}

# Test de connectivité
test_agent() {
    echo -e "${BLUE}🧪 Test de l'agent${NC}"

    echo "Port-forward temporaire..."
    kubectl port-forward -n $NAMESPACE svc/$RELEASE_NAME-kube-seer 8080:8080 &
    PF_PID=$!

    sleep 5

    echo "Test de l'endpoint health..."
    if curl -s http://localhost:8080/health > /dev/null; then
        echo -e "${GREEN}✅ Agent accessible et fonctionnel${NC}"
    else
        echo -e "${RED}❌ Agent non accessible${NC}"
    fi

    kill $PF_PID 2>/dev/null || true
}

# Parse des arguments
DRY_RUN="false"
VALUES_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        -f|--values)
            VALUES_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        install)
            check_prereqs
            install_agent "$VALUES_FILE" "$DRY_RUN"
            exit 0
            ;;
        install-dev)
            check_prereqs
            install_agent "$CHART_PATH/examples/values-dev.yaml" "$DRY_RUN"
            exit 0
            ;;
        install-prod)
            check_prereqs
            install_agent "$CHART_PATH/examples/values-prod.yaml" "$DRY_RUN"
            exit 0
            ;;
        upgrade)
            check_prereqs
            install_agent "$VALUES_FILE" "$DRY_RUN"
            exit 0
            ;;
        uninstall)
            check_prereqs
            echo -e "${BLUE}🗑️  Désinstallation de l'agent${NC}"
            helm uninstall $RELEASE_NAME -n $NAMESPACE
            echo -e "${GREEN}✅ Agent désinstallé${NC}"
            exit 0
            ;;
        status)
            check_prereqs
            show_status
            exit 0
            ;;
        logs)
            check_prereqs
            show_logs
            exit 0
            ;;
        port-forward)
            check_prereqs
            port_forward
            exit 0
            ;;
        test)
            check_prereqs
            test_agent
            exit 0
            ;;
        lint)
            check_prereqs
            echo -e "${BLUE}🔍 Validation du chart Helm${NC}"
            helm lint $CHART_PATH
            exit 0
            ;;
        template)
            check_prereqs
            echo -e "${BLUE}📄 Génération des manifests${NC}"
            helm template $RELEASE_NAME $CHART_PATH --namespace $NAMESPACE
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Commande inconnue: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Afficher l'aide si aucune commande n'est fournie
show_help

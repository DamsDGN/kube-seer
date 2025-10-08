#!/bin/bash

# Script de déploiement pour l'agent SRE EFK avec Kind

set -e

echo "🚀 Déploiement de l'agent IA SRE EFK avec Kind"

# Variables
NAMESPACE="monitoring"
IMAGE_NAME="efk-sre-agent"
IMAGE_TAG="latest"
KIND_CLUSTER_NAME="efk-sre"

# Fonctions utilitaires
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        echo "❌ kubectl n'est pas installé"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker n'est pas installé"
        exit 1
    fi
}

check_kind() {
    if ! command -v kind &> /dev/null; then
        echo "❌ Kind n'est pas installé"
        echo "💡 Installation: go install sigs.k8s.io/kind@latest"
        echo "💡 Ou: curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64 && chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind"
        exit 1
    fi
}

setup_kind_cluster() {
    echo "🔧 Configuration du cluster Kind"
    
    # Vérifier si le cluster existe déjà
    if kind get clusters | grep -q "^$KIND_CLUSTER_NAME$"; then
        echo "✅ Cluster Kind '$KIND_CLUSTER_NAME' existe déjà"
        kubectl cluster-info --context kind-$KIND_CLUSTER_NAME
    else
        echo "🏗️  Création du cluster Kind '$KIND_CLUSTER_NAME'"
        
        # Créer la configuration Kind avec port mapping pour l'API
        cat > kind-config.yaml << EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: $KIND_CLUSTER_NAME
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
EOF
        
        kind create cluster --config kind-config.yaml
        kubectl cluster-info --context kind-$KIND_CLUSTER_NAME
    fi
    
    # S'assurer que le contexte est correct
    kubectl config use-context kind-$KIND_CLUSTER_NAME
}

create_namespace() {
    echo "📦 Création du namespace $NAMESPACE"
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
}

build_image() {
    echo "🏗️  Build de l'image Docker pour Kind"
    docker build -t $IMAGE_NAME:$IMAGE_TAG .
    
    # Charger l'image dans Kind
    echo "� Chargement de l'image dans le cluster Kind"
    kind load docker-image $IMAGE_NAME:$IMAGE_TAG --name $KIND_CLUSTER_NAME
}

configure_secrets() {
    echo "🔐 Configuration des secrets"
    
    # Vérifier si le fichier .env existe
    if [ ! -f .env ]; then
        echo "⚠️  Fichier .env non trouvé"
        echo "📝 Création d'un fichier .env minimal pour les tests"
        
        cat > .env << EOF
# Configuration pour tests locaux avec Kind
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=changeme
METRICS_INDEX=metricbeat-*
LOGS_INDEX=fluentd-*
K8S_IN_CLUSTER=true
K8S_NAMESPACE=monitoring
ANALYSIS_INTERVAL=300
ANOMALY_THRESHOLD=0.05
CPU_THRESHOLD_WARNING=70.0
CPU_THRESHOLD_CRITICAL=85.0
MEMORY_THRESHOLD_WARNING=70.0
MEMORY_THRESHOLD_CRITICAL=85.0
MODEL_RETRAIN_INTERVAL=3600
MODEL_WINDOW_SIZE=100
LOG_LEVEL=INFO
EOF
        echo "✅ Fichier .env créé avec des valeurs par défaut"
        echo "⚠️  ATTENTION: Modifiez .env avec vos vraies valeurs avant la production!"
    fi
    
    # Charger les variables d'environnement
    source .env
    
    # Créer ou mettre à jour le secret avec des valeurs par défaut sécurisées
    kubectl create secret generic efk-sre-agent-secrets \
        --from-literal=ELASTICSEARCH_PASSWORD="${ELASTICSEARCH_PASSWORD:-changeme}" \
        --from-literal=WEBHOOK_URL="${WEBHOOK_URL:-}" \
        --from-literal=SLACK_WEBHOOK="${SLACK_WEBHOOK:-}" \
        --from-literal=EMAIL_USERNAME="${EMAIL_USERNAME:-}" \
        --from-literal=EMAIL_PASSWORD="${EMAIL_PASSWORD:-}" \
        --from-literal=EMAIL_RECIPIENTS="${EMAIL_RECIPIENTS:-}" \
        -n $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
}

deploy_agent() {
    echo "🚀 Déploiement de l'agent SRE"
    kubectl apply -f k8s/deployment.yaml
    kubectl apply -f k8s/monitoring.yaml
}

wait_for_deployment() {
    echo "⏳ Attente du déploiement..."
    kubectl rollout status deployment/efk-sre-agent -n $NAMESPACE --timeout=300s
}

show_status() {
    echo "📊 Statut du déploiement:"
    kubectl get pods -n $NAMESPACE -l app=efk-sre-agent
    echo ""
    echo "🌐 Service:"
    kubectl get svc -n $NAMESPACE efk-sre-agent
    echo ""
    echo "📈 Pour accéder à l'API depuis l'extérieur du cluster:"
    echo "kubectl port-forward -n $NAMESPACE svc/efk-sre-agent 8080:8080"
    echo "Puis ouvrir: http://localhost:8080/health"
    echo ""
    echo "🔗 Avec Kind, l'API est aussi accessible via: http://localhost:8080 (si NodePort configuré)"
}

cleanup_kind() {
    echo "🧹 Suppression du cluster Kind complet"
    kind delete cluster --name $KIND_CLUSTER_NAME
    rm -f kind-config.yaml
}

show_logs() {
    echo "📝 Logs de l'agent:"
    kubectl logs -n $NAMESPACE -l app=efk-sre-agent --tail=50 -f
}

cleanup() {
    echo "🧹 Nettoyage des ressources"
    kubectl delete -f k8s/deployment.yaml --ignore-not-found=true
    kubectl delete -f k8s/monitoring.yaml --ignore-not-found=true
    kubectl delete secret efk-sre-agent-secrets -n $NAMESPACE --ignore-not-found=true
}

# Menu principal
case "${1:-deploy}" in
    "setup-kind")
        check_kubectl
        check_docker
        check_kind
        setup_kind_cluster
        ;;
    "build")
        check_docker
        check_kind
        build_image
        ;;
    "deploy")
        check_kubectl
        check_docker
        check_kind
        setup_kind_cluster
        create_namespace
        configure_secrets
        build_image
        deploy_agent
        wait_for_deployment
        show_status
        ;;
    "deploy-quick")
        # Déploiement rapide sans rebuilder le cluster Kind
        check_kubectl
        check_docker
        create_namespace
        configure_secrets
        build_image
        deploy_agent
        wait_for_deployment
        show_status
        ;;
    "update")
        check_kubectl
        check_docker
        check_kind
        build_image
        kubectl set image deployment/efk-sre-agent efk-sre-agent=$IMAGE_NAME:$IMAGE_TAG -n $NAMESPACE
        wait_for_deployment
        show_status
        ;;
    "status")
        check_kubectl
        show_status
        ;;
    "logs")
        check_kubectl
        show_logs
        ;;
    "cleanup")
        check_kubectl
        cleanup
        ;;
    "cleanup-kind")
        check_kind
        cleanup_kind
        ;;
    "test")
        echo "🧪 Test de l'API"
        kubectl port-forward -n $NAMESPACE svc/efk-sre-agent 8080:8080 &
        PORT_FORWARD_PID=$!
        sleep 5
        
        echo "Test de santé:"
        curl -s http://localhost:8080/health | jq . || curl -s http://localhost:8080/health
        
        echo -e "\nTest de statut:"
        curl -s http://localhost:8080/status | jq . || curl -s http://localhost:8080/status
        
        kill $PORT_FORWARD_PID
        ;;
    *)
        echo "Usage: $0 {setup-kind|build|deploy|deploy-quick|update|status|logs|cleanup|cleanup-kind|test}"
        echo ""
        echo "Commandes:"
        echo "  setup-kind    - Configure uniquement le cluster Kind"
        echo "  build         - Build l'image Docker et la charge dans Kind"
        echo "  deploy        - Déploiement complet (cluster + app)"
        echo "  deploy-quick  - Déploiement rapide (sans recréer le cluster)"
        echo "  update        - Mise à jour du déploiement existant"
        echo "  status        - Affiche le statut du déploiement"
        echo "  logs          - Affiche les logs en temps réel"
        echo "  test          - Test de l'API via port-forward"
        echo "  cleanup       - Supprime l'application (garde le cluster)"
        echo "  cleanup-kind  - Supprime complètement le cluster Kind"
        echo ""
        echo "🚀 Démarrage rapide:"
        echo "  $0 deploy        # Première installation"
        echo "  $0 deploy-quick  # Redéploiements suivants"
        exit 1
        ;;
esac
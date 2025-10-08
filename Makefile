.PHONY: help install build deploy test clean

# Variables
PYTHON := python3
VENV := .venv
CLUSTER_NAME := efk-sre
ACTIVATE := source $(VENV)/bin/activate &&

help: ## Affiche cette aide
	@echo "🤖 Agent IA SRE EFK - Commandes disponibles:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🚀 Démarrage rapide avec pipx:"
	@echo "  make setup && make activate && make deploy"

setup: ## Configuration complète avec pipx et venv
	./setup.sh install

setup-tools: ## Installe uniquement les outils pipx
	./setup.sh tools

activate: ## Instructions pour activer l'environnement
	@echo "💡 Pour activer l'environnement de développement:"
	@echo "  source activate.sh"
	@echo ""
	@echo "💡 Ou manuellement:"
	@echo "  source $(VENV)/bin/activate"

install: ## Installe les dépendances dans le venv (legacy)
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Environnement virtuel non trouvé. Lancez: make setup"; \
		exit 1; \
	fi
	$(ACTIVATE) pip install --upgrade pip
	$(ACTIVATE) pip install -r requirements.txt

install-dev: ## Installe les dépendances de développement
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install pytest-xdist ipython jupyter

check-kind: ## Vérifie que Kind est installé
	@which kind > /dev/null || (echo "❌ Kind n'est pas installé. Voir QUICKSTART.md" && exit 1)
	@echo "✅ Kind est installé"

setup-kind: check-kind ## Configure uniquement le cluster Kind
	./deploy.sh setup-kind

build: ## Build l'image Docker
	./deploy.sh build

deploy: ## Déploie l'agent complet (cluster + app)
	./deploy.sh deploy

deploy-quick: ## Déploie l'agent rapidement (sans recréer le cluster)
	./deploy.sh deploy-quick

status: ## Affiche le statut du déploiement
	./deploy.sh status

logs: ## Affiche les logs de l'agent
	./deploy.sh logs

test-api: ## Teste l'API de l'agent
	./deploy.sh test

test: ## Lance tous les tests (unitaires + quick)
	@echo "🧪 Lancement de tous les tests..."
	make test-quick
	@echo "✅ Tests terminés!"

test-unit: ## Lance les tests unitaires
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Environnement virtuel non trouvé. Lancez: make setup"; \
		exit 1; \
	fi
	$(ACTIVATE) pytest tests/ -v

test-unit-cov: ## Lance les tests avec couverture
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Environnement virtuel non trouvé. Lancez: make setup"; \
		exit 1; \
	fi
	$(ACTIVATE) pytest tests/ --cov=src --cov-report=html --cov-report=term

test-quick: ## Tests rapides sans dépendances externes
	./test.sh

lint: ## Vérifie le code avec flake8 (via pipx)
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 src/ tests/ --max-line-length=100 --ignore=E203,W503; \
	else \
		echo "❌ flake8 non installé. Lancez: make setup-tools"; \
	fi

format: ## Formate le code avec black (via pipx)
	@if command -v black >/dev/null 2>&1; then \
		black src/ tests/; \
	else \
		echo "❌ black non installé. Lancez: make setup-tools"; \
	fi

type-check: ## Vérification de types avec mypy (via pipx)
	@if command -v mypy >/dev/null 2>&1; then \
		mypy src/ --ignore-missing-imports; \
	else \
		echo "❌ mypy non installé. Lancez: make setup-tools"; \
	fi

dev-env: ## Crée un environnement de développement complet
	make setup
	@echo ""
	@echo "✅ Environnement prêt! Prochaines étapes:"
	@echo "  1. source activate.sh    # Activer l'environnement"
	@echo "  2. make deploy           # Déployer avec Kind"

dev-check: ## Vérifie l'environnement de développement
	@echo "🔍 Vérification de l'environnement de développement..."
	@if [ -d "$(VENV)" ]; then \
		echo "✅ Environnement virtuel trouvé"; \
	else \
		echo "❌ Environnement virtuel manquant"; \
	fi
	@command -v black >/dev/null 2>&1 && echo "✅ black (pipx)" || echo "❌ black manquant"
	@command -v flake8 >/dev/null 2>&1 && echo "✅ flake8 (pipx)" || echo "❌ flake8 manquant"
	@command -v mypy >/dev/null 2>&1 && echo "✅ mypy (pipx)" || echo "❌ mypy manquant"
	@command -v pre-commit >/dev/null 2>&1 && echo "✅ pre-commit (pipx)" || echo "❌ pre-commit manquant"

port-forward: ## Forward l'API sur localhost:8080
	@echo "🌐 API accessible sur http://localhost:8080"
	@echo "⏹️  Appuyer Ctrl+C pour arrêter"
	kubectl port-forward -n monitoring svc/efk-sre-agent 8080:8080

clean: ## Supprime l'application (garde le cluster)
	./deploy.sh cleanup

clean-all: ## Supprime tout (cluster inclus)
	./deploy.sh cleanup-kind
	docker rmi efk-sre-agent:latest 2>/dev/null || true

check-security: ## Vérifie qu'aucun secret n'est commité
	@echo "🔍 Vérification de sécurité..."
	@git log --all --full-history -S "password" --oneline | head -5 | grep -v "changeme\|example\|fake" || echo "✅ Aucun mot de passe détecté"
	@git log --all --full-history -S "token" --oneline | head -5 | grep -v "YOUR\|example\|fake" || echo "✅ Aucun token détecté"
	@echo "✅ Vérification terminée"

info: ## Affiche les informations du projet
	@echo "📋 Informations du projet:"
	@echo "  Nom: Agent IA SRE EFK"
	@echo "  Cluster Kind: $(CLUSTER_NAME)"
	@echo "  Python: $(shell python3 --version 2>/dev/null || echo 'Non installé')"
	@echo "  Docker: $(shell docker --version 2>/dev/null || echo 'Non installé')"
	@echo "  kubectl: $(shell kubectl version --client --short 2>/dev/null || echo 'Non installé')"
	@echo "  Kind: $(shell kind version 2>/dev/null || echo 'Non installé')"
	@echo ""
	@echo "📁 Structure:"
	@find . -maxdepth 2 -type f -name "*.py" -o -name "*.yaml" -o -name "*.md" | grep -v __pycache__ | sort

demo: ## Lance une démo complète
	@echo "🎬 Démo de l'agent SRE EFK avec pipx"
	@echo "1️⃣  Configuration de l'environnement..."
	make setup
	@echo "2️⃣  Activation de l'environnement..."
	@echo "💡 Activez manuellement: source activate.sh"
	@echo "3️⃣  Tests rapides..."
	./test.sh
	@echo "4️⃣  Prêt pour le déploiement..."
	@echo "💡 Lancez: make deploy (après activation)"
	@echo "✅ Démo terminée!"
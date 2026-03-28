.PHONY: help setup-dev test test-cov lint format type-check \
        kind-up kind-down kind-reload \
        helm-lint helm-template port-forward check-security

VENV := .venv
CLUSTER_NAME := kube-seer

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────────────────

setup-dev: ## Create venv and install all dependencies
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install pytest-xdist ipython
	@echo "Done. Activate with: source $(VENV)/bin/activate"

test: ## Run unit tests
	$(VENV)/bin/pytest tests/ -v

test-cov: ## Run unit tests with coverage report
	$(VENV)/bin/pytest tests/ --cov=src --cov-report=html --cov-report=term

lint: ## Check code with flake8
	$(VENV)/bin/flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503

format: ## Format code with black
	$(VENV)/bin/black src/ tests/

type-check: ## Type-check with mypy
	$(VENV)/bin/mypy src/ --ignore-missing-imports

# ── Kind local environment ────────────────────────────────────────────────────

kind-up: ## Spin up full Kind environment (cluster + ES + Prometheus + kube-seer)
	@chmod +x scripts/kind-up.sh
	./scripts/kind-up.sh

kind-down: ## Delete the Kind cluster
	@chmod +x scripts/kind-down.sh
	./scripts/kind-down.sh

kind-reload: ## Rebuild and reload kube-seer in Kind without recreating the cluster
	docker build -t kube-seer:local . --quiet
	kind load docker-image kube-seer:local --name $(CLUSTER_NAME)
	kubectl rollout restart deployment/kube-seer -n monitoring
	kubectl rollout status deployment/kube-seer -n monitoring

# ── Helm ─────────────────────────────────────────────────────────────────────

helm-lint: ## Validate the Helm chart
	helm lint ./helm/kube-seer/

helm-template: ## Render Helm chart templates (dry-run)
	helm template kube-seer ./helm/kube-seer/ \
		--namespace monitoring \
		--set elasticsearch.url=http://elasticsearch:9200

port-forward: ## Forward kube-seer API to localhost:8080
	kubectl port-forward -n monitoring svc/kube-seer 8080:8080

# ── Security ──────────────────────────────────────────────────────────────────

check-security: ## Check that no secrets are committed
	@git log --all --full-history -S "password" --oneline | \
		grep -v "changeme\|example\|fake\|getenv" || echo "No passwords detected"
	@git log --all --full-history -S "token" --oneline | \
		grep -v "YOUR\|example\|fake" || echo "No tokens detected"

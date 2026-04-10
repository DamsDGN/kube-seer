# Contributing to kube-seer

Thank you for your interest in contributing to kube-seer!

## Getting Started

1. **Fork** the repository and clone your fork
2. **Set up** the development environment:
   ```bash
   make setup-dev
   source .venv/bin/activate
   ```
3. **Create a branch** for your change:
   ```bash
   git checkout -b feat/your-feature
   ```

## Development Workflow

### Run tests

```bash
make test                        # unit tests
pytest tests/integration/ -v     # integration tests (requires Kind cluster)
make kind-up && make test-integration
```

### Code quality

```bash
make lint     # black + flake8
make format   # auto-format with black
make type-check  # mypy
```

All checks run automatically in CI on every push and PR.

### Local cluster

```bash
make kind-up     # full stack (ES + Prometheus + Fluent Bit + kube-seer)
make kind-reload # rebuild and redeploy kube-seer only
make kind-down   # tear down
```

## How to Contribute

### Reporting bugs

Open an [issue](https://github.com/DamsDGN/kube-seer/issues) with:
- Kubernetes version and cluster type
- kube-seer version (`helm list -n monitoring`)
- Relevant logs (`kubectl logs -n monitoring deploy/kube-seer`)
- Steps to reproduce

### Suggesting features

Open an [issue](https://github.com/DamsDGN/kube-seer/issues) with the `enhancement` label. Describe the use case, not just the solution.

### Submitting pull requests

1. Make sure tests pass and code is formatted
2. Keep PRs focused — one feature or fix per PR
3. Update the README if you add a new config variable, Helm value, or API endpoint
4. Write tests for new behavior

## Project Structure

```
src/
├── analyzer/     # Anomaly detection logic (metrics, logs, events, resources)
├── alerter/      # Alertmanager + webhook alerting
├── collector/    # Data collection (Prometheus, Metrics Server, K8s API)
├── intelligence/ # LLM integration (providers, prompt, service)
├── storage/      # Elasticsearch persistence
└── api/          # FastAPI REST endpoints

helm/kube-seer/   # Helm chart
scripts/          # Local Kind cluster scripts
tests/            # Unit + integration tests
```

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

FROM python:3.11-slim as base

# Métadonnées pour OCI
LABEL org.opencontainers.image.title="EFK SRE Agent"
LABEL org.opencontainers.image.description="Agent IA SRE pour l'analyse automatisée des métriques et logs EFK"
LABEL org.opencontainers.image.source="https://github.com/DamsDGN/efk-sre-agent"
LABEL org.opencontainers.image.licenses="CC-BY-NC-SA-4.0"

# Arguments de build (fournis par le CI/CD)
ARG BUILDTIME
ARG VERSION=dev
ARG REVISION=unknown

LABEL org.opencontainers.image.created=$BUILDTIME
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$REVISION

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Étape de build des dépendances
FROM base as builder

# Installer les dépendances de compilation
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Créer l'environnement virtuel
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copier les requirements et installer les dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Étape finale
FROM base as final

# Créer un utilisateur non-root
RUN groupadd -r sre && useradd -r -g sre sre

# Copier l'environnement virtuel depuis le builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Répertoire de travail
WORKDIR /app

# Copier le code source
COPY src/ ./src/
COPY README.md .

# Créer les répertoires nécessaires
RUN mkdir -p /tmp/models && \
    chown -R sre:sre /app /tmp/models

# Passer à l'utilisateur non-root
USER sre

# Port exposé pour l'API REST
EXPOSE 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Point d'entrée
CMD ["python", "-m", "src.main"]
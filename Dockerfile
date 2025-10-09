FROM python:3.13-slim as base

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
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

# Étape de build des dépendances
FROM base as builder

# Installer les dépendances de compilation en une seule couche
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        pkg-config \
        && \
    python -m venv /opt/venv && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Utiliser le venv pour les installations suivantes
ENV PATH="/opt/venv/bin:$PATH"

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -type d -exec rm -rf {} + || true

# Étape finale
FROM base as final

# Installer curl pour les healthchecks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Créer un utilisateur non-root avec UID/GID fixes pour la reproductibilité
RUN groupadd -r sre -g 1001 && \
    useradd -r -g sre -u 1001 -m -d /home/sre sre

# Copier l'environnement virtuel depuis le builder
COPY --from=builder --chown=sre:sre /opt/venv /opt/venv

# Répertoire de travail
WORKDIR /app

# Copier le code source avec les bonnes permissions
COPY --chown=sre:sre src/ ./src/
COPY --chown=sre:sre README.md .

# Créer les répertoires nécessaires avec les bonnes permissions
RUN mkdir -p /tmp/models /app/logs && \
    chown -R sre:sre /tmp/models /app

# Passer à l'utilisateur non-root
USER sre

# Port exposé pour l'API REST
EXPOSE 8080

# Healthcheck optimisé avec curl
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Point d'entrée
CMD ["python", "-m", "src.main"]
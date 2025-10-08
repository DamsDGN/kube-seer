FROM python:3.11-slim

# Métadonnées
LABEL maintainer="dams@example.com"
LABEL description="Agent IA SRE pour l'analyse des métriques et logs EFK"
LABEL version="1.0.0"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Créer un utilisateur non-root
RUN groupadd -r sre && useradd -r -g sre sre

# Répertoire de travail
WORKDIR /app

# Installer les dépendances système
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copier les requirements et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
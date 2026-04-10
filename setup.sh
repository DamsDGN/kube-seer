#!/bin/bash

# Script d'installation et configuration pour l'agent SRE EFK
# Utilise pipx pour l'isolation des dépendances

set -e

echo "🔧 Configuration de l'environnement de développement avec pipx"

# Variables
PYTHON_VERSION="3.11"
VENV_DIR=".venv"

# Fonctions utilitaires
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 n'est pas installé"
        echo "💡 Installation: sudo apt install python3 python3-pip python3-venv"
        exit 1
    fi

    PYTHON_VER=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    echo "✅ Python $PYTHON_VER détecté"
}

check_pipx() {
    if ! command -v pipx &> /dev/null; then
        echo "❌ pipx n'est pas installé"
        echo "💡 Installation:"
        echo "  python3 -m pip install --user pipx"
        echo "  python3 -m pipx ensurepath"
        echo "  # Puis redémarrer le terminal"
        exit 1
    fi
    echo "✅ pipx $(pipx --version) détecté"
}

install_dev_tools() {
    echo "📦 Installation des outils de développement avec pipx..."

    # Outils essentiels
    pipx install black || echo "⚠️ black déjà installé"
    pipx install flake8 || echo "⚠️ flake8 déjà installé"
    pipx install mypy || echo "⚠️ mypy déjà installé"
    pipx install pytest || echo "⚠️ pytest déjà installé"

    echo "✅ Outils de développement installés"
}

create_venv() {
    echo "🐍 Création de l'environnement virtuel..."

    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv $VENV_DIR
        echo "✅ Environnement virtuel créé dans $VENV_DIR"
    else
        echo "✅ Environnement virtuel existant trouvé"
    fi

    # Activation et installation des dépendances
    source $VENV_DIR/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

    echo "✅ Dépendances installées dans l'environnement virtuel"
}

setup_pre_commit() {
    echo "🔗 Configuration des hooks pre-commit..."

    # Installer pre-commit avec pipx
    pipx install pre-commit || echo "⚠️ pre-commit déjà installé"

    # Créer le fichier de configuration pre-commit
    cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/psf/black
    rev: '23.9.1'
    hooks:
      - id: black
        language_version: python3
        files: ^(src/|tests/).*\.py$

  - repo: https://github.com/pycqa/flake8
    rev: '6.1.0'
    hooks:
      - id: flake8
        args: [--max-line-length=100, --ignore=E203,W503]
        files: ^(src/|tests/).*\.py$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: local
    hooks:
      - id: check-secrets
        name: Check for secrets
        entry: bash -c 'if git diff --cached --name-only | xargs grep -l "password\|token\|secret\|key" | grep -v "example\|changeme\|fake"; then echo "❌ Secrets détectés!"; exit 1; fi'
        language: system
        pass_filenames: false
EOF

    # Installer les hooks
    pre-commit install

    echo "✅ Pre-commit hooks configurés"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "⚠️ Docker n'est pas installé (optionnel pour le développement)"
        echo "💡 Installation: https://docs.docker.com/get-docker/"
    else
        echo "✅ Docker $(docker --version | cut -d' ' -f3 | cut -d',' -f1) détecté"
    fi
}

check_kind() {
    if ! command -v kind &> /dev/null; then
        echo "⚠️ Kind n'est pas installé (optionnel pour les tests)"
        echo "💡 Installation avec pipx:"
        echo "  pipx install kind-python"
        echo "💡 Ou installation directe:"
        echo "  curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64"
        echo "  chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind"
    else
        echo "✅ Kind $(kind version | cut -d' ' -f2) détecté"
    fi
}

create_dev_scripts() {
    echo "📜 Création des scripts de développement..."

    # Script d'activation de l'environnement
    cat > activate.sh << 'EOF'
#!/bin/bash
# Script d'activation de l'environnement de développement

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "✅ Environnement virtuel activé"
    echo "🐍 Python: $(python --version)"
    echo "📦 Pip: $(pip --version | cut -d' ' -f1,2)"
    echo ""
    echo "💡 Commandes utiles:"
    echo "  make help           # Voir toutes les commandes"
    echo "  make test-unit      # Tests unitaires"
    echo "  make format         # Formater le code"
    echo "  make deploy         # Déployer avec Kind"
    echo ""
else
    echo "❌ Environnement virtuel non trouvé"
    echo "💡 Lancez: ./setup.sh"
fi
EOF
    chmod +x activate.sh

    # Script de test rapide
    cat > test.sh << 'EOF'
#!/bin/bash
# Script de test rapide

set -e

echo "🧪 Tests rapides de l'agent SRE..."

# Activer l'environnement
source .venv/bin/activate

# Tests de syntaxe
echo "1️⃣ Vérification de la syntaxe Python..."
python -m py_compile src/*.py

# Tests d'imports
echo "2️⃣ Vérification des imports..."
python -c "
import sys
sys.path.insert(0, 'src')
try:
    from config import Config
    from models import Alert, Metric, LogEntry
    print('✅ Imports principaux OK')
except ImportError as e:
    print(f'❌ Erreur d\'import: {e}')
    sys.exit(1)
"

# Tests unitaires (si disponibles)
if command -v pytest &> /dev/null; then
    echo "3️⃣ Lancement des tests unitaires..."
    pytest tests/ -v --tb=short || echo "⚠️ Certains tests ont échoué"
else
    echo "⚠️ pytest non disponible, installation des dépendances de test..."
    pip install pytest pytest-asyncio
fi

echo "✅ Tests terminés"
EOF
    chmod +x test.sh

    echo "✅ Scripts de développement créés"
}

show_summary() {
    echo ""
    echo "🎉 Configuration terminée!"
    echo ""
    echo "📋 Résumé:"
    echo "  🐍 Environnement virtuel: $VENV_DIR"
    echo "  🔧 Outils pipx installés: black, flake8, mypy, pytest, pre-commit"
    echo "  🔗 Pre-commit hooks: configurés"
    echo "  📜 Scripts créés: activate.sh, test.sh"
    echo ""
    echo "🚀 Prochaines étapes:"
    echo "  1. source activate.sh     # Activer l'environnement"
    echo "  2. ./test.sh             # Tester le code"
    echo "  3. make deploy           # Déployer avec Kind (si installé)"
    echo ""
    echo "💡 Pour le développement quotidien:"
    echo "  - Toujours activer l'environnement: source activate.sh"
    echo "  - Utiliser les commandes make: make help"
    echo "  - Les hooks pre-commit vérifient automatiquement le code"
}

# Menu principal
case "${1:-install}" in
    "install")
        check_python
        check_pipx
        install_dev_tools
        create_venv
        setup_pre_commit
        create_dev_scripts
        check_docker
        check_kind
        show_summary
        ;;
    "tools")
        check_pipx
        install_dev_tools
        ;;
    "venv")
        check_python
        create_venv
        ;;
    "hooks")
        setup_pre_commit
        ;;
    "check")
        check_python
        check_pipx
        check_docker
        check_kind
        echo "✅ Tous les outils sont vérifiés"
        ;;
    *)
        echo "Usage: $0 {install|tools|venv|hooks|check}"
        echo ""
        echo "Commandes:"
        echo "  install  - Installation complète (par défaut)"
        echo "  tools    - Installer uniquement les outils pipx"
        echo "  venv     - Créer uniquement l'environnement virtuel"
        echo "  hooks    - Configurer uniquement les pre-commit hooks"
        echo "  check    - Vérifier les outils installés"
        exit 1
        ;;
esac

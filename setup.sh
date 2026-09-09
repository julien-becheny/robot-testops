#!/bin/bash
# ROBOT-TESTOPS — Installation de l'environnement (macOS / Linux)
set -e

echo "================================================================================"
echo "       ROBOT-TESTOPS — INSTALLATION DE L'ENVIRONNEMENT"
echo "================================================================================"
echo ""
echo "Ce script :"
echo "  1. Crée un environnement virtuel Python"
echo "  2. Installe les packages Python (pip_requirements.txt)"
echo "  3. Initialise Playwright (navigateurs Chromium, Firefox, WebKit)"
echo "  4. Installe les dépendances React (testops)"
echo "  5. Build le frontend TestOps"
echo ""

# ── Vérification des prérequis ──
check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo "❌ $1 n'est pas installé ou pas dans le PATH."
        echo "   $2"
        exit 1
    fi
}

check_command python3 "Installez Python 3.12+ : brew install python@3.12 (macOS) ou apt install python3 (Linux)"
check_command node "Installez Node.js 22.12+ : brew install node (macOS) ou https://nodejs.org/"

if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"; then
    echo "❌ Python 3.12+ est requis par les locks du projet (version détectée : $(python3 --version))."
    exit 1
fi

NODE_VERSION="$(node -p 'process.versions.node')"
NODE_MAJOR="${NODE_VERSION%%.*}"
NODE_REST="${NODE_VERSION#*.}"
NODE_MINOR="${NODE_REST%%.*}"
if [ "$NODE_MAJOR" -lt 22 ] || { [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -lt 12 ]; }; then
    echo "❌ Node.js 22.12+ est requis par Vite (version détectée : $NODE_VERSION)."
    echo "   Installez une version LTS récente : brew install node (macOS) ou https://nodejs.org/"
    exit 1
fi

# ── Affichage des versions ──
echo "🔍 Versions détectées :"
echo "  Python : $(python3 --version)"
echo "  Node   : $(node --version)"
echo "  npm    : $(npm --version)"
echo ""

# ── 1. Environnement virtuel Python ──
echo "────────────────────────────────────────────────────────────────"
echo " ÉTAPE 1/5 : Environnement virtuel Python"
echo "────────────────────────────────────────────────────────────────"

if [ -d "env" ]; then
    read -p "⚠️  Un environnement virtuel existe déjà. Le recréer ? (o/N) : " CONFIRM
    if [[ "$CONFIRM" =~ ^[oOyY]$ ]]; then
        echo "🧹 Suppression de l'ancien environnement..."
        deactivate 2>/dev/null || true
        rm -rf env
    else
        echo "✅ Conservation de l'environnement existant."
    fi
fi

if [ ! -d "env" ]; then
    python3 -m venv env
    echo "✅ Environnement virtuel créé."
fi

# ── 2. Activation + Installation pip ──
echo ""
echo "────────────────────────────────────────────────────────────────"
echo " ÉTAPE 2/5 : Installation des packages Python"
echo "────────────────────────────────────────────────────────────────"

source env/bin/activate
python -m pip install --upgrade pip --quiet

if [ ! -f "pip_requirements.txt" ]; then
    echo "❌ pip_requirements.txt introuvable."
    exit 1
fi

python -m pip install -r pip_requirements.txt
python -m pip check
echo "✅ Packages Python installés et vérifiés."

# ── 3. Initialisation Playwright (RF Browser) ──
echo ""
echo "────────────────────────────────────────────────────────────────"
echo " ÉTAPE 3/5 : Initialisation de Playwright (navigateurs)"
echo "────────────────────────────────────────────────────────────────"

if ! python -m Browser.entry init; then
    echo "❌ Échec de l'initialisation de Playwright."
    echo "   La version Python est verrouillée : vérifiez l'accès au registre npm,"
    echo "   puis relancez setup.sh sans mettre robotframework-browser à niveau."
    exit 1
fi
echo "✅ Playwright initialisé (Chromium, Firefox, WebKit)."

# ── 4. Installation des dépendances frontend ──
echo ""
echo "────────────────────────────────────────────────────────────────"
echo " ÉTAPE 4/5 : Installation des dépendances React/Vite (testops)"
echo "────────────────────────────────────────────────────────────────"

if [ ! -f "testops/package.json" ]; then
    echo "⚠️  Dossier testops non trouvé, étape ignorée."
else
    (
        cd testops
        npm ci
        echo "✅ Dépendances React/Vite installées."

        # ── 5. Build du frontend ──
        echo ""
        echo "────────────────────────────────────────────────────────────────"
        echo " ÉTAPE 5/5 : Build du frontend TestOps"
        echo "────────────────────────────────────────────────────────────────"

        npm run build
        echo "✅ Frontend TestOps compilé."
    )
fi

# ── Vérification finale ──
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "                   VÉRIFICATION FINALE"
echo "════════════════════════════════════════════════════════════════"

python -c "import robot; print(f'  ✅ Robot Framework: {robot.__version__}')"
python -c "import Browser; print(f'  ✅ RF Browser:      {Browser.__version__}')"
python -c "import flask; print(f'  ✅ Flask:            {flask.__version__}')"
python -c "import requests; print(f'  ✅ Requests:         {requests.__version__}')"

# ── Outils qualité ──
echo ""
echo "─────────────────────────────────────────────"
echo " OUTILS QUALITÉ (lint, analyse statique, tests)"
echo "─────────────────────────────────────────────"
python -m pip install -r pip_requirements-dev.txt --quiet
python -m pip check
echo " Contrôles disponibles : python tools/ci_local.py"

# ── Création des dossiers de sortie ──
mkdir -p "$HOME/rf_output/report"

deactivate

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "                   INSTALLATION TERMINÉE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🚀 Pour démarrer :"
echo "   1. source env/bin/activate"
echo "   2. python -m api.app"
echo "   3. Ouvrir http://localhost:5000 dans le navigateur"
echo ""

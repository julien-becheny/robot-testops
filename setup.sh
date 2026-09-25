#!/bin/bash
# ROBOT-TESTOPS - Installation de l'environnement (macOS / Linux)
set -e

echo "================================================================================"
echo "       ROBOT-TESTOPS - INSTALLATION DE L'ENVIRONNEMENT"
echo "================================================================================"
echo ""
echo "Ce script :"
echo "  1. Crée l'environnement Python à l'identique du verrou (uv.lock)"
echo "  2. Initialise Playwright (navigateurs Chromium, Firefox, WebKit)"
echo "  3. Installe les dépendances React (testops)"
echo "  4. Build le frontend TestOps"
echo ""

# ── Vérification des prérequis ──
check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo "❌ $1 n'est pas installé ou pas dans le PATH."
        echo "   $2"
        exit 1
    fi
}

if ! command -v uv &>/dev/null; then
    echo "❌ uv n'est pas installé : c'est lui qui gère Python et les dépendances du projet."
    echo "   Installez-le, puis rouvrez un terminal :"
    echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   (sans curl : wget -qO- https://astral.sh/uv/install.sh | sh)"
    echo "   (macOS avec Homebrew : brew install uv)"
    exit 1
fi
check_command node "Installez Node.js 22.12+ : brew install node (macOS) ou https://nodejs.org/"

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
echo "  uv     : $(uv --version)"
echo "  Node   : $(node --version)"
echo "  npm    : $(npm --version)"
echo ""

# ── 1. Environnement Python ──
echo "────────────────────────────────────────────────────────────────"
echo " ÉTAPE 1/4 : Environnement Python (uv sync)"
echo "────────────────────────────────────────────────────────────────"
echo " uv télécharge au besoin la version de Python indiquée par .python-version."

uv sync --locked
echo "✅ Environnement Python conforme au verrou (outils qualité inclus)."

source .venv/bin/activate

# ── 2. Initialisation Playwright (RF Browser) ──
echo ""
echo "─────────────────────────────────────────────────────────────"
echo " ÉTAPE 2/4 : Initialisation de Playwright (navigateurs)"
echo "────────────────────────────────────────────────────────────────"

if ! python -m Browser.entry init; then
    echo "❌ Échec de l'initialisation de Playwright."
    echo "   La version de robotframework-browser est verrouillée : vérifiez l'accès au"
    echo "   registre npm, puis relancez setup.sh sans modifier cette version."
    exit 1
fi
echo "✅ Navigateurs Playwright téléchargés."

# Linux : Playwright livre les navigateurs mais pas les bibliothèques système, réservées à root.
# La sonde NAVIGUE vers un serveur local : un navigateur peut démarrer et rester incapable de
# charger la moindre page, auquel cas un simple test de lancement annoncerait un faux succès.
if [ "$(uname -s)" = "Linux" ]; then
    WRAPPER="$(python -c 'import os, Browser; print(os.path.join(os.path.dirname(Browser.__file__), "wrapper"))')"
    INDISPO="$(cd "$WRAPPER" && PLAYWRIGHT_BROWSERS_PATH=0 node -e "const http=require('http'),pw=require('playwright-core');(async()=>{const s=http.createServer((q,r)=>r.end('ok')).listen(0,'127.0.0.1');await new Promise(r=>s.on('listening',r));s.unref();const u='http://127.0.0.1:'+s.address().port;for(const n of ['chromium','firefox','webkit']){let b;try{b=await pw[n].launch();const p=await (await b.newContext()).newPage();await p.goto(u,{timeout:10000});}catch(e){console.log(n);}finally{if(b)await b.close().catch(()=>{});}}s.close();})();" 2>/dev/null || true)"
    if [ -n "$INDISPO" ]; then
        echo "⚠️  Ne chargent aucune page sur cette machine : $(echo $INDISPO | tr '\n' ' ')"
        echo "   1) Bibliothèques système absentes ? Playwright livre les navigateurs, pas les"
        echo "      bibliothèques que la distribution doit fournir :  npx playwright install-deps"
        echo "      (sans sudo : la commande demande elle-meme les droits ; sudo perdrait le npx de nvm)"
        echo "   2) Déjà installées ? Le navigateur est alors inopérant sur cette distribution -"
        echo "      cas connu sur les versions très récentes. Les autres navigateurs restent utilisables."
        echo "   Le reste du framework fonctionne sans lui."
    else
        echo "✅ Chromium, Firefox et WebKit chargent une page."
    fi
fi

# ── 3. Installation des dépendances frontend ──
echo ""
echo "─────────────────────────────────────────────────────────────"
echo " ÉTAPE 3/4 : Installation des dépendances React/Vite (testops)"
echo "────────────────────────────────────────────────────────────────"

if [ ! -f "testops/package.json" ]; then
    echo "⚠️  Dossier testops non trouvé, étape ignorée."
else
    (
        cd testops
        npm ci
        echo "✅ Dépendances React/Vite installées."

        # ── 4. Build du frontend ──
        echo ""
        echo "─────────────────────────────────────────────────────────────"
        echo " ÉTAPE 4/4 : Build du frontend TestOps"
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
python -c "import importlib.metadata as m; print('  ✅ AppiumLibrary:   ' + m.version('robotframework-appiumlibrary'))"
python -c "import importlib.metadata as m; print('  ✅ Flask:            ' + m.version('flask'))"
python -c "import requests; print(f'  ✅ Requests:         {requests.__version__}')"

# ── Mobile (Appium) : installation des drivers ──
echo ""
echo "───────────────────────────────────────────────────────────"
echo " MOBILE (APPIUM) - installation des drivers"
echo "───────────────────────────────────────────────────────────"

if ! command -v appium &>/dev/null; then
    echo " Installation du serveur Appium (npm -g)..."
    npm install -g appium || echo " ⚠️  Échec npm install -g appium (droits ?) - à installer manuellement."
else
    echo " Serveur Appium déjà présent."
fi

if command -v appium &>/dev/null && ! appium driver list --installed 2>/dev/null | grep -q uiautomator2; then
    echo " Installation du driver Android uiautomator2..."
    appium driver install uiautomator2 || true
else
    echo " Driver uiautomator2 déjà installé (ou appium absent)."
fi

# iOS (macOS uniquement) : Xcode + driver xcuitest
if [ "$(uname)" = "Darwin" ]; then
    echo ""
    echo " iOS (macOS) :"
    if xcode-select -p &>/dev/null; then
        echo "   ✅ Xcode outils : $(xcode-select -p)"
    else
        echo "   ⚠️  Xcode outils absents -> xcode-select --install"
    fi
    if command -v appium &>/dev/null && ! appium driver list --installed 2>/dev/null | grep -q xcuitest; then
        echo "   Installation du driver iOS xcuitest..."
        appium driver install xcuitest || true
    fi
    echo "   ℹ️  WebDriverAgent à builder/signer à la 1re exécution sur un device réel."
fi

echo ""
echo " ℹ️  À installer manuellement : Android SDK (Android Studio) + ANDROID_HOME."
python -m services.mobile.preflight || true

# ── Tests de charge : Locust vient du verrou, k6 est un binaire externe ──
echo ""
echo "───────────────────────────────────────────────────────"
echo " TESTS DE CHARGE - moteurs d'injection"
echo "───────────────────────────────────────────────────────"
echo " ✅ Locust (modèle fermé) : installé par uv, rien à faire."
if command -v k6 &>/dev/null; then
    echo " ✅ k6 (modèle ouvert)  : $(k6 version 2>/dev/null | head -1)"
else
    echo " ⚠️  k6 absent : les tests à DÉBIT IMPOSÉ ne pourront pas démarrer."
    echo "    Les autres types - smoke, load, stress, endurance, capacité, calibrage -"
    echo "    tournent avec Locust et ne le réclament pas."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "    macOS : brew install k6"
    else
        echo "    Linux : dépôt officiel dl.k6.io - https://grafana.com/docs/k6/latest/set-up/install-k6/"
        echo "            (éviter le snap : son confinement bloque l'écriture des résultats)"
    fi
fi

# ── Outils qualité ──
echo ""
echo "─────────────────────────────────────────────"
echo " OUTILS QUALITÉ (lint, analyse statique, tests)"
echo "─────────────────────────────────────────────"
echo " Installés par uv sync. Contrôles disponibles : uv run tools/ci_local.py"

# ── Création des dossiers de sortie ──
mkdir -p "$HOME/rf_output/report"

deactivate

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "                   INSTALLATION TERMINÉE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🚀 Pour démarrer :"
echo "   macOS :"
echo "   chmod +x start_testops_mac.sh"
echo "   ./start_testops_mac.sh"
echo "   linux :"
echo "   chmod +x start_testops_linux.sh"
echo "   ./start_testops_linux.sh"
echo "   Interface TestOps : http://localhost:3000  -  API : http://localhost:5001"
echo ""

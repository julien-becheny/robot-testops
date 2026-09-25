#!/bin/bash
# Script de démarrage TestOps pour Linux
#
# Les services tournent en arrière-plan, journaux dans temp/. Pas de fenêtres de terminal :
# leur pilotage dépend de l'émulateur installé (ptyxis, konsole, xterm...), qui change d'une
# distribution et d'une version à l'autre - alors que ceci marche aussi en WSL et sans écran.

set -u

cd "$(dirname "$0")" || exit 1

echo "================================================================================"
echo "                    DÉMARRAGE DE TESTOPS (Linux)"
echo "                 Test Automation Control Panel"
echo "================================================================================"

if ! command -v uv &>/dev/null; then
    echo "❌ uv est introuvable dans le PATH - voir la section Démarrage du README."
    echo "   Terminal ouvert avant l'installation d'uv ? Essayez : source ~/.bashrc"
    exit 1
fi

if ! command -v npm &>/dev/null; then
    echo "❌ npm est introuvable dans le PATH - voir la section Démarrage du README."
    echo "   Node.js installé via nvm ? Essayez : source ~/.nvm/nvm.sh"
    exit 1
fi

LOG_DIR="temp"
mkdir -p "$LOG_DIR"

port_ouvert() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

for port in 5001 3000; do
    if port_ouvert "$port"; then
        echo "❌ Le port $port répond déjà : TestOps est probablement lancé."
        echo "   Pour l'arrêter : kill -- \$(cat $LOG_DIR/testops.pid)"
        exit 1
    fi
done

echo "📂 Répertoire de travail : $(pwd)"
echo ""

# Job control : chaque service obtient son propre groupe de processus. Sans cela, tuer le seul
# parent laisse vivre ses enfants (npm lance vite) et le port reste occupé.
set -m

echo "🌐 Démarrage du serveur Flask (port 5001)..."
nohup uv run python api/app.py > "$LOG_DIR/flask.log" 2>&1 &
FLASK_PID=$!

echo "⚛️  Démarrage de l'interface React (port 3000)..."
( cd testops && exec npm start ) > "$LOG_DIR/react.log" 2>&1 &
REACT_PID=$!

set +m

# Identifiants stockés négatifs : `kill -- -PGID` vise le groupe entier, enfants compris.
echo "-$FLASK_PID -$REACT_PID" > "$LOG_DIR/testops.pid"

attendre_port() {
    local port="$1"
    for _ in $(seq 1 60); do
        port_ouvert "$port" && return 0
        sleep 1
    done
    return 1
}

echo "⏳ Attente de la réponse des services..."
ECHEC=0
attendre_port 5001 || { echo "❌ L'API Flask n'écoute pas sur le port 5001."; ECHEC=1; }
attendre_port 3000 || { echo "❌ L'interface n'écoute pas sur le port 3000."; ECHEC=1; }

if [ "$ECHEC" -eq 1 ]; then
    echo ""
    echo "──── $LOG_DIR/flask.log ────"
    tail -n 10 "$LOG_DIR/flask.log"
    echo "──── $LOG_DIR/react.log ────"
    tail -n 10 "$LOG_DIR/react.log"
    kill -- "-$FLASK_PID" "-$REACT_PID" 2>/dev/null
    rm -f "$LOG_DIR/testops.pid"
    exit 1
fi

if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:3000" >/dev/null 2>&1 &
fi

echo ""
echo "================================================================================"
echo "                        TESTOPS DÉMARRÉ"
echo "================================================================================"
echo "Utilisez ces URL pour accéder aux services:"
echo "  • Interface utilisateur : http://localhost:3000"
echo "  • API Flask             : http://localhost:5001"
echo ""
echo "📋 Journaux : tail -f $LOG_DIR/flask.log  |  tail -f $LOG_DIR/react.log"
echo "📋 Arrêt    : kill -- \$(cat $LOG_DIR/testops.pid)"
echo "================================================================================"

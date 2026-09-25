import os
import sys
import threading
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH AVANT tous les imports
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flask import jsonify
from flask_socketio import join_room, leave_room
from werkzeug.exceptions import HTTPException

from api.routes.campaign_routes import campaign_bp
from api.routes.config_routes import config_bp
from api.routes.coverage_routes import coverage_bp
from api.routes.execution_routes import execution_bp
from api.routes.history_routes import history_bp
from api.routes.load_routes import load_bp
from api.routes.mobile_routes import mobile_bp
from api.routes.status_routes import status_bp
from api.routes.tags_routes import tags_bp
from api.socketio_instance import app, socketio
from core import config
from core.logging_config import configure_logging, get_logger

configure_logging(config.get("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)


@app.errorhandler(Exception)
def handle_unexpected_http_error(error: Exception):
    """Journalise une panne HTTP imprévue sans exposer ses détails au client."""
    if isinstance(error, HTTPException):
        return error
    logger.error(
        "Erreur HTTP interne non gérée",
        exc_info=(type(error), error, error.__traceback__),
    )
    return jsonify({'error': 'Erreur interne du serveur'}), 500


# Enregistrer les Blueprints
app.register_blueprint(config_bp)
app.register_blueprint(execution_bp)
app.register_blueprint(load_bp)
app.register_blueprint(status_bp)
app.register_blueprint(tags_bp)
app.register_blueprint(campaign_bp)
app.register_blueprint(mobile_bp)
app.register_blueprint(coverage_bp)
app.register_blueprint(history_bp)


@app.route('/')
def index():
    return "TestOps API is running"


def _api_host() -> str:
    """Retourne l'interface réseau sur laquelle l'API doit écouter.

    L'adresse de boucle locale est utilisée par défaut pour ne pas exposer les
    routes de pilotage sur le réseau sans décision explicite.

    Returns:
        Le nom d'hôte ou l'adresse IP configurée pour le serveur Flask.
    """
    return str(config.get("API_HOST", "127.0.0.1") or "127.0.0.1").strip()


def _api_port() -> int:
    """Retourne un port TCP valide pour le serveur API.

    Returns:
        Le port configuré lorsqu'il appartient à l'intervalle 1 à 65535,
        sinon le port par défaut 5001.
    """
    try:
        port = int(config.get("API_PORT", 5001))
    except (TypeError, ValueError):
        return 5001
    return port if 1 <= port <= 65535 else 5001


@socketio.on('join_session')
def handle_join_session(data):
    """Le client rejoint la room de sa session pour recevoir ses events."""
    session_id = data.get('session_id', '')
    if session_id:
        join_room(session_id)
        logger.info("Client a rejoint la session : %s", session_id)


@socketio.on('leave_session')
def handle_leave_session(data):
    """Le client quitte la room de sa session."""
    session_id = data.get('session_id', '')
    if session_id:
        leave_room(session_id)
        logger.info("Client a quitté la session : %s", session_id)


def _free_port(port: int = 5001):
    """Libère le port en arrêtant tout ancien process Flask qui l'occupe encore."""
    import platform
    import signal
    import subprocess
    import time

    current_pid = os.getpid()
    system = platform.system()
    pids = set()

    try:
        if system == 'Windows':
            out = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
            ).stdout or ''
            for line in out.splitlines():
                if f':{port}' in line and 'LISTENING' in line.upper():
                    parts = line.split()
                    if parts:
                        pids.add(parts[-1])
        else:
            out = subprocess.run(
                ['lsof', '-ti', f':{port}', '-sTCP:LISTEN'],
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            ).stdout or ''
            pids.update(out.split())
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Vérification du port %s impossible : %s", port, exc)
        logger.debug("Détail de la vérification du port", exc_info=True)
        return

    for pid_str in pids:
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        try:
            if system == 'Windows':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            else:
                os.kill(pid, signal.SIGTERM)
            logger.info("Ancien processus Flask (PID %s) sur le port %s arrêté", pid, port)
            time.sleep(1)
        except ProcessLookupError:
            logger.debug("Le processus %s était déjà arrêté", pid)
        except OSError as exc:
            logger.warning("Impossible d'arrêter le PID %s : %s", pid, exc)
            logger.debug("Détail de l'arrêt du processus", exc_info=True)


def _silence_gevent_keyboardinterrupt():
    """Empêche gevent d'imprimer sa pile interne au Ctrl+C.

    gevent imprime la KeyboardInterrupt depuis sa boucle (hub) puis la relance
    dans le greenlet principal. On l'ajoute au NOT_ERROR du hub : plus d'impression,
    mais elle reste relancée (arrêt propre géré par le try/except plus bas).
    """
    try:
        import gevent
        hub = gevent.get_hub()
        if KeyboardInterrupt not in hub.NOT_ERROR:
            hub.NOT_ERROR = tuple(hub.NOT_ERROR) + (KeyboardInterrupt,)
    except (ImportError, AttributeError, RuntimeError, TypeError):
        logger.debug("Configuration du hub gevent indisponible", exc_info=True)


def _log_mobile_preflight():
    """Écrit l'état de la chaîne mobile dans le log, sans jamais l'imposer au reste."""
    try:
        from services.mobile.preflight import check_mobile_env, summary_lines
        for line in summary_lines(check_mobile_env()):
            logger.info("%s", line)
    except Exception:  # noqa: BLE001 - le mobile optionnel ne doit pas bloquer le web
        logger.debug("Préflight mobile indisponible au démarrage", exc_info=True)


def _start_mobile_preflight():
    """Lance le préflight mobile en fond.

    Il interroge le serveur Appium et le CLI Node : à froid, cela prend des dizaines
    de secondes. Le faire avant `socketio.run` retardait d'autant l'ouverture du port,
    alors que le web, la charge et la couverture n'ont aucun besoin du mobile.
    """
    thread = threading.Thread(target=_log_mobile_preflight, name="mobile-preflight",
                              daemon=True)
    thread.start()
    return thread


if __name__ == '__main__':
    api_port = _api_port()
    _free_port(api_port)
    _silence_gevent_keyboardinterrupt()

    logger.info("Démarrage de TestOps sur http://%s:%s", _api_host(), api_port)
    _start_mobile_preflight()

    try:
        socketio.run(app, host=_api_host(), port=api_port, debug=False)
    except KeyboardInterrupt:
        logger.info("Arrêt de TestOps")

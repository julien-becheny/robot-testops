"""
Routes API pour les tests de charge, pilotees depuis TestOps.

Le MOTEUR n'est pas choisi par l'appelant : il decoule du modele de charge du type
demande (ferme -> Locust, ouvert -> k6), declare dans services/load/profiles.py.

Endpoints :
- GET  /load-targets  : liste blanche des cibles autorisees
- GET  /load-profiles : familles de charge + types de test et champs (UI dynamique)
- POST /run-load      : lance un test de charge (cible + type + params)
- POST /load-result   : recoit le resume du runner et le pousse en SocketIO
- POST /load-metrics  : recoit les metriques live et les pousse en SocketIO
- GET  /load-report/<name> : sert le rapport HTML autonome produit par k6
- GET/POST/DELETE /load-baseline : reference a laquelle les runs suivants se comparent

La progression/fin reutilise les routes existantes /log et /execution-complete.
"""

import re
import threading

from flask import Blueprint, jsonify, request, send_from_directory

from api.socketio_instance import socketio
from core.session_registry import registry
from services.load import baselines, k6_runner, locust_runner
from services.load.history import clear_history, list_runs
from services.load.profiles import engine_for, list_models, list_test_types, validate_params
from services.load.runner_common import free_port
from services.load.targets import get_target, list_targets

load_bp = Blueprint('load', __name__)

_RUNNERS = {
    'locust': locust_runner.run_load_test,
    'k6': k6_runner.run_load_test,
}

# Le nom du rapport est genere par le runner : tout ce qui en sort est un chemin force.
_REPORT_NAME = re.compile(r'^(k6|rapport)_[0-9a-f]{4,64}\.html$')


def _emit_to_session(event, data, session_id):
    """Emet un event SocketIO dans la room de la session."""
    if session_id:
        socketio.emit(event, {**data, 'session_id': session_id}, room=session_id)
    else:
        socketio.emit(event, data)


@load_bp.route('/load-targets', methods=['GET'])
def load_targets():
    """Retourne la liste blanche des cibles de charge autorisees."""
    return jsonify({'targets': list_targets()})


@load_bp.route('/load-profiles', methods=['GET'])
def load_profiles():
    """Familles de charge et types de test (champs par type) pour l'UI dynamique."""
    return jsonify({'types': list_test_types(), 'models': list_models()})


@load_bp.route('/run-load', methods=['POST'])
def run_load():
    """
    Lance un test de charge.

    Body:
        { 'target': str, 'test_type': str, 'params': dict }
    """
    data = request.get_json() or {}

    target_id = data.get('target', '')
    if not get_target(target_id):
        return jsonify({'error': f'Cible non autorisee : {target_id}'}), 400

    test_type = str(data.get('test_type', 'load')).lower()
    try:
        params = validate_params(test_type, data.get('params'))
        engine = engine_for(test_type)
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    # Port libre dedie au dashboard temps reel de ce run (Locust ou k6).
    web_port = free_port()
    session = registry.create_session(workflow='load')

    thread = threading.Thread(
        target=_RUNNERS[engine],
        args=(target_id, test_type, params, session.session_id, web_port),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'status': 'started',
        'session_id': session.session_id,
        'engine': engine,
        # Ecran temps reel du moteur, a ouvrir a cote de TestOps.
        'dashboard_url': f'http://localhost:{web_port}',
    })


@load_bp.route('/load-result', methods=['POST'])
def load_result():
    """Recoit le resume du runner et le pousse dans la room de la session."""
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    _emit_to_session('load-result', {'result': data.get('result', {})}, session_id)
    return jsonify({'status': 'ok'})


@load_bp.route('/load-metrics', methods=['POST'])
def load_metrics():
    """Recoit les metriques live du runner et les pousse dans la room."""
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    _emit_to_session('load-metrics', {'metrics': data.get('metrics', {})}, session_id)
    return jsonify({'status': 'ok'})


@load_bp.route('/load-report/<name>', methods=['GET'])
def load_report(name):
    """Sert le rapport HTML autonome d'un run k6 (survit a la fin du dashboard)."""
    if not _REPORT_NAME.match(name):
        return jsonify({'error': 'Rapport inconnu'}), 404
    report_dir = k6_runner.REPORTS_DIR
    if not (report_dir / name).is_file():
        return jsonify({'error': 'Rapport introuvable (run trop ancien ?)'}), 404
    return send_from_directory(str(report_dir), name)


@load_bp.route('/load-history', methods=['GET'])
def load_history():
    """Historique des runs de charge (du plus recent au plus ancien)."""
    return jsonify({'runs': list_runs(limit=50)})


@load_bp.route('/load-history', methods=['DELETE'])
def clear_load_history():
    """Vide l'historique des runs de charge."""
    clear_history()
    return jsonify({'status': 'ok'})


@load_bp.route('/load-baseline', methods=['GET'])
def get_baseline():
    """Reference enregistree pour un couple cible / type de test."""
    target_id = request.args.get('target', '')
    test_type = request.args.get('test_type', '')
    return jsonify({'baseline': baselines.get(target_id, test_type)})


@load_bp.route('/load-baselines', methods=['GET'])
def list_baselines():
    """Toutes les references : l'UI doit savoir quels runs sont epingles apres un F5."""
    return jsonify({'baselines': baselines.list_all()})


@load_bp.route('/load-baseline', methods=['POST'])
def set_baseline():
    """Fait d'un run de l'historique la reference de sa cible et de son type."""
    run_id = (request.get_json() or {}).get('run_id', '')
    run = next((r for r in list_runs(limit=200) if r.get('id') == run_id), None)
    if not run:
        return jsonify({'error': 'Run introuvable dans l historique'}), 404
    reference = baselines.set_baseline(run)
    if not reference:
        return jsonify({'error': 'Ce run ne peut pas servir de reference'}), 400
    return jsonify({'baseline': reference})


@load_bp.route('/load-baseline', methods=['DELETE'])
def clear_baseline():
    """Retire la reference d'un couple cible / type de test."""
    data = request.get_json() or {}
    removed = baselines.clear(data.get('target', ''), data.get('test_type', ''))
    return jsonify({'status': 'ok', 'removed': removed})

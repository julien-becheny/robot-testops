"""
Routes API pour l'exécution des tests.

Tous les events SocketIO sont scopés par session_id via des rooms.
Le listener RF envoie session_id dans chaque payload.
Le frontend rejoint la room de sa session pour ne recevoir que ses events.

Endpoints :
- POST /run-test : Lance l'exécution d'un test
- GET /smoke-suite : Ce que le smoke jouera (suite fixe et ses tests)
- GET /last-run : Résumé du dernier run joué
- GET /last-run/<filename> : Sert un fichier du dernier run (log, rapport, captures)
- POST /stop-test : Arrête une exécution (par session_id)
- POST /log : Reçoit un log depuis un listener RF
- POST /log-link : Reçoit le nom du fichier de log
- POST /log-directory : Reçoit le chemin du dossier de rapports
- POST /progress : Reçoit l'avancement du run (tests joués / total)
- POST /final-status : Reçoit le statut final de la suite
- GET /logs/<session_id>/standard/<filename> : Sert un fichier de log
- GET /logs/<session_id>/original/<filename> : Sert un fichier original
- GET /logs/<session_id>/merged/<filename> : Sert un fichier mergé
- POST /open-directory : Ouvre le dossier de rapports dans l'explorateur
- GET /sessions : Liste les sessions actives
"""

import os
import platform
import subprocess
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from api.socketio_instance import socketio
from api.validation import (
    RequestValidationError,
    require_json_object,
    validate_run_target,
    validate_string,
    validate_workflow,
)
from core import config
from core.logging_config import get_logger
from core.paths import paths
from core.session_registry import registry
from services.execution import history
from services.execution.commands import SMOKE_SUITE
from services.tags.parser import build_tests_list

execution_bp = Blueprint('execution', __name__)
logger = get_logger(__name__)

# log_directory par session {session_id: path}
_session_log_dirs = {}


def _emit_to_session(event, data, session_id):
    """Émet un event SocketIO dans la room de la session."""
    if session_id:
        socketio.emit(event, {**data, 'session_id': session_id}, room=session_id)
    else:
        socketio.emit(event, data)


@execution_bp.route('/run-test', methods=['POST'])
def run_test():
    """
    Lance l'exécution d'un test Robot Framework.
    
    Body:
        {
            'workflow': str,
            'include_tags': list,
            'exclude_tags': list,
        }
    
    Returns:
        JSON: { 'status': str, 'session_id': str }
    """
    try:
        data = require_json_object(request.get_json(silent=True))
        workflow = validate_workflow(data.get('workflow', 'smoke'))
        browser, _viewport, device = validate_run_target(
            data,
            config.get('RF_BROWSER', 'chromium'),
            config.get('RF_VIEWPORT', '1920x1080'),
        )
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    from services.execution.orchestrator import run_workflow

    session = registry.create_session(browser=browser, workflow=workflow)
    thread = threading.Thread(
        target=run_workflow,
        args=(workflow,),
        kwargs={
            'session_id': session.session_id,
            'browser': browser,
            'device': device,
        },
        daemon=True
    )
    try:
        thread.start()
    except (OSError, RuntimeError):
        registry.remove(session.session_id)
        raise

    return jsonify({
        'status': 'started',
        'session_id': session.session_id,
        'message': f'Workflow "{workflow}" lancé'
    })


@execution_bp.route('/smoke-suite', methods=['GET'])
def smoke_suite():
    """Retourne ce que le smoke jouera : sa suite fixe et les tests qu'elle contient."""
    tests = build_tests_list([SMOKE_SUITE])
    return jsonify({
        'file': SMOKE_SUITE.name,
        'tests': [test['name'] for test in tests],
    })


@execution_bp.route('/last-run', methods=['GET'])
def last_run():
    """Retourne le résumé du dernier run joué, ou None si le dépôt n'en a aucun."""
    return jsonify({'last_run': history.last_run()})


@execution_bp.route('/last-run/<path:filename>', methods=['GET'])
def last_run_file(filename):
    """Sert un fichier du dernier run : son log, son rapport, ses captures.

    Robot lie ces fichiers entre eux par des chemins relatifs (le rapport renvoie au
    log, le log affiche les captures d'échec) : les servir depuis une racine commune
    est ce qui garde ces liens vivants.
    """
    run_dir = history.last_run_dir()
    if run_dir is None:
        return jsonify({'error': 'Aucun run disponible'}), 404
    return _serve_report_file(run_dir, filename, f'Fichier {filename} introuvable')


@execution_bp.route('/stop-test', methods=['POST'])
def stop_test():
    """
    Arrête une exécution en créant le fichier stop_signal scopé.
    
    Body:
        { 'session_id': str }
    """
    try:
        data = require_json_object(request.get_json(silent=True))
        session_id = validate_string(data.get('session_id', ''), 'session_id')
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    if session_id:
        stop_path = registry.stop_signal_path(session_id)
        stop_path.parent.mkdir(parents=True, exist_ok=True)
        stop_path.write_text('STOP', encoding='utf-8')
        _emit_to_session('log', {'message': '🛑 Arrêt demandé...'}, session_id)
    else:
        paths.STOP_SIGNAL.parent.mkdir(parents=True, exist_ok=True)
        paths.STOP_SIGNAL.write_text('STOP', encoding='utf-8')
        socketio.emit('log', {'message': '🛑 Arrêt demandé...'})

    return jsonify({'status': 'stop_requested', 'session_id': session_id})


@execution_bp.route('/log', methods=['POST'])
def receive_log():
    """Reçoit un log depuis un listener RF et le broadcast dans la room de session."""
    try:
        data = require_json_object(request.get_json(silent=True))
        message = validate_string(data.get('message', ''), 'message')
        level = validate_string(data.get('level', 'info'), 'level', allow_empty=False)
        session_id = validate_string(data.get('session_id', ''), 'session_id')
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    _emit_to_session('log', {'message': message, 'level': level}, session_id)
    return jsonify({'status': 'ok'})


@execution_bp.route('/log-link', methods=['POST'])
def receive_log_link():
    """Reçoit le nom d'un fichier de log et le broadcast dans la room."""
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    _emit_to_session('log-link', {
        'log_link': data.get('log_link', ''),
        'is_merged': data.get('is_merged', False),
        'has_rerun': data.get('has_rerun', False),
    }, session_id)
    return jsonify({'status': 'ok'})


@execution_bp.route('/log-directory', methods=['POST'])
def receive_log_directory():
    """Valide et mémorise le dossier de rapports sans changer l'événement UI."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps JSON invalide'}), 400

    session_id = data.get('session_id', '')
    try:
        log_dir = _resolve_report_directory(data.get('log_directory'))
    except (OSError, ValueError) as exc:
        logger.warning("Dossier de rapports refusé pour %s : %s", session_id or 'default', exc)
        return jsonify({'error': 'Dossier de rapports invalide'}), 400

    serialized_log_dir = str(log_dir)
    if session_id:
        _session_log_dirs[session_id] = serialized_log_dir
        registry.update(session_id, log_directory=serialized_log_dir)
    else:
        _session_log_dirs['_default'] = serialized_log_dir

    _emit_to_session('log-directory', {'log_directory': serialized_log_dir}, session_id)
    return jsonify({'status': 'ok'})


@execution_bp.route('/test-result', methods=['POST'])
def receive_test_result():
    """Reçoit le verdict d'un test et le diffuse dans la room de session.

    Sans cet événement, l'interface devait deviner le résultat en cherchant des mots
    dans les lignes de log - des chaînes d'affichage, pas un contrat.
    """
    try:
        data = require_json_object(request.get_json(silent=True))
        longname = validate_string(data.get('longname', ''), 'longname', allow_empty=False)
        name = validate_string(data.get('name', ''), 'name')
        status = validate_string(data.get('status', ''), 'status', allow_empty=False)
        message = validate_string(data.get('message', ''), 'message')
        session_id = validate_string(data.get('session_id', ''), 'session_id')
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    _emit_to_session(
        'test-result',
        {
            'longname': longname,
            'name': name or longname,
            'status': status,
            'message': message,
            'elapsed': data.get('elapsed', 0),
        },
        session_id,
    )
    return jsonify({'status': 'ok'})


@execution_bp.route('/progress', methods=['POST'])
def receive_progress():
    """Reçoit l'avancement du run et le broadcast dans la room."""
    data = request.get_json() or {}
    _emit_to_session(
        'progress',
        {
            'done': data.get('done', 0),
            'total': data.get('total', 0),
            'phase': data.get('phase', 'run'),
        },
        data.get('session_id', ''),
    )
    return jsonify({'status': 'ok'})


@execution_bp.route('/final-status', methods=['POST'])
def receive_final_status():
    """Reçoit le statut final de la suite et le broadcast dans la room.

    Les compteurs voyagent en clair : l'interface ne doit pas avoir à deviner un
    verdict en cherchant des mots dans une phrase de résumé.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    _emit_to_session('final-status', {
        'status': data.get('status', ''),
        'is_merged': data.get('is_merged', False),
        'passed': data.get('passed'),
        'failed': data.get('failed'),
        'skipped': data.get('skipped'),
        'total': data.get('total'),
        'rerun': data.get('rerun'),
    }, session_id)
    return jsonify({'status': 'ok'})


def _resolve_report_directory(raw_directory: object) -> Path:
    """Résout un dossier existant et vérifie qu'il reste sous ``paths.REPORTS``.

    Args:
        raw_directory: Chemin reçu du listener Robot ou du service de rerun.

    Returns:
        Le chemin absolu canonique du dossier autorisé.

    Raises:
        ValueError: Si la valeur est absente ou sort de la racine des rapports.
        FileNotFoundError: Si le dossier n'existe pas.
    """
    if not isinstance(raw_directory, str) or not raw_directory.strip():
        raise ValueError("chemin absent")

    report_root = paths.REPORTS.resolve()
    candidate = Path(raw_directory).expanduser().resolve()
    if not candidate.is_relative_to(report_root):
        raise ValueError("chemin hors de la racine des rapports")
    if not candidate.is_dir():
        raise FileNotFoundError("dossier de rapports introuvable")
    return candidate


def _get_log_dir(session_id: str) -> Path | None:
    """Retourne le dossier validé d'une session ou le repli historique par défaut."""
    stored_directory = _session_log_dirs.get(
        session_id,
        _session_log_dirs.get('_default', ''),
    )
    if not stored_directory:
        return None
    try:
        return _resolve_report_directory(stored_directory)
    except (OSError, ValueError) as exc:
        logger.warning("Dossier de rapports devenu indisponible pour %s : %s", session_id, exc)
        return None


def _serve_report_file(base_directory: Path, filename: str, missing_message: str):
    """Sert un fichier borné à son dossier de rapport, y compris ses sous-dossiers."""
    resolved_base = base_directory.resolve()
    candidate = (resolved_base / filename).resolve()
    if not candidate.is_relative_to(resolved_base) or not candidate.is_file():
        return jsonify({'error': missing_message}), 404
    relative_filename = candidate.relative_to(resolved_base).as_posix()
    return send_from_directory(str(resolved_base), relative_filename)


@execution_bp.route('/logs/<session_id>/standard/<path:filename>')
def serve_standard_logs(session_id, filename):
    """Sert un fichier de log depuis le dossier de rapports (racine)."""
    log_dir = _get_log_dir(session_id)
    if not log_dir:
        return jsonify({'error': 'Log directory not set'}), 500
    return _serve_report_file(log_dir, filename, f'File {filename} not found')


@execution_bp.route('/logs/<session_id>/original/<path:filename>')
def serve_original_logs(session_id, filename):
    """Sert un fichier de log depuis Output_original/."""
    log_dir = _get_log_dir(session_id)
    if not log_dir:
        return jsonify({'error': 'Log directory not set'}), 500
    return _serve_report_file(
        log_dir / "Output_original",
        filename,
        f'File {filename} not found in original directory',
    )


@execution_bp.route('/logs/<session_id>/merged/<path:filename>')
def serve_merged_logs(session_id, filename):
    """Sert un fichier de log depuis Output_merge/."""
    log_dir = _get_log_dir(session_id)
    if not log_dir:
        return jsonify({'error': 'Log directory not set'}), 500
    return _serve_report_file(
        log_dir / "Output_merge",
        filename,
        f'File {filename} not found in merged directory',
    )


def _open_report_directory(log_dir: Path) -> None:
    """Ouvre un dossier déjà validé avec l'API native du système d'exploitation."""
    if platform.system() == 'Windows':
        os.startfile(str(log_dir))
    elif platform.system() == 'Darwin':
        subprocess.run(['open', str(log_dir)], check=True)
    else:
        subprocess.run(['xdg-open', str(log_dir)], check=True)


@execution_bp.route('/open-directory', methods=['POST'])
def open_directory():
    """Ouvre le dossier validé de la session dans l'explorateur de fichiers."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps JSON invalide'}), 400
    session_id = data.get('session_id', '')
    log_dir = _get_log_dir(session_id)

    if not log_dir:
        return jsonify({'error': 'Log directory not set'}), 500

    try:
        _open_report_directory(log_dir)
        return jsonify({'status': 'ok', 'directory': str(log_dir)})
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Ouverture du dossier de rapports impossible : %s", exc)
        logger.debug("Détail de l'ouverture du dossier de rapports", exc_info=True)
        return jsonify({'error': 'Ouverture du dossier de rapports impossible'}), 500


@execution_bp.route('/sessions', methods=['GET'])
def list_sessions():
    """Retourne la liste des sessions actives."""
    sessions = registry.get_all()
    return jsonify({
        'sessions': [
            {
                'session_id': s.session_id,
                'browser': s.browser,
                'workflow': s.workflow,
                'status': s.status,
                'dt_stamp': s.dt_stamp,
            }
            for s in sessions.values()
        ],
        'running_count': registry.count_running()
    })

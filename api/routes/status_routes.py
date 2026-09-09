"""
Routes API pour le statut d'exécution.

Multi-session : le statut est dérivé du session_registry.
Chaque session a son propre état.

Endpoints :
- GET /execution-status : État global (au moins une session en cours ?)
- POST /execution-complete : Marque une session comme terminée
"""

import datetime

from flask import Blueprint, jsonify, request

from api.socketio_instance import socketio
from core.session_registry import registry

status_bp = Blueprint('status', __name__)


def get_client_ip(req):
    """Récupère l'IP réelle du client en tenant compte des proxies"""
    if req.headers.get('X-Forwarded-For'):
        return req.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif req.headers.get('X-Real-IP'):
        return req.headers.get('X-Real-IP')
    return req.remote_addr


@status_bp.route('/execution-status', methods=['GET'])
def get_execution_status():
    """Retourne le statut d'exécution global + détail par session."""
    running = registry.get_running()
    all_sessions = registry.get_all()
    
    return jsonify({
        'is_running': len(running) > 0,
        'running_count': len(running),
        'sessions': [
            {
                'session_id': s.session_id,
                'browser': s.browser,
                'workflow': s.workflow,
                'status': s.status,
                'started_by_ip': s.started_by_ip,
            }
            for s in all_sessions.values()
        ]
    })


@status_bp.route('/execution-complete', methods=['POST'])
def execution_complete():
    """Termine une session et notifie le frontend."""
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    
    if session_id:
        registry.update(session_id, status='completed')
        socketio.emit('execution-complete', {'session_id': session_id}, room=session_id)
        socketio.emit('execution_status_changed', {
            'isRunning': registry.count_running() > 0,
            'runningCount': registry.count_running(),
            'session_id': session_id,
            'timestamp': datetime.datetime.now().isoformat()
        })
    else:
        socketio.emit('execution-complete')
        socketio.emit('execution_status_changed', {
            'isRunning': False,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    return jsonify({'status': 'success', 'session_id': session_id})

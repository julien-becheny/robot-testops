"""
Routes API pour les campagnes de test (CRUD + matrice), pilotees depuis TestOps.

Endpoints :
- GET    /campaigns                 : liste des campagnes + progression
- POST   /campaigns                 : cree une campagne (tests x cibles -> matrice)
- GET    /campaigns/<id>            : une campagne + progression
- GET    /campaigns/<id>/cells      : la matrice (cellules) d'une campagne
- POST   /campaigns/<id>/activate   : passe la campagne en « active »
- POST   /campaigns/<id>/close      : passe la campagne en « closed »
- DELETE /campaigns/<id>            : supprime la campagne (et ses cellules)

L'EXECUTION progressive d'une campagne arrive dans un increment suivant.
"""

import threading

from flask import Blueprint, jsonify, request, send_from_directory

from api.socketio_instance import socketio
from core.paths import paths
from core.session_registry import registry
from services.campaigns.execution import run_campaign_batch
from services.campaigns.manager import (
    create_campaign,
    delete_campaign,
    get_campaign,
    get_campaign_cells,
    list_campaigns,
    reset_failed_cells,
    set_status,
)
from services.campaigns.report import build_campaign_report

campaign_bp = Blueprint('campaign', __name__)


@campaign_bp.route('/campaigns', methods=['GET'])
def campaigns_list():
    """Liste des campagnes avec leur progression."""
    return jsonify({'campaigns': list_campaigns()})


@campaign_bp.route('/campaigns', methods=['POST'])
def campaigns_create():
    """Cree une campagne : { name, include_tags, exclude_tags, targets, config }."""
    data = request.get_json() or {}
    try:
        campaign = create_campaign(
            name=data.get('name'),
            include_tags=data.get('include_tags', []),
            exclude_tags=data.get('exclude_tags', []),
            targets=data.get('targets', []),
            config=data.get('config', {}),
        )
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'campaign': campaign}), 201


@campaign_bp.route('/campaigns/<campaign_id>', methods=['GET'])
def campaigns_get(campaign_id):
    """Une campagne + sa progression."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'campaign': campaign})


@campaign_bp.route('/campaigns/<campaign_id>/cells', methods=['GET'])
def campaigns_cells(campaign_id):
    """La matrice (cellules test x cible) d'une campagne."""
    if not get_campaign(campaign_id):
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'cells': get_campaign_cells(campaign_id)})


@campaign_bp.route('/campaigns/<campaign_id>/run', methods=['POST'])
def campaigns_run(campaign_id):
    """Lance un lot : joue jusqu'a N cellules « todo » d'une cible.

    Body : { browser, device, count }. La cible doit appartenir a la campagne.
    """
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campagne introuvable'}), 404
    data = request.get_json() or {}
    browser = str(data.get('browser', '')).lower()
    device = str(data.get('device', '')).lower()
    try:
        count = int(data.get('count', 10) or 10)
    except (TypeError, ValueError):
        count = 10
    targets = {(t.get('browser'), t.get('device')) for t in campaign.get('targets', [])}
    if (browser, device) not in targets:
        return jsonify({'error': f'Cible hors campagne : {browser}+{device}'}), 400

    session = registry.create_session(browser=browser, workflow='campaign')
    thread = threading.Thread(
        target=run_campaign_batch,
        args=(campaign_id, browser, device, count, session.session_id),
        daemon=True,
    )
    thread.start()
    return jsonify({'status': 'started', 'session_id': session.session_id})


@campaign_bp.route('/campaigns/<campaign_id>/activate', methods=['POST'])
def campaigns_activate(campaign_id):
    """Passe la campagne en « active »."""
    campaign = set_status(campaign_id, 'active')
    if not campaign:
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'campaign': campaign})


@campaign_bp.route('/campaigns/<campaign_id>/close', methods=['POST'])
def campaigns_close(campaign_id):
    """Passe la campagne en « closed »."""
    campaign = set_status(campaign_id, 'closed')
    if not campaign:
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'campaign': campaign})


@campaign_bp.route('/campaigns/<campaign_id>/reset-failed', methods=['POST'])
def campaigns_reset_failed(campaign_id):
    """Remet les cellules en echec a « a jouer » (pour rejouer les echecs)."""
    n = reset_failed_cells(campaign_id)
    if n is None:
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'status': 'ok', 'reset': n})


@campaign_bp.route('/campaigns/<campaign_id>', methods=['DELETE'])
def campaigns_delete(campaign_id):
    """Supprime la campagne et ses cellules."""
    if not delete_campaign(campaign_id):
        return jsonify({'error': 'Campagne introuvable'}), 404
    return jsonify({'status': 'deleted'})


@campaign_bp.route('/campaigns/<campaign_id>/report', methods=['POST'])
def campaigns_build_report(campaign_id):
    """Genere (ou regenere) le rapport agrege de tous les lots joues."""
    if not get_campaign(campaign_id):
        return jsonify({'error': 'Campagne introuvable'}), 404
    result = build_campaign_report(campaign_id)
    if not result:
        return jsonify({'error': 'Aucun lot joue a agreger.'}), 400
    return jsonify({'status': 'ok', 'sources': result['sources'],
                    'url': f'/campaigns/{campaign_id}/report/report.html'})


@campaign_bp.route('/campaigns/<campaign_id>/report/<path:filename>', methods=['GET'])
def campaigns_serve_report(campaign_id, filename):
    """Sert un fichier du rapport agrege (report.html, log.html, ...)."""
    report_dir = paths.get_campaign_report_folder(campaign_id)
    if not (report_dir / filename).exists():
        return jsonify({'error': 'Fichier introuvable'}), 404
    return send_from_directory(str(report_dir), filename)


@campaign_bp.route('/campaign-updated', methods=['POST'])
def campaign_updated():
    """Recu du runner de campagne -> pousse « campaign_updated » dans la room de session."""
    data = request.get_json() or {}
    session_id = data.get('session_id', '')
    payload = {'campaign_id': data.get('campaign_id')}
    if session_id:
        socketio.emit('campaign_updated', {**payload, 'session_id': session_id}, room=session_id)
    else:
        socketio.emit('campaign_updated', payload)
    return jsonify({'status': 'ok'})

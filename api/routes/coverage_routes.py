"""
Routes API pour la couverture fonctionnelle.

Endpoints :
- GET  /coverage         : analyse à la demande (rapport + anomalies détectées)
- POST /coverage/export  : génère le rapport HTML autonome et renvoie son URL
- GET  /coverage/report  : sert le rapport HTML généré
"""

from flask import Blueprint, jsonify, send_from_directory

from core.paths import paths
from services.coverage import analyse, write_html

coverage_bp = Blueprint('coverage', __name__)

_HTML_NAME = 'functional_coverage.html'


@coverage_bp.route('/coverage', methods=['GET'])
def coverage():
    """Analyse le référentiel et le code des tests, sans dépendre d'une exécution."""
    report, findings = analyse()
    return jsonify({
        'report': report,
        'findings': [vars(finding) for finding in findings],
    })


@coverage_bp.route('/coverage/export', methods=['POST'])
def export_coverage():
    """Écrit le rapport HTML autonome, partageable par simple lien."""
    report, _ = analyse()
    write_html(report, paths.RESULTS / _HTML_NAME)
    return jsonify({'url': '/coverage/report'})


@coverage_bp.route('/coverage/report', methods=['GET'])
def coverage_report():
    """Sert le rapport HTML généré."""
    if not (paths.RESULTS / _HTML_NAME).exists():
        return jsonify({'error': 'Rapport non généré'}), 404
    return send_from_directory(paths.RESULTS, _HTML_NAME)

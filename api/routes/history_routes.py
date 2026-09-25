"""
Routes API pour la santé de la suite de tests.

Endpoints :
- GET /suite-health : ingère les runs pas encore vus, puis rend l'état de chaque test
- GET /run-diff : ce qui a changé entre le dernier run et le dernier run comparable
- GET /health-dashboard : le dashboard de tendances (HTML autonome), remis à jour
- GET /run-log/<run_id> : le log Robot d'un run, vers lequel pointe le dashboard
"""

import re
from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

from core.paths import paths
from services.execution.history import RESULT_LAYOUTS
from services.history import dashboard, retention
from services.history.diff import last_run_diff
from services.history.ingest import ingest_new_runs
from services.history.stability import suite_health

history_bp = Blueprint('history', __name__)

# Un identifiant de run nomme un dossier : ni séparateur ni point, donc aucun `..` à
# désamorcer plus loin.
RUN_ID = re.compile(r'^[0-9A-Za-z_-]{1,64}$')


@history_bp.route('/suite-health', methods=['GET'])
def get_suite_health():
    """Met l'historique à jour puis rend le verdict de chaque test.

    L'ingestion est déclenchée ici et pas à l'exécution des tests : la source de vérité
    est le dossier de rapports, donc un run lancé en ligne de commande ou par la CI entre
    dans l'historique au même titre qu'un run lancé depuis l'interface.

    La purge vient après, jamais avant : un rapport effacé sans avoir été lu serait un
    trou définitif dans l'historique.
    """
    ingest_new_runs()
    retention.purge_old_runs()
    return jsonify(suite_health())


@history_bp.route('/health-dashboard', methods=['GET'])
def get_health_dashboard():
    """Rend le dashboard de tendances, après y avoir versé les runs nouveaux."""
    ingest_new_runs()
    report = dashboard.refresh()
    if report is None:
        return jsonify({'error': 'Dashboard indisponible'}), 503
    return send_from_directory(str(report.parent), report.name)


@history_bp.route('/run-log/<run_id>', methods=['GET'])
def get_run_log(run_id):
    """Sert le log Robot d'un run passé, cible des liens du dashboard."""
    if not RUN_ID.match(run_id):
        return jsonify({'error': 'Run inconnu'}), 404

    root = paths.REPORTS.resolve()
    log = _log_of(root / run_id, root)
    if log is None:
        return jsonify({'error': 'Log introuvable (run purgé ?)'}), 404
    return send_from_directory(str(root), log.relative_to(root).as_posix())


def _log_of(run_dir: Path, root: Path) -> Path | None:
    """Retourne le log qui fait foi pour ce run, borné à la racine des rapports."""
    for _output_name, log_name in RESULT_LAYOUTS:
        candidate = (run_dir / log_name).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    return None


@history_bp.route('/run-diff', methods=['GET'])
def get_run_diff():
    """Rend ce qui a changé depuis le dernier run de même périmètre.

    Même ingestion préalable que la santé de la suite, pour la même raison : le dernier
    run peut venir d'ailleurs que de l'interface.
    """
    ingest_new_runs()
    return jsonify(last_run_diff())

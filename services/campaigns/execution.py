"""
Execution progressive d'une campagne : joue un LOT de cellules « todo » pour une
cible (navigateur + appareil), puis bascule ces cellules en passed/failed.

Reutilise l'orchestration RF existante (commands + runner + rerun combo-aware).
Tourne dans un thread du backend (comme run_workflow) ; le live per-test remonte
via le listener RF deja en place, et un event `campaign_updated` est emis en fin
de lot pour que l'UI rafraichisse la progression.

Modele : on ne touche QUE les cellules « todo » (on ne rejoue jamais un passed).
Une cellule jouee (passee ou echouee apres rerun immediat) sort du « todo ».
"""

import datetime
import xml.etree.ElementTree as ET

import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from services.campaigns.db import get_connection
from services.campaigns.manager import get_campaign
from services.execution import run_meta
from services.execution.commands import get_campaign_cmd
from services.execution.runner import (
    _notify_execution_complete,
    _was_manually_stopped,
    execute_rf_commands,
)

logger = get_logger(__name__)


def run_campaign_batch(campaign_id: str, browser: str, device: str, count: int,
                       session_id: str):
    """Joue jusqu'a `count` cellules « todo » de (campaign, browser, device)."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        _notify_execution_complete(session_id)
        return

    test_names = _select_todo_tests(campaign_id, browser, device, count)
    if not test_names:
        _emit_campaign_updated(session_id, campaign_id)
        _notify_execution_complete(session_id)
        return

    base_stamp = datetime.datetime.now().strftime("%Y_%m_%d-%H%M%S")
    dt_stamp = f"{base_stamp}_camp_{browser}_{device}_{session_id}"
    report_folder = paths.REPORTS / dt_stamp

    run_meta.write(dt_stamp, workflow='campaign', engine='playwright',
                   browser=browser, device=device)

    cmd = get_campaign_cmd(dt_stamp, test_names, session_id=session_id,
                           browser=browser, device=device)
    execute_rf_commands([cmd], session_id=session_id, notify_complete=False)

    if _was_manually_stopped(session_id):
        # Arret manuel : on NE fige PAS les cellules (elles restent « todo »).
        _emit_campaign_updated(session_id, campaign_id)
        _notify_execution_complete(session_id)
        return

    results = _parse_test_results(report_folder / "output.xml")
    _apply_results(campaign_id, browser, device, results, session_id, str(report_folder))

    _emit_campaign_updated(session_id, campaign_id)
    _notify_execution_complete(session_id)


def _select_todo_tests(campaign_id, browser, device, count):
    """Noms de tests des cellules « todo » de la cible (uniques, ordre stable)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT test_name FROM campaign_cells WHERE campaign_id=? AND platform='web' "
            "AND browser=? AND device=? AND status='todo' ORDER BY test_name LIMIT ?",
            (campaign_id, browser, device, max(1, int(count)))).fetchall()
    return list(dict.fromkeys(r["test_name"] for r in rows))


def _parse_test_results(xml_path):
    """{test_name: 'passed'|'failed'} depuis un output.xml Robot Framework."""
    results = {}
    try:
        root = ET.parse(str(xml_path)).getroot()
    except (OSError, ET.ParseError):
        return results
    for test in root.findall(".//test"):
        name = test.get("name", "")
        status = test.find("status")
        if name and status is not None:
            results[name] = "passed" if status.get("status", "").upper() == "PASS" else "failed"
    return results


def _apply_results(campaign_id, browser, device, results, session_id, report_path):
    """Bascule les cellules « todo » de la cible selon le resultat de chaque test."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        for name, status in results.items():
            conn.execute(
                "UPDATE campaign_cells SET status=?, last_session_id=?, report_path=?, "
                "updated_at=? WHERE campaign_id=? AND platform='web' AND browser=? AND "
                "device=? AND test_name=? AND status='todo'",
                (status, session_id, report_path, now, campaign_id, browser, device, name))


def _emit_campaign_updated(session_id, campaign_id):
    """Signale a l'UI (via l'API -> SocketIO) que la campagne a avance."""
    try:
        requests.post(f"{API_BASE_URL}/campaign-updated",
                     json={"session_id": session_id, "campaign_id": campaign_id}, timeout=5)
    except requests.RequestException as exc:
        logger.debug("Notification de campagne non envoyée : %s", exc)

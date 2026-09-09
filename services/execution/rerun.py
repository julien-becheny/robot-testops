"""
Gestion du re-run des tests échoués.

Workflow (identique à RFEM) :
1. Parse Output_original/output_original.xml pour extraire les tests FAIL
2. Relance ces tests dans Output_rerun/
3. Fusionne les résultats dans Output_merge/ via rebot --merge
4. Notifie l'UI avec les liens original + merged
"""

import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from services.execution.commands import (
    _actions_arg,
    _environment_arg,
    _listener_arg,
    robot_command,
)
from services.execution.runner import format_rf_command_for_log, run_rf_command

logger = get_logger(__name__)
ROBOT_TECHNICAL_ERROR_MIN = 251


class RerunOutputError(RuntimeError):
    """Signale qu'un fichier de résultat indispensable au rerun est inutilisable."""


def extract_failed_tests(xml_path: str) -> list[str]:
    """Extrait les noms des tests échoués depuis un résultat Robot Framework.

    Args:
        xml_path: Chemin vers le fichier ``output.xml`` original.

    Returns:
        La liste, éventuellement vide, des noms de tests en échec.

    Raises:
        RerunOutputError: Si le fichier est absent, illisible ou mal formé.
    """
    if not os.path.exists(xml_path):
        raise RerunOutputError(f"Fichier XML original introuvable : {xml_path}")

    try:
        tree = ET.parse(xml_path)
    except (ET.ParseError, OSError) as exc:
        raise RerunOutputError(f"Fichier XML original invalide : {xml_path}") from exc

    failed_tests = []
    for test in tree.getroot().findall(".//test"):
        status_node = test.find("status")
        if status_node is not None and status_node.get("status", "").upper() == "FAIL":
            failed_tests.append(test.get("name", ""))

    logger.info("[Rerun] %s test(s) échoué(s) détecté(s)", len(failed_tests))
    return failed_tests


def extract_counts(xml_path: str) -> dict:
    """Extrait les compteurs d'un résultat Robot.

    Args:
        xml_path: Chemin vers le fichier ``output.xml`` à lire.

    Returns:
        Un dictionnaire ``passed``/``failed``/``skipped``/``total``, à zéro si le
        fichier est inutilisable.
    """
    empty = {'passed': 0, 'failed': 0, 'skipped': 0, 'total': 0}
    try:
        stat = ET.parse(xml_path).getroot().find(".//statistics/total/stat")
        if stat is None:
            return empty
        counts = {
            'passed': int(stat.get("pass", 0)),
            'failed': int(stat.get("fail", 0)),
            'skipped': int(stat.get("skip", 0)),
        }
    except (ET.ParseError, OSError, ValueError) as exc:
        logger.warning("[Rerun] Compteurs indisponibles : %s", exc)
        return empty
    return {**counts, 'total': sum(counts.values())}


def extract_final_status(xml_path: str) -> str:
    """Construit un résumé lisible depuis les statistiques d'un résultat Robot.

    Args:
        xml_path: Chemin vers le fichier ``output.xml`` à résumer.

    Returns:
        Le nombre de tests passés et échoués, ou un libellé explicite lorsque les
        statistiques sont absentes ou que le fichier est inutilisable.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        stat = root.find(".//statistics/total/stat")
        if stat is not None:
            p = stat.get("pass", "0")
            f = stat.get("fail", "0")
            total = int(p) + int(f)
            return f"{total} tests : {p} passés, {f} échoués"
        return "Statut non disponible"
    except (ET.ParseError, OSError, ValueError) as exc:
        logger.warning("[Rerun] Erreur lors de l'extraction du statut : %s", exc)
        logger.debug("Détail de l'extraction du statut", exc_info=True)
        return "Erreur statut"


def _extract_suite_name(xml_path: str) -> str:
    """Extrait le nom de la suite racine ou retourne le nom de repli historique."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        suite = root.find("suite")
        if suite is not None:
            return suite.get("name", "Execution_Filtree")
    except (ET.ParseError, OSError) as exc:
        logger.warning("[Rerun] Nom de suite indisponible : %s", exc)
        logger.debug("Détail de l'extraction du nom de suite", exc_info=True)
    return "Execution_Filtree"


def rerun_failed_tests(report_folder: str, dt_stamp: str, session_id: str = None,
                       browser: str = 'chromium', device: str = 'desktop'):
    """
    Relance les tests echoues sur la MEME combo (navigateur + appareil) que le run
    d'origine, puis fusionne les resultats.

    Args:
        report_folder: Dossier racine du timestamp (contient Output_original/)
        dt_stamp: Timestamp de l'execution
        session_id: Identifiant optionnel utilisé pour isoler les événements UI
        browser: Navigateur du run d'origine (rejoue a l'identique)
        device: Appareil du run d'origine (profil d'emulation)
    """
    xml_path = os.path.join(report_folder, "Output_original", "output_original.xml")
    try:
        failed_tests = extract_failed_tests(xml_path)
    except RerunOutputError as exc:
        logger.error("[Rerun] Rerun abandonné : %s", exc)
        logger.debug("Détail de l'abandon du rerun", exc_info=True)
        return

    if not failed_tests:
        logger.info("[Rerun] Aucun test échoué à réexécuter")
        _notify_original_only(report_folder, session_id)
        return

    # Récupérer le nom de suite pour que rebot --merge fonctionne
    suite_name = _extract_suite_name(xml_path)

    rerun_dir = os.path.join(report_folder, "Output_rerun")
    os.makedirs(rerun_dir, exist_ok=True)

    command = robot_command()
    command += _listener_arg(session_id, phase='rerun')

    # `--test <nom>` en argument distinct : les noms de tests contenant des espaces,
    # des accents ou un `&` passent sans guillemets (aucun shell ne redécoupe).
    for test_name in failed_tests:
        command += ["--test", test_name]

    command += ["-d", str(rerun_dir)]
    command += ["-o", "output_rerun.xml", "-r", "report_rerun.html", "-l", "log_rerun.html"]
    command += ["-v", f"BROWSER:{browser}"]
    command += ["-v", f"DEVICE:{device}"]
    command += _environment_arg()
    command += _actions_arg()
    command += ["-N", suite_name]
    command += [str(paths.TEST_SUITES)]

    logger.info("[Rerun] Commande : %s", format_rf_command_for_log(command))
    rerun_exit_code = run_rf_command(command, session_id)
    if rerun_exit_code >= ROBOT_TECHNICAL_ERROR_MIN:
        logger.error("[Rerun] Erreur technique Robot, code de sortie : %s", rerun_exit_code)
        _notify_original_only(report_folder, session_id)
        return
    if rerun_exit_code:
        logger.warning(
            "[Rerun] Des tests restent en échec (code : %s), fusion maintenue",
            rerun_exit_code,
        )
    else:
        logger.info("[Rerun] Tous les tests rejoués sont passés")

    # Fusion des résultats
    _merge_outputs(report_folder, session_id, len(failed_tests))


def _merge_outputs(report_folder: str, session_id: str = None, rerun_count: int = 0) -> bool:
    """Fusionne les résultats original et rejoué avec Rebot.

    Un code Rebot compris entre 1 et 250 signifie que des tests restent en échec :
    le rapport reste valide et doit être publié. Les codes 251 à 255 représentent
    une erreur technique et provoquent un retour au rapport original.

    Args:
        report_folder: Dossier racine contenant ``Output_original`` et
            ``Output_rerun``.
        session_id: Identifiant optionnel utilisé pour isoler les événements UI.

    Returns:
        ``True`` si le rapport fusionné est stable et publié, sinon ``False``.
    """
    output_original = os.path.join(report_folder, "Output_original", "output_original.xml")
    output_rerun = os.path.join(report_folder, "Output_rerun", "output_rerun.xml")

    if not (os.path.exists(output_original) and os.path.exists(output_rerun)):
        logger.warning("[Rerun] Fichiers manquants pour la fusion")
        _notify_original_only(report_folder, session_id)
        return False

    merge_dir = os.path.join(report_folder, "Output_merge")
    os.makedirs(merge_dir, exist_ok=True)

    logger.info("[Rerun] Fusion des résultats")
    rebot_command = [
        sys.executable,
        "-m",
        "robot.rebot",
        "-d",
        merge_dir,
        "-o",
        "output_merge.xml",
        "-r",
        "report_merge.html",
        "-l",
        "log_merge.html",
        "--merge",
        output_original,
        output_rerun,
    ]
    try:
        result = subprocess.run(rebot_command)
    except OSError as exc:
        logger.error("[Rerun] Impossible de lancer Rebot : %s", exc)
        logger.debug("Détail de l'échec de lancement de Rebot", exc_info=True)
        _notify_original_only(report_folder, session_id)
        return False

    if result.returncode >= ROBOT_TECHNICAL_ERROR_MIN:
        logger.error("[Rerun] Erreur technique Rebot, code de sortie : %s", result.returncode)
        _notify_original_only(report_folder, session_id)
        return False
    if result.returncode:
        logger.warning(
            "[Rerun] Fusion générée avec des tests en échec (code : %s)",
            result.returncode,
        )
    else:
        logger.info("[Rerun] Fusion Rebot terminée sans test en échec")

    # Attendre la stabilité des fichiers
    if not _wait_for_stable_files(merge_dir):
        _notify_original_only(report_folder, session_id)
        return False

    # Notifier l'UI avec les deux rapports
    _notify_merged_results(report_folder, merge_dir, session_id, rerun_count)
    return True


def _wait_for_stable_files(merge_dir: str, max_wait: int = 30) -> bool:
    """Attend que les fichiers fusionnés existent et cessent de grossir.

    Args:
        merge_dir: Dossier dans lequel Rebot écrit les fichiers fusionnés.
        max_wait: Durée maximale d'attente en secondes.

    Returns:
        ``True`` si les deux fichiers sont présents, non vides et stables avant
        le délai maximal, sinon ``False``.
    """
    merged_log = os.path.join(merge_dir, "log_merge.html")
    merged_xml = os.path.join(merge_dir, "output_merge.xml")
    wait_time = 0

    while wait_time < max_wait:
        if os.path.exists(merged_log) and os.path.exists(merged_xml):
            try:
                log_size = os.path.getsize(merged_log)
                xml_size = os.path.getsize(merged_xml)
                time.sleep(2)
                wait_time += 2
                if (os.path.getsize(merged_log) == log_size and
                        os.path.getsize(merged_xml) == xml_size and
                        log_size > 0 and xml_size > 0):
                    logger.info("[Rerun] Fichiers fusionnés stables après %s s", wait_time)
                    return True
            except OSError as exc:
                logger.debug("[Rerun] Fichiers fusionnés temporairement illisibles : %s", exc)
                time.sleep(2)
                wait_time += 2
        else:
            time.sleep(2)
            wait_time += 2

    logger.warning("[Rerun] Timeout après %s s : fichiers fusionnés instables", max_wait)
    return False


def _post_notification(route: str, payload: dict, timeout: int = 3) -> None:
    """Envoie une notification interne et vérifie la réponse HTTP.

    Args:
        route: Route relative de l'API TestOps, précédée de ``/``.
        payload: Corps JSON à transmettre.
        timeout: Délai maximal de la requête en secondes.

    Raises:
        requests.RequestException: Si l'appel réseau ou la réponse HTTP échoue.
    """
    response = requests.post(f"{API_BASE_URL}{route}", json=payload, timeout=timeout)
    response.raise_for_status()


def _notify_original_only(report_folder: str, session_id: str = None) -> None:
    """Notifie l'UI qu'aucun rerun n'était nécessaire et expose le rapport original."""
    try:
        _post_notification('/log-link', {
            'log_link': 'log_original.html',
            'is_merged': False,
            'has_rerun': False,
            'session_id': session_id or '',
        })
        _post_notification('/log-directory', {
            'log_directory': os.path.join(report_folder, "Output_original"),
            'session_id': session_id or '',
        })
    except requests.RequestException as exc:
        logger.warning("[Rerun] Notification du rapport original échouée : %s", exc)
        logger.debug("Détail de la notification du rapport original", exc_info=True)


def _notify_merged_results(
    report_folder: str,
    merge_dir: str,
    session_id: str = None,
    rerun_count: int = 0,
) -> None:
    """Expose dans l'UI les rapports original et fusionné ainsi que le statut final."""
    sid = session_id or ''
    try:
        # Lien rapport original
        _post_notification('/log-link', {
            'log_link': 'log_original.html',
            'is_merged': False,
            'has_rerun': True,
            'session_id': sid,
        })

        # Lien rapport fusionné
        _post_notification('/log-link', {
            'log_link': 'log_merge.html',
            'is_merged': True,
            'session_id': sid,
        })

        # Répertoire racine
        _post_notification('/log-directory', {
            'log_directory': report_folder,
            'session_id': sid,
        })

        # Statut final basé sur le merge
        merged_xml = os.path.join(merge_dir, "output_merge.xml")
        merged_status = extract_final_status(merged_xml)
        _post_notification('/final-status', {
            'status': merged_status,
            'is_merged': True,
            'session_id': sid,
            # Un test vert au second essai n'est pas un test vert : le dire.
            'rerun': rerun_count,
            **extract_counts(merged_xml),
        })

        logger.info("[Rerun] Notifications de fusion envoyées")
    except requests.RequestException as exc:
        logger.warning("[Rerun] Notification des résultats fusionnés échouée : %s", exc)
        logger.debug("Détail de la notification des résultats fusionnés", exc_info=True)

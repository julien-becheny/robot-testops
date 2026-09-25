"""
Execution d'un test de charge LOCUST (modele FERME, lance en subprocess du backend).

Repartition des roles :
  - locustfile_testops.py (dans le subprocess) POSTe le LIVE en direct et ECRIT
    le resultat final dans un fichier (il a acces aux stats en memoire) ;
  - ce runner lance/surveille le subprocess (stop_signal, cleanup), LIT le
    resultat, y ajoute l'analyse + le verdict, publie et historise ;
  - runner_common.py porte la plomberie partagee avec le runner k6.

Aligne sur l'architecture du projet (comme le listener Robot Framework, la
communication passe par des POST HTTP que l'API repousse en SocketIO).
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from core.session_registry import registry
from services.load import runner_common as common
from services.load.analysis import analyze, compute_status
from services.load.targets import get_target

_LOCUSTFILE = os.path.join(os.path.dirname(__file__), "locustfile_testops.py")

# Dashboard Locust temps reel (mode web). Un port LIBRE est choisi par run (par la
# route) : evite les conflits si un ancien dashboard traine encore sur le port.
DEFAULT_WEB_PORT = 8089
logger = get_logger(__name__)


def run_load_test(target_id: str, test_type: str, params: dict, session_id: str,
                  web_port: int = DEFAULT_WEB_PORT) -> None:
    """Lance Locust sur une cible autorisée et publie son résultat final.

    Args:
        target_id: Identifiant de la cible déclarée dans la liste blanche.
        test_type: Profil de charge demandé.
        params: Paramètres validés du profil de charge.
        session_id: Identifiant utilisé pour isoler les événements UI.
        web_port: Port libre attribué au dashboard Locust.
    """
    target = get_target(target_id)
    if not target:
        common.fail(session_id, f"Cible inconnue : {target_id}")
        return

    if importlib.util.find_spec("locust") is None:
        common.fail(session_id, (
            "Locust n'est pas installé dans l'environnement Python du backend. "
            "Démarre le backend avec `uv run python api/app.py` (uv choisit "
            "l'environnement du projet), ou lance `uv sync`."))
        return

    result_path = paths.TEMP / f"load_result_{session_id}.json"
    stop_path = registry.stop_signal_path(session_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    common.clean(result_path, stop_path)

    env = dict(os.environ)
    env.update({
        "TESTOPS_API": API_BASE_URL,
        "SESSION_ID": session_id,
        "TARGET_ID": target_id,
        "TEST_TYPE": test_type,
        "PARAMS_JSON": json.dumps(params),
        "STOP_SIGNAL_PATH": str(stop_path),
        "RESULT_PATH": str(result_path),
    })
    # Un seul dashboard Locust a la fois : coupe le precedent (libere ses ressources).
    common.kill_previous()

    # Mode WEB (pas --headless) : dashboard temps reel sur le port alloue. --autostart
    # demarre le test immediatement ; --autoquit laisse le dashboard consultable un
    # moment apres la fin, puis Locust s'arrete seul.
    cmd = [sys.executable, "-m", "locust", "-f", _LOCUSTFILE,
           "--autostart", "--autoquit", "300",
           "-H", target["base_url"], "--web-port", str(web_port),
           "--loglevel", "WARNING"]
    cmd += _processes_args(params, session_id)

    registry.update(session_id, status="running")
    # Le port seul, jamais l'URL : « localhost » designerait le poste du lecteur, pas
    # la machine d'injection. Le bouton de l'interface, lui, reconstruit la bonne adresse.
    common.emit_log(session_id, f"🚀 Locust sur « {target['label']} » - type {test_type} - "
                                f"dashboard live sur le port {web_port}")

    try:
        proc = subprocess.Popen(cmd, env=env)
    except FileNotFoundError:
        logger.error("[load] Exécutable Python ou module Locust introuvable")
        common.fail(session_id, "Locust introuvable. Installe-le (pip install locust).")
        return
    except OSError as exc:
        logger.error("[load] Échec du lancement de Locust : %s", exc)
        logger.debug("Détail de l'échec du lancement de Locust", exc_info=True)
        common.fail(session_id, f"Échec du lancement de Locust : {exc}")
        return

    common.remember(proc)
    registry.update(session_id, process=proc)

    outcome = _wait_for_result(proc, result_path, stop_path)
    if outcome == "stopped":
        common.terminate(proc)
    registry.update(session_id, status="stopped" if outcome == "stopped" else "completed")

    result = common.read_result(result_path, proc.returncode)
    if outcome == "stopped" and not result.get("breach"):
        result["stopped"] = True
    if not result.get("error"):
        common.describe_injector(result, target, params)
        common.compare_to_baseline(result, target_id, test_type, params)
        result["analysis"] = analyze(result, params, test_type)
        result["status"] = compute_status(result, params)
        common.write_report(session_id, target_id, target, test_type, params, result)
    common.emit_log(session_id, common.verdict_log(result))
    common.post_result(session_id, result)
    common.save_history(target_id, target, test_type, params, result)
    common.notify_complete(session_id)


def _processes_args(params: dict, session_id: str) -> list[str]:
    """Repartit l'injection sur plusieurs coeurs quand la plateforme le permet.

    Locust forke pour cela : l'option n'existe pas sous Windows.
    """
    processes = int(params.get("processes") or 1)
    if processes <= 1:
        return []
    if sys.platform == "win32":
        common.emit_log(session_id, "⚠️ Multi-processus indisponible sous Windows : "
                                    "injection sur un seul coeur.")
        return []
    return ["--processes", str(processes)]


def _wait_for_result(proc, result_path: Path, stop_path: Path) -> str:
    """Attend le résultat final, l'arrêt manuel ou la fin inattendue de Locust.

    Le processus n'est pas attendu après l'écriture du résultat afin que le
    dashboard web reste consultable.

    Args:
        proc: Processus Locust surveillé.
        result_path: Fichier JSON écrit à la fin du scénario.
        stop_path: Signal d'arrêt propre à la session.

    Returns:
        ``stopped`` pour un arrêt manuel, ``done`` pour un résultat écrit ou
        ``ended`` si le processus se termine sans résultat.
    """
    while True:
        if stop_path.exists():
            for _ in range(8):  # laisse le locustfile ecrire le resultat avant de couper
                if result_path.exists():
                    break
                time.sleep(0.5)
            return "stopped"
        if result_path.exists():
            return "done"
        if proc.poll() is not None:
            return "ended"
        time.sleep(1)

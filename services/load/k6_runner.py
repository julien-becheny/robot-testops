"""
Execution d'un test de charge K6 (modele OUVERT, lance en subprocess du backend).

k6 impose un DEBIT d'arrivees : contrairement a Locust, la charge produite ne
retombe pas quand le systeme ralentit (cf. regle LOAD_CLOSED). Repartition des roles :
  - k6_scenario.js (dans le subprocess) joue le scenario et ECRIT le resultat final
    au MEME format que le locustfile ;
  - ce runner lance/surveille le subprocess, interroge l'API REST de k6 pour le
    direct et la timeline, LIT le resultat, l'analyse, le publie et l'historise ;
  - runner_common.py porte la plomberie partagee avec le runner Locust.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import psutil
import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from core.session_registry import registry
from services.load import runner_common as common
from services.load.analysis import CPU_WARN_PCT, analyze, compute_status
from services.load.targets import get_target

_SCENARIO = os.path.join(os.path.dirname(__file__), "k6_scenario.js")

# API REST de k6 : desactivee par defaut depuis la v2, on l'active par run sur un port
# libre. Elle sert au direct ET a l'arret propre (un kill sauterait le resume final).
DEFAULT_API_PORT = 6565
POLL_S = 2

# Dashboard web integre a k6 (equivalent du dashboard Locust) : un ecran temps reel
# pendant le run, et un rapport HTML autonome consultable apres coup.
REPORTS_DIR = paths.REPORTS / "load"
# Le rapport n'a de graphes que si la duree du run depasse 3x cette periode : 10 s (le
# defaut de k6) priverait de courbes tous les runs courts.
DASHBOARD_PERIOD = "2s"
# k6 n'ecrit son resume qu'apres avoir ferme ses sorties, et la sortie dashboard attend
# que les navigateurs se deconnectent : passe ce delai, plus personne ne fermera l'onglet.
DASHBOARD_GRACE_S = 120
logger = get_logger(__name__)


def run_load_test(target_id: str, test_type: str, params: dict, session_id: str,
                  web_port: int = DEFAULT_API_PORT) -> None:
    """Lance k6 sur une cible autorisée et publie son résultat final.

    Args:
        target_id: Identifiant de la cible déclarée dans la liste blanche.
        test_type: Profil de charge demandé (modèle ouvert).
        params: Paramètres validés du profil de charge.
        session_id: Identifiant utilisé pour isoler les événements UI.
        web_port: Port libre attribué au dashboard web de k6.
    """
    target = get_target(target_id)
    if not target:
        common.fail(session_id, f"Cible inconnue : {target_id}")
        return

    if shutil.which("k6") is None:
        common.fail(session_id, (
            "k6 est introuvable dans le PATH. Installe-le (winget install k6 --source winget, "
            "brew install k6, ou https://grafana.com/docs/k6/latest/set-up/install-k6/) "
            "puis relance le backend."))
        return

    result_path = paths.TEMP / f"load_result_{session_id}.json"
    report_path = REPORTS_DIR / f"k6_{session_id}.html"
    stop_path = registry.stop_signal_path(session_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    common.clean(result_path, stop_path)

    env = dict(os.environ)
    env.update({
        "TESTOPS_API": API_BASE_URL,
        "SESSION_ID": session_id,
        "TARGET_ID": target_id,
        "TEST_TYPE": test_type,
        "BASE_URL": target["base_url"],
        "PARAMS_JSON": json.dumps(params),
        # handleSummary ecrit ce fichier : k6 traite la cle comme un chemin, slashs inclus.
        "RESULT_PATH": result_path.as_posix(),
        "K6_WEB_DASHBOARD": "true",
        "K6_WEB_DASHBOARD_PORT": str(web_port),
        "K6_WEB_DASHBOARD_PERIOD": DASHBOARD_PERIOD,
        "K6_WEB_DASHBOARD_EXPORT": report_path.as_posix(),
    })
    common.kill_previous()
    # L'API REST reste interne au runner : seul le dashboard est ouvert dans un navigateur.
    api_port = common.free_port()
    api_url = f"http://127.0.0.1:{api_port}"

    cmd = ["k6", "run", "--quiet", "--no-color",  # path-exec-ok: binaire k6, pas un module Python
           "--address", f"127.0.0.1:{api_port}", _SCENARIO]

    registry.update(session_id, status="running")
    common.emit_log(session_id, f"🚀 k6 sur « {target['label']} » - {test_type} - "
                                f"débit visé {params.get('rate')} req/s (modèle ouvert)")
    common.emit_log(session_id, f"📊 Dashboard k6 en direct sur le port {web_port}")

    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as exc:
        logger.error("[load] Échec du lancement de k6 : %s", exc)
        logger.debug("Détail de l'échec du lancement de k6", exc_info=True)
        common.fail(session_id, f"Échec du lancement de k6 : {exc}")
        return

    common.remember(proc)
    registry.update(session_id, process=proc)

    state = {"timeline": [], "breach": None, "cpu_max": 0.0}
    outcome = _follow(proc, api_url, session_id, result_path, stop_path, state, test_type)
    if outcome in ("stopped", "breached"):
        _wait_for_file(result_path, seconds=8)
    # Le rapport s'ecrit a la toute fin : couper k6 trop tot le tronquerait.
    exported = result_path.exists() and _wait_for_export(report_path, seconds=8)
    common.terminate(proc)
    registry.update(session_id, status="stopped" if outcome == "stopped" else "completed")

    result = common.read_result(result_path, proc.returncode)
    if exported:
        result["report_url"] = f"/load-report/{report_path.name}"
    if outcome == "abandoned":
        result["error"] = ("k6 n'a pas pu écrire son résumé : un onglet du dashboard est resté "
                           "ouvert après la fin du test. Le rapport HTML, lui, est complet.")
    if not result.get("error"):
        result["timeline"] = state["timeline"]
        result["breach"] = state["breach"]
        result["stopped"] = outcome == "stopped"
        # k6 ne mesure pas sa propre charge CPU, contrairement a Locust : sans ce releve,
        # rien ne distinguerait un systeme lent d'un injecteur a bout de souffle.
        result["injector_cpu_max"] = round(state["cpu_max"], 1) if state["cpu_max"] else None
        result["injector_cpu_warning"] = state["cpu_max"] >= CPU_WARN_PCT
        common.describe_injector(result, target, params)
        common.compare_to_baseline(result, target_id, test_type, params)
        result["analysis"] = analyze(result, params, test_type)
        result["status"] = compute_status(result, params)
        common.write_report(session_id, target_id, target, test_type, params, result)
    common.emit_log(session_id, common.verdict_log(result))
    common.post_result(session_id, result)
    common.save_history(target_id, target, test_type, params, result)
    common.notify_complete(session_id)


def _follow(proc, api_url: str, session_id: str, result_path: Path, stop_path: Path,
            state: dict, test_type: str) -> str:
    """Suit le run : relevés en direct, timeline, décrochage, arrêt manuel.

    Returns:
        ``stopped`` pour un arrêt manuel, ``breached`` quand le système a décroché,
        ``done`` quand le résultat est écrit, ``ended`` si k6 se termine sans rien produire,
        ``abandoned`` si le dashboard a retenu le résumé trop longtemps.
    """
    previous, started = None, time.monotonic()
    stalling, last_healthy = 0, None
    running_seen, ended_at = False, None
    cpu = _cpu_meter(proc)
    while True:
        if stop_path.exists():
            _request_stop(api_url)
            return "stopped"
        if result_path.exists():
            return "done"
        if proc.poll() is not None:
            return "ended"
        time.sleep(POLL_S)
        # Test fini mais k6 encore vivant : plus rien à mesurer, on attend son résumé.
        if ended_at is not None:
            if time.monotonic() - ended_at > DASHBOARD_GRACE_S:
                return "abandoned"
            continue
        load = cpu()
        state["cpu_max"] = max(state["cpu_max"], load or 0)
        sample = _sample(api_url, time.monotonic() - started, previous)
        if not sample:
            continue
        # Deux fenêtres d'affilée où des requêtes n'ont pas pu partir : le retard est
        # installé, pas accidentel (une allocation de VUs en produit une seule).
        if previous is not None and sample["dropped"] > previous["dropped"]:
            stalling += 1
        else:
            stalling, last_healthy = 0, sample
        previous = sample
        state["timeline"].append({k: sample[k] for k in
                                  ("t", "users", "rps", "p95_ms", "error_rate", "dropped")})
        common.emit_metrics(session_id, {
            "vus": sample["users"], "reqs_per_sec": sample["rps"],
            "p95_ms": sample["p95_ms"], "error_rate": sample["error_rate"],
            "dropped": sample["dropped"], "cpu": round(load, 1) if load else None,
        })
        if test_type == "open_capacity" and stalling >= 2:
            absorbed = (last_healthy or sample)["rps"]
            state["breach"] = {
                "t": sample["t"], "rps": absorbed, "p95_ms": sample["p95_ms"],
                "dropped": sample["dropped"], "cause": "dropped",
            }
            common.emit_log(session_id, f"🔴 Décrochage à {sample['t']:.0f} s : le système "
                                        f"absorbait ~{absorbed:.0f} req/s")
            _request_stop(api_url)
            return "breached"
        running = _is_running(api_url)
        running_seen = running_seen or running is True
        if running is False and running_seen:
            ended_at = time.monotonic()
            # Le front ferme sur ce signal la fenetre du dashboard qu'il a ouverte.
            common.emit_metrics(session_id, {"finished": True})
            common.emit_log(session_id, "⏳ Test terminé - fermeture du dashboard k6 : il "
                                        "retient le résumé tant qu'un onglet reste ouvert.")


def _cpu_meter(proc):
    """Rend un relève-compteur de la charge CPU du processus k6, en % de la machine.

    `cpu_percent()` compte 100 % par coeur occupé : sur une machine à 16 coeurs, k6 peut
    afficher 400 % sans être à la peine. On divise donc par le nombre de coeurs pour que
    le seuil de 90 % garde le sens qu'il a côté Locust : « la machine est à bout ».
    Le premier appel sert de référence et renvoie toujours 0.
    """
    cores = os.cpu_count() or 1
    try:
        process = psutil.Process(proc.pid)
        process.cpu_percent()
    except (psutil.Error, ValueError) as exc:
        logger.debug("[load] Charge CPU de k6 non mesurable : %s", exc)
        return lambda: None

    def read():
        try:
            return process.cpu_percent() / cores
        except psutil.Error:
            return None

    return read


def _sample(api_url: str, elapsed: float, previous: dict | None) -> dict | None:
    """Construit un relevé à partir des compteurs cumulés de l'API k6.

    k6 ne publie que des cumuls depuis le début du run : le débit instantané se
    calcule par différence avec le relevé précédent. Le p95, lui, reste cumulé.
    """
    metrics = _metrics(api_url)
    if not metrics:
        return None
    reqs = (metrics.get("http_reqs") or {}).get("count") or 0
    dropped = (metrics.get("dropped_iterations") or {}).get("count") or 0
    window = elapsed - previous["t"] if previous else elapsed
    produced = reqs - previous["reqs"] if previous else reqs
    return {
        "t": round(elapsed, 1),
        "reqs": reqs,
        "users": int((metrics.get("vus") or {}).get("value") or 0),
        "rps": round(produced / window, 1) if window > 0 else 0.0,
        "p95_ms": int((metrics.get("http_req_duration") or {}).get("p(95)") or 0),
        "error_rate": round((metrics.get("http_req_failed") or {}).get("rate") or 0, 4),
        "dropped": int(dropped),
    }


def _metrics(api_url: str) -> dict:
    """Relève les métriques courantes de k6, ou un dict vide si l'API ne répond pas."""
    try:
        response = requests.get(f"{api_url}/v1/metrics", timeout=3)
        response.raise_for_status()
        return {item.get("id"): (item.get("attributes") or {}).get("sample") or {}
                for item in (response.json().get("data") or [])}
    except (requests.RequestException, ValueError, AttributeError) as exc:
        logger.debug("[load] Métriques k6 indisponibles : %s", exc)
        return {}


def _request_stop(api_url: str) -> bool:
    """Demande à k6 de s'arrêter proprement, pour qu'il écrive quand même son résumé.

    Un `terminate()` sauterait `handleSummary` - et sous Windows il n'existe pas de
    signal d'interruption transmissible à un sous-processus.
    """
    try:
        response = requests.patch(
            f"{api_url}/v1/status",
            json={"data": {"type": "status", "id": "default",
                           "attributes": {"stopped": True}}},
            timeout=5,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("[load] Arrêt propre de k6 impossible : %s", exc)
        return False


def _is_running(api_url: str) -> bool | None:
    """k6 tire-t-il encore ? ``None`` quand l'API ne répond pas (on ne conclut rien).

    Le processus survit à la fin du test tant qu'un navigateur est connecté au
    dashboard : seul ce statut distingue « ça tourne » de « ça attend ».
    """
    try:
        response = requests.get(f"{api_url}/v1/status", timeout=3)
        response.raise_for_status()
        return bool(response.json()["data"]["attributes"]["running"])
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.debug("[load] Statut k6 indisponible : %s", exc)
        return None


def _wait_for_file(path: Path, seconds: float) -> bool:
    """Laisse k6 finir d'écrire son résumé après une demande d'arrêt."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.5)
    return False


def _wait_for_export(path: Path, seconds: float) -> bool:
    """Attend que le rapport HTML du dashboard soit complet, sans dépasser le délai.

    L'existence du fichier ne suffit pas : k6 l'ouvre avant de le remplir. On attend
    donc deux relevés de taille identiques et non nulle.
    """
    deadline = time.monotonic() + seconds
    previous = -1
    while time.monotonic() < deadline:
        size = _size(path)
        if size and size == previous:
            return True
        previous = size
        time.sleep(0.5)
    return _size(path) > 0


def _size(path: Path) -> int:
    """Taille du fichier, ou 0 s'il est absent ou illisible."""
    try:
        return path.stat().st_size
    except OSError:
        return 0

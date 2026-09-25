"""Plomberie commune aux moteurs de charge (Locust, k6).

Les deux runners diffèrent par la façon de produire la charge et de suivre le run.
Ils partagent tout le reste : publication vers l'UI, lecture du résultat final,
historique, arrêt du processus.
"""

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil
import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from services.load import baselines, html_report
from services.load.history import save_run
from services.load.profiles import PROFILES

logger = get_logger(__name__)

REPORTS_DIR = paths.REPORTS / "load"

# Un seul injecteur à la fois sur la machine : deux moteurs simultanés se disputeraient
# le CPU et fausseraient les deux mesures.
_ACTIVE: dict[str, Any] = {"proc": None}


def is_local(base_url: str) -> bool:
    """La cible tourne-t-elle sur la machine de l'injecteur (CPU partagé) ?"""
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def link_speed_mbps(base_url: str) -> int | None:
    """Vitesse négociée du lien qui porte le trafic vers la cible, en Mb/s.

    Répond à « le réseau a-t-il bridé le test avant le serveur ? ». Un lien
    retombé à 100 Mb/s sature vers 12 Mo/s et produit tous les symptômes d'un
    serveur à bout de souffle, qu'aucun outil de charge ne sait distinguer.

    Returns:
        La vitesse du lien, ou None si l'interface est indéterminable (cible
        locale, pilote qui ne la publie pas, interface virtuelle).
    """
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        # `connect` sur un socket UDP n'émet rien : il ne fait que résoudre la route.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((host, port))
            local_ip = probe.getsockname()[0]
        for name, addresses in psutil.net_if_addrs().items():
            if not any(a.family == socket.AF_INET and a.address == local_ip for a in addresses):
                continue
            stats = psutil.net_if_stats().get(name)
            return stats.speed if stats and stats.speed > 0 else None
    except (OSError, ValueError):
        return None
    return None


def describe_injector(result: dict[str, Any], target: dict[str, Any],
                      params: dict[str, Any]) -> None:
    """Consigne dans le résultat les conditions matérielles du run.

    Deux runs du même scénario peuvent différer d'un facteur cinq selon le nombre
    de processus : sans ces champs, l'écart devient inexplicable dès qu'on relit
    les résultats quelques semaines plus tard.
    """
    result["target_is_local"] = is_local(target["base_url"])
    result["injector_cores"] = os.cpu_count()
    processes = params.get("processes")
    # k6 répartit la charge en interne : le nombre de processus n'a de sens que pour Locust.
    result["injector_processes"] = max(1, int(processes)) if processes else None
    speed = link_speed_mbps(target["base_url"])
    result["link_speed_mbps"] = speed
    rate = result.get("data_received_rate")
    if speed and isinstance(rate, (int, float)) and rate > 0:
        result["network_usage_pct"] = round(rate / (speed * 1_000_000 / 8) * 100, 1)


def free_port() -> int:
    """Retourne un port TCP libre, attribué par le système."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("", 0))
        return probe.getsockname()[1]


def post(route: str, payload: dict[str, Any]) -> bool:
    """Envoie une notification interne sans faire échouer le test de charge.

    Args:
        route: Route relative de l'API TestOps.
        payload: Corps JSON à transmettre.

    Returns:
        ``True`` si la réponse HTTP est réussie, sinon ``False``.
    """
    try:
        response = requests.post(f"{API_BASE_URL}{route}", json=payload, timeout=5)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("[load] POST %s échoué : %s", route, exc)
        logger.debug("Détail du POST interne %s", route, exc_info=True)
        return False


def post_result(session_id: str, result: dict[str, Any]) -> None:
    """Publie le résultat final du test de charge dans sa session UI."""
    post("/load-result", {"session_id": session_id, "result": result})


def compare_to_baseline(result: dict[str, Any], target_id: str, test_type: str,
                        params: dict[str, Any]) -> None:
    """Confronte le résultat à la référence de son couple cible/type, s'il en existe une.

    Posé avant l'analyse pour qu'une règle puisse en tirer un verdict de régression.
    """
    if not result or result.get("error"):
        return
    reference = baselines.get(target_id, test_type)
    if reference:
        result["baseline"] = baselines.compare(result, params, reference)


def write_report(session_id: str, target_id: str, target: dict[str, Any], test_type: str,
                 params: dict[str, Any], result: dict[str, Any]) -> None:
    """Écrit le rapport partageable et pose son lien dans le résultat.

    Un rapport qui ne part pas ne sert à personne : l'échec d'écriture est journalisé,
    jamais propagé, pour ne pas faire tomber un run qui s'est bien déroulé.
    """
    if not result or result.get("error"):
        return
    try:
        label = PROFILES.get(test_type, {}).get("label", test_type)
        run = html_report.build_run(target_id, target, test_type, params, result, label)
        destination = REPORTS_DIR / f"rapport_{session_id}.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html_report.render(run), encoding="utf-8")
        result["summary_report_url"] = f"/load-report/{destination.name}"
    except OSError as exc:
        logger.warning("[load] Rapport partageable non écrit : %s", exc)
        logger.debug("Détail de l'écriture du rapport", exc_info=True)


def emit_log(session_id: str, message: str) -> None:
    """Publie un message métier dans le journal de la session UI."""
    post("/log", {"session_id": session_id, "message": message})


def emit_metrics(session_id: str, metrics: dict[str, Any]) -> None:
    """Publie un relevé temps réel dans le bandeau de la session UI."""
    post("/load-metrics", {"session_id": session_id, "metrics": metrics})


def notify_complete(session_id: str) -> None:
    """Notifie l'API que le test de charge a terminé sa finalisation."""
    post("/execution-complete", {"session_id": session_id})


def fail(session_id: str, message: str) -> None:
    """Termine proprement un run qui n'a pas pu démarrer."""
    post_result(session_id, {"error": message})
    notify_complete(session_id)


def read_result(result_path: Path, exit_code: int | None) -> dict[str, Any]:
    """Lit et valide le résultat final écrit par le moteur de charge.

    Args:
        result_path: Chemin du fichier JSON produit par le scénario.
        exit_code: Code du processus, éventuellement absent s'il tourne encore.

    Returns:
        Le résultat enrichi du code de sortie, ou un objet contenant une erreur
        explicite lorsque le fichier est absent, illisible ou mal structuré.
    """
    if not result_path.exists():
        return {"error": "Aucun resultat (fichier manquant). Le test a-t-il demarre ?",
                "exit_code": exit_code}
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"error": f"Résultat illisible : {exc}", "exit_code": exit_code}

    if not isinstance(data, dict):
        return {
            "error": "Résultat invalide : la racine JSON doit être un objet.",
            "exit_code": exit_code,
        }

    data["exit_code"] = exit_code
    return data


def clean(*paths: Path) -> None:
    """Supprime les fichiers d'un run précédent sans bloquer le démarrage."""
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.debug("[load] Nettoyage impossible pour %s : %s", path, exc)


def terminate(proc) -> None:
    """Arrête un processus d'injection avec terminate, puis kill après le timeout."""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError as exc:
        logger.debug("[load] Arrêt du processus d'injection impossible : %s", exc)


def kill_previous() -> None:
    """Arrête l'injecteur du run précédent et libère sa référence globale."""
    prev = _ACTIVE.get("proc")
    if prev is not None and prev.poll() is None:
        terminate(prev)
    _ACTIVE["proc"] = None


def remember(proc) -> None:
    """Retient le processus courant pour pouvoir le couper au run suivant."""
    _ACTIVE["proc"] = proc


def verdict_log(result: dict[str, Any]) -> str:
    """Construit le message UI final depuis le point de rupture et le verdict."""
    if result.get("error"):
        return f"❌ {result['error']}"
    breach = result.get("breach")
    if breach and breach.get("cause") == "dropped":
        return (f"🔴 Décrochage à {breach['t']:.0f} s - le système absorbait "
                f"~{breach['rps']:.0f} req/s avant d'accumuler du retard.")
    if breach and breach.get("cause") == "cpu":
        return (f"🎚️ Injecteur saturé à {breach.get('cpu', 0):.0f} % de CPU à "
                f"{breach['t']:.0f} s - capacité ~{breach['rps']:.0f} req/s "
                f"avec {breach['users']} utilisateurs.")
    if breach:
        seuil = int(result.get("seuil_p95_ms", 0))
        return (f"🔴 Rupture a ~{breach['users']} users actifs - "
                f"p95 {breach['p95_ms']} ms (> {seuil} ms) a {breach['t']:.0f} s.")
    if result.get("stopped"):
        return "🛑 Test arrete manuellement."
    status = result.get("status") or ("ok" if result.get("thresholds_ok") else "fail")
    if status == "ok":
        return "✅ Termine - charge tenue sous le seuil, aucune rupture."
    if status == "warn":
        return "⚠️ Termine - a surveiller (erreurs)."
    return "❌ Termine - seuil non tenu."


def save_history(
    target_id: str,
    target: dict[str, Any],
    test_type: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Historise un run valide sans laisser l'historique bloquer sa finalisation."""
    if not result or result.get("error"):
        return
    try:
        save_run({
            "target": target_id,
            "target_label": target.get("label", target_id),
            "test_type": test_type,
            "params": params,
            "result": result,
        })
    except Exception as exc:  # noqa: BLE001 - l'historique ne doit jamais casser le run
        logger.warning("[load] Historique non enregistré : %s", exc)
        logger.debug("Détail de l'enregistrement de l'historique", exc_info=True)

"""Référence de comparaison d'un test de charge, pour détecter une régression.

Un run devient la référence d'un couple (cible, type de test) ; les runs suivants
s'y comparent automatiquement. Les chiffres sont **recopiés** ici plutôt que relus
dans l'historique : celui-ci est borné aux derniers runs, une référence posée il y a
six mois y aurait depuis longtemps disparu.
"""

from __future__ import annotations

import json
import time
from typing import Any

from core.logging_config import get_logger
from core.paths import paths

BASELINES_FILE = paths.OUTPUT_ROOT / "load_baselines.json"

# Ces paramètres JUGENT le résultat sans changer la charge appliquée. Les inclure
# dans la comparaison interdirait de comparer deux runs identiques au prétexte
# qu'on a resserré un seuil entre-temps.
_SEUILS = {"p95_ms", "p99_ms", "error_pct"}

# Ce qu'on retient d'un run : de quoi comparer sans dépendre de l'historique.
_METRIQUES = ("p50_ms", "p95_ms", "p99_ms", "min_ms", "reqs_per_sec",
              "error_rate", "checks_rate", "injector_capacity_rps")

logger = get_logger(__name__)


def _metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Chiffres retenus pour la comparaison, point de rupture aplati compris.

    Deux tests de capacité aux mêmes réglages ne s'arrêtent pas au même palier :
    leurs percentiles n'agrègent donc pas la même population de requêtes, et un p95
    en hausse peut cacher une capacité en hausse. C'est le point de rupture qui se
    compare.
    """
    valeurs = {m: result[m] for m in _METRIQUES if result.get(m) is not None}
    breach = result.get("breach") or {}
    if breach.get("users") is not None:
        valeurs["breach_users"] = breach["users"]
    if breach.get("rps") is not None:
        valeurs["breach_rps"] = breach["rps"]
    return valeurs


def key(target_id: str, test_type: str) -> str:
    """Une référence n'a de sens qu'à cible et type de test constants."""
    return f"{target_id}|{test_type}"


def load_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Les paramètres qui déterminent la charge, sans ceux qui la jugent."""
    return {k: v for k, v in (params or {}).items() if k not in _SEUILS}


def _read() -> dict[str, Any]:
    try:
        return json.loads(BASELINES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get(target_id: str, test_type: str) -> dict[str, Any] | None:
    """Référence enregistrée pour ce couple, ou None."""
    return _read().get(key(target_id, test_type))


def list_all() -> dict[str, Any]:
    """Toutes les références, indexées par couple cible/type."""
    return _read()


def set_baseline(run: dict[str, Any]) -> dict[str, Any] | None:
    """Fait de ce run la référence de sa cible et de son type de test.

    Args:
        run: Une entrée d'historique (``target``, ``test_type``, ``params``, ``result``).

    Returns:
        La référence enregistrée, ou None si le run est inexploitable.
    """
    result = run.get("result") or {}
    target_id, test_type = run.get("target"), run.get("test_type")
    if not target_id or not test_type or result.get("error"):
        return None
    reference = {
        "run_id": run.get("id"),
        "ts": run.get("ts") or time.time(),
        "label": run.get("target_label") or target_id,
        "params": load_params(run.get("params")),
        "metrics": _metrics(result),
    }
    data = _read()
    data[key(target_id, test_type)] = reference
    try:
        BASELINES_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    except OSError as exc:
        logger.warning("[load] Référence non enregistrée : %s", exc)
        return None
    return reference


def clear(target_id: str, test_type: str) -> bool:
    """Retire la référence de ce couple. True si quelque chose a été retiré."""
    data = _read()
    if data.pop(key(target_id, test_type), None) is None:
        return False
    try:
        BASELINES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    except OSError as exc:
        logger.warning("[load] Référence non effacée : %s", exc)
        return False
    return True


def compare(result: dict[str, Any], params: dict[str, Any],
            reference: dict[str, Any]) -> dict[str, Any]:
    """Écarts entre ce run et sa référence.

    Returns:
        Un dict portant ``comparable`` (les charges sont-elles identiques ?),
        ``deltas`` en pourcentage par métrique, et le rappel de la référence.
        Quand les charges diffèrent, les écarts sont calculés quand même mais
        ``comparable`` vaut False : c'est à la lecture d'en tenir compte.
    """
    attendus = reference.get("metrics") or {}
    courantes = _metrics(result)
    deltas = {}
    for nom, avant in attendus.items():
        apres = courantes.get(nom)
        if not isinstance(apres, (int, float)) or not isinstance(avant, (int, float)):
            continue
        if avant == 0:
            deltas[nom] = {"avant": avant, "apres": apres, "pct": None}
            continue
        deltas[nom] = {"avant": avant, "apres": apres,
                       "pct": round((apres - avant) / abs(avant) * 100, 1)}
    return {
        "comparable": load_params(params) == (reference.get("params") or {}),
        "ts": reference.get("ts"),
        "run_id": reference.get("run_id"),
        "deltas": deltas,
    }

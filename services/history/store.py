"""Persistance de la mémoire des exécutions : une ligne JSON par couple (run, test).

Fichier append-only dans `paths.OUTPUT_ROOT`, hors du dépôt : il survit aux
nettoyages de `temp/` et n'encombre aucun commit.

**Ce module est la seule porte vers le fichier.** Ni les routes, ni le frontend, ni
l'analyse de stabilité ne le lisent directement : ils passent par `append`,
`read_entries` et `stored_run_ids`. Le jour où le volume imposera une vraie base
(plusieurs centaines de milliers de lignes, ou des filtres croisés
environnement × navigateur), ce fichier est le seul à réécrire.
"""

import json
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from core.paths import paths

logger = get_logger(__name__)

HISTORY_FILE: Path = paths.OUTPUT_ROOT / "test_history.jsonl"

# Jusqu'où le dossier de rapports a déjà été balayé. Tenu à part des entrées : un run
# écarté (résultat abimé, run d'un autre dépôt) ne laisse aucune entrée derrière lui, et
# serait donc re-analysé à chaque lecture - relire un gros XML pour rien.
STATE_FILE: Path = paths.OUTPUT_ROOT / "test_history_state.json"

# Version du format d'une ligne. Portée par chaque enregistrement pour qu'un
# historique ancien se reconnaisse au lieu de se lire de travers.
SCHEMA = 1

# Ce qu'on GARDE, à ne pas confondre avec la fenêtre d'ANALYSE (30 runs) : garder
# plus large laisse la possibilité d'élargir l'analyse plus tard sans avoir jeté
# les données entre-temps.
MAX_RUNS_KEPT = 200


def append(entries: list[dict[str, Any]]) -> None:
    """Ajoute les résultats d'un run sans jamais pouvoir casser son appelant.

    Args:
        entries: Une entrée par test joué, telles que produites par l'ingestion.
    """
    if not entries:
        return
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as history_file:
            for entry in entries:
                history_file.write(
                    json.dumps({**entry, "schema": SCHEMA}, ensure_ascii=False) + "\n"
                )
        _trim()
    except (OSError, TypeError) as exc:
        logger.warning("[history] Historique non écrit : %s", exc)
        logger.debug("Détail de l'écriture de l'historique", exc_info=True)


def read_entries(runs: int) -> list[dict[str, Any]]:
    """Retourne les entrées des ``runs`` derniers runs, du plus ancien au plus récent.

    L'ordre chronologique est celui dont l'analyse a besoin : détecter qu'un test a
    alterné vert et rouge suppose de lire ses résultats dans l'ordre où ils sont
    tombés.

    Args:
        runs: Nombre de runs à retenir. Une valeur nulle ou négative rend une liste vide.
    """
    if runs <= 0:
        return []
    records = list(_iter_records())
    kept = set(_distinct_run_ids(records)[-runs:])
    return [record for record in records if record.get("run_id") in kept]


def stored_run_ids() -> list[str]:
    """Retourne les identifiants des runs déjà enregistrés, dans l'ordre d'ingestion."""
    return _distinct_run_ids(list(_iter_records()))


def clear() -> None:
    """Supprime tout l'historique sans interrompre l'appelant en cas d'échec."""
    try:
        HISTORY_FILE.unlink(missing_ok=True)
        STATE_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("[history] Historique non effacé : %s", exc)
        logger.debug("Détail de la suppression de l'historique", exc_info=True)


def scan_watermark() -> float:
    """Retourne la date du résultat le plus récent déjà balayé, ou 0 au premier passage."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return float(state["scanned_until"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0.0


def set_scan_watermark(timestamp: float) -> None:
    """Retient jusqu'où le balayage est allé, sans jamais casser l'appelant."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({"scanned_until": timestamp}), encoding="utf-8"
        )
    except (OSError, TypeError) as exc:
        logger.warning("[history] Repère de balayage non écrit : %s", exc)
        logger.debug("Détail de l'écriture du repère de balayage", exc_info=True)


def _iter_records():
    """Parcourt les enregistrements valides du fichier, en ignorant les lignes abîmées."""
    if not HISTORY_FILE.exists():
        return
    try:
        content = HISTORY_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        logger.warning("[history] Historique illisible : %s", exc)
        logger.debug("Détail de la lecture de l'historique", exc_info=True)
        return
    for line_number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("[history] Ligne JSONL invalide ignorée : %s", line_number)
            continue
        if isinstance(record, dict):
            yield record
        else:
            logger.debug("[history] Ligne JSONL non objet ignorée : %s", line_number)


def _distinct_run_ids(records: list[dict[str, Any]]) -> list[str]:
    """Retourne les identifiants de run rencontrés, sans doublon, dans l'ordre du fichier."""
    seen: dict[str, None] = {}
    for record in records:
        run_id = record.get("run_id")
        if isinstance(run_id, str):
            seen.setdefault(run_id, None)
    return list(seen)


def _trim() -> None:
    """Ne conserve que les ``MAX_RUNS_KEPT`` derniers runs, entrées comprises."""
    try:
        records = list(_iter_records())
        run_ids = _distinct_run_ids(records)
        if len(run_ids) <= MAX_RUNS_KEPT:
            return
        kept = set(run_ids[-MAX_RUNS_KEPT:])
        lines = [
            json.dumps(record, ensure_ascii=False)
            for record in records
            if record.get("run_id") in kept
        ]
        HISTORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, TypeError) as exc:
        logger.warning("[history] Limitation de l'historique impossible : %s", exc)
        logger.debug("Détail de la limitation de l'historique", exc_info=True)

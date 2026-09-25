"""
Historique des runs de charge (persiste dans un fichier JSONL).

Un run = une ligne JSON. Stockage dans `paths.OUTPUT_ROOT` (hors du repo, survit
aux nettoyages de `temp/`). Volontairement simple : pas de base de donnees, juste
un fichier append-only borne aux N derniers runs.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from core.paths import paths

HISTORY_FILE: Path = paths.OUTPUT_ROOT / "load_history.jsonl"
_MAX_RUNS = 200
logger = get_logger(__name__)


def save_run(entry: dict[str, Any]) -> dict[str, Any]:
    """Ajoute un run à l'historique sans pouvoir casser son exécution.

    Les champs système ``id`` et ``ts`` sont toujours générés par le service et
    remplacent d'éventuelles valeurs fournies par l'appelant.

    Args:
        entry: Données à conserver pour le run de charge.

    Returns:
        Une copie enrichie d'un identifiant et d'un horodatage, même si
        l'écriture best-effort échoue.
    """
    record = {**entry, "id": uuid.uuid4().hex[:12], "ts": time.time()}
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        _trim()
    except (OSError, TypeError) as exc:
        logger.warning("[load] Historique non écrit : %s", exc)
        logger.debug("Détail de l'écriture de l'historique", exc_info=True)
    return record


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Retourne les runs du plus récent au plus ancien.

    Args:
        limit: Nombre maximal de runs à retourner. Une valeur nulle ou négative
            produit une liste vide.

    Returns:
        Les enregistrements JSON valides, dans l'ordre antéchronologique.
    """
    if limit <= 0 or not HISTORY_FILE.exists():
        return []

    runs: list[dict[str, Any]] = []
    try:
        with HISTORY_FILE.open(encoding="utf-8") as history_file:
            for line_number, line in enumerate(history_file, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(
                        "[load] Ligne JSONL invalide ignorée dans l'historique : %s",
                        line_number,
                    )
                    continue
                if isinstance(record, dict):
                    runs.append(record)
                else:
                    logger.debug(
                        "[load] Ligne JSONL non objet ignorée dans l'historique : %s",
                        line_number,
                    )
    except (OSError, UnicodeError) as exc:
        logger.warning("[load] Historique illisible : %s", exc)
        logger.debug("Détail de la lecture de l'historique", exc_info=True)
        return []

    runs.reverse()
    return runs[:limit]


def clear_history() -> None:
    """Supprime tout l'historique sans interrompre l'appelant en cas d'échec."""
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
    except OSError as exc:
        logger.warning("[load] Historique non effacé : %s", exc)
        logger.debug("Détail de la suppression de l'historique", exc_info=True)


def _trim() -> None:
    """Conserve uniquement les ``_MAX_RUNS`` dernières lignes non vides."""
    try:
        lines = [
            line
            for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(lines) > _MAX_RUNS:
            HISTORY_FILE.write_text("\n".join(lines[-_MAX_RUNS:]) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        logger.warning("[load] Limitation de l'historique impossible : %s", exc)
        logger.debug("Détail de la limitation de l'historique", exc_info=True)

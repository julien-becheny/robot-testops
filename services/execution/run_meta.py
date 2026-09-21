"""Carte d'identité d'un run, déposée dans son dossier de rapport au lancement.

Un dossier de rapport ne dit pas sur quel commit ni dans quel contexte le run a
tourné. Sans cette trace, l'analyse de stabilité ne pourrait pas distinguer un test
fragile - vert puis rouge sur le **même** commit - d'une vraie régression du produit.

Le nom du dossier porte bien navigateur et appareil, mais l'en déduire supposerait de
le découper : un analyseur de nom de fichier casse au premier libellé contenant un
souligné. On écrit donc l'information plutôt que de la deviner.
"""

import json
import subprocess
from pathlib import Path

from core import environments
from core.logging_config import get_logger
from core.paths import paths

logger = get_logger(__name__)

META_FILE = "run_meta.json"
GIT_TIMEOUT_SECONDS = 5


def write(dt_stamp: str, **fields) -> None:
    """Dépose le contexte du run, sans jamais pouvoir empêcher son lancement.

    Args:
        dt_stamp: Horodatage du run, qui nomme son dossier de rapport.
        **fields: Contexte connu de l'appelant seul (navigateur, appareil, moteur...).
    """
    try:
        run_dir = paths.get_report_folder(dt_stamp)
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "commit": current_commit(),
            "environment": environments.active_environment(),
            **fields,
        }
        (run_dir / META_FILE).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, TypeError) as exc:
        logger.warning("Contexte du run non écrit (%s) : %s", dt_stamp, exc)
        logger.debug("Détail de l'écriture du contexte de run", exc_info=True)


def read(run_dir: Path) -> dict:
    """Retourne le contexte d'un run, ou un dictionnaire vide s'il est absent ou illisible.

    Les runs antérieurs à cette trace n'en ont pas : leur absence est un cas normal,
    pas une erreur.
    """
    try:
        payload = json.loads((run_dir / META_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def current_commit() -> str | None:
    """Retourne le commit courant en forme courte, ou None hors dépôt Git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(paths.PROJECT_ROOT),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None

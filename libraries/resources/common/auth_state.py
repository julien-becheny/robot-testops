"""État d'authentification : sortir le fichier de session du dossier de rapport.

`Save Storage State` (Browser 20.0.0) n'accepte aucun chemin : il écrit dans
``${OUTPUTDIR}/browser/state/<uuid>.json``, donc DANS le rapport du run - que la CI
archive et que l'API sert telle quelle par ``/logs/<session_id>/standard/<chemin>``.
Or ce fichier porte le cookie de session, qui vaut le mot de passe. On le déplace
donc aussitôt vers un dossier privé au processus, hors de l'arborescence des
rapports, supprimé en fin de suite.

Le dossier vient de ``mkdtemp`` : un run en matrice lance N processus Robot
simultanés, et l'unicité par construction suffit à les empêcher de se marcher
dessus - sans faire transiter le `session_id` jusqu'aux tests, ni écrire quoi que
ce soit sous ``paths.REPORTS``.

Importé côté Robot via ::

    Library  ${CURDIR}/auth_state.py
"""

import shutil
import tempfile
import time
from pathlib import Path

_PREFIX = "rf_auth_"
_STATE_NAME = "storage_state.json"
# Le bouton « Arrêter » de TestOps peut tuer le processus avant son teardown : le
# dossier survivrait alors à son run, avec une session vivante dedans. Au-delà d'une
# journée, aucun run en cours ne peut plus revendiquer celui d'un autre.
_STALE_AFTER_S = 24 * 3600

_private_dir: Path | None = None


def _purge_stale() -> None:
    """Efface les dossiers laissés par des runs tués avant leur teardown."""
    cutoff = time.time() - _STALE_AFTER_S
    for leftover in Path(tempfile.gettempdir()).glob(f"{_PREFIX}*"):
        try:
            if leftover.is_dir() and leftover.stat().st_mtime < cutoff:
                shutil.rmtree(leftover, ignore_errors=True)
        except OSError:
            continue


def stash_auth_state(saved_file: str) -> str:
    """Déplace le fichier d'état hors du rapport et retourne son nouveau chemin.

    Prend le chemin que `Save Storage State` vient de retourner. Le déplacement est
    immédiat : entre l'écriture et lui, le secret est dans le rapport.
    """
    global _private_dir
    if _private_dir is None:
        _purge_stale()
        _private_dir = Path(tempfile.mkdtemp(prefix=_PREFIX))
    target = _private_dir / _STATE_NAME
    shutil.move(saved_file, target)
    return str(target)


def discard_auth_state() -> None:
    """Supprime le dossier privé du processus. Sans état enregistré, ne fait rien."""
    global _private_dir
    if _private_dir is None:
        return
    shutil.rmtree(_private_dir, ignore_errors=True)
    _private_dir = None

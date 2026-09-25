"""Purge des dossiers de rapport devenus inutiles.

Le dossier de rapports n'appartient pas à ce dépôt : il vit sous `~/rf_output`, donc
**partagé** avec les autres projets de la machine - chacun y dépose ses runs. Purger par
simple ancienneté effacerait les rapports du voisin. On ne supprime donc que ce que ce
TestOps a lui-même produit, reconnaissable à la carte d'identité qu'il dépose au
lancement (`run_meta.json`). Ce marqueur sert deux fois : il dit à qui appartient le
dossier, et sa date dit quand le run a commencé.

Ce choix écarte volontairement les runs non tracés (ligne de commande, dépôt voisin,
rapports de charge) : ne rien supprimer coûte de l'espace disque, supprimer à tort coûte
le travail de quelqu'un d'autre.

La purge suit l'ingestion et jamais l'inverse : un dossier supprimé avant d'être lu
serait un trou définitif dans l'historique.
"""

import shutil
import time
from pathlib import Path

from core.logging_config import get_logger
from core.paths import paths
from services.execution.run_meta import META_FILE

logger = get_logger(__name__)

# Au-delà, un rapport n'est plus ouvert : l'historique garde le verdict de chaque test et
# le dashboard ses statistiques. Très large devant la fenêtre d'analyse (30 runs).
MAX_AGE_DAYS = 60

SECONDS_PER_DAY = 86400


def expired_runs(max_age_days: int = MAX_AGE_DAYS) -> list[Path]:
    """Retourne les dossiers de run purgeables, du plus ancien au plus récent.

    Sans effet de bord : sert aussi bien à purger qu'à montrer ce qui serait supprimé.

    Args:
        max_age_days: Âge à partir duquel un run est considéré comme périmé.
    """
    if not paths.REPORTS.is_dir():
        return []

    root = paths.REPORTS.resolve()
    deadline = time.time() - max_age_days * SECONDS_PER_DAY
    expired = []
    for entry in paths.REPORTS.iterdir():
        started_at = _owned_run_start(entry, root)
        if started_at is not None and started_at < deadline:
            expired.append((started_at, entry))
    return [entry for _, entry in sorted(expired)]


def purge_old_runs(max_age_days: int = MAX_AGE_DAYS) -> int:
    """Supprime les rapports périmés et retourne combien ont été effacés.

    Ne peut jamais interrompre son appelant : un dossier verrouillé par l'explorateur de
    fichiers ou un antivirus est sauté, et retenté au prochain passage.
    """
    purged = 0
    for run_dir in expired_runs(max_age_days):
        try:
            shutil.rmtree(run_dir)
        except OSError as exc:
            logger.warning("[retention] Rapport non supprimé (%s) : %s", run_dir.name, exc)
            continue
        purged += 1

    if purged:
        logger.info("[retention] %d rapport(s) de plus de %d jours supprimé(s)",
                    purged, max_age_days)
    return purged


def _owned_run_start(entry: Path, root: Path) -> float | None:
    """Retourne la date de début d'un run produit par ce TestOps, sinon None.

    Un lien symbolique est écarté d'office : `rmtree` le suivrait et sortirait de la
    racine des rapports, pour effacer une cible qu'on n'a jamais choisie.
    """
    if entry.is_symlink() or not entry.is_dir():
        return None
    if entry.resolve().parent != root:
        return None
    marker = entry / META_FILE
    try:
        return marker.stat().st_mtime
    except OSError:
        return None

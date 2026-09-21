"""Dernier run joué : de quoi répondre « est-ce que ça passe ? » sans ouvrir un rapport.

La source de vérité est le dossier de rapports, pas le registre de sessions : celui-ci
vit en mémoire et disparaît au redémarrage du backend, alors que la question posée à
l'ouverture de TestOps porte justement sur ce qui s'est passé avant.
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from core.logging_config import get_logger
from core.paths import paths

logger = get_logger(__name__)

OUTPUT_FILE = "output.xml"
REPORT_FILE = "report.html"
LOG_FILE = "log.html"

# Où un run dépose son résultat, du plus complet au plus brut. Un run ordinaire écrit
# à la racine ; avec « rejouer les échecs », le premier passage va dans Output_original/
# et la fusion dans Output_merge/ - la racine, elle, reste vide.
RESULT_LAYOUTS = (
    ("Output_merge/output_merge.xml", "Output_merge/log_merge.html"),
    (OUTPUT_FILE, LOG_FILE),
    ("Output_original/output_original.xml", "Output_original/log_original.html"),
)


def _result_of(run_dir: Path) -> tuple[Path, str] | None:
    """Retourne (résultat, log relatif) d'un dossier de run, ou None s'il n'a rien produit."""
    for output_name, log_name in RESULT_LAYOUTS:
        output = run_dir / output_name
        if output.is_file():
            return output, log_name
    return None


def _latest_run() -> tuple[Path, Path, str] | None:
    """Retourne (dossier du run, résultat, log relatif) du run le plus récent."""
    if not paths.REPORTS.is_dir():
        return None

    runs = []
    for run_dir in paths.REPORTS.iterdir():
        if not run_dir.is_dir():
            continue
        found = _result_of(run_dir)
        if found:
            runs.append((run_dir, *found))

    if not runs:
        return None
    return max(runs, key=lambda item: item[1].stat().st_mtime)


def _counts(root: ET.Element) -> tuple[int, int, int]:
    """Extrait (passés, échoués, ignorés) des statistiques globales du run."""
    stat = root.find(".//statistics/total/stat")
    if stat is None:
        return 0, 0, 0
    try:
        return (int(stat.get("pass", 0)), int(stat.get("fail", 0)), int(stat.get("skip", 0)))
    except ValueError:
        logger.warning("Statistiques du dernier run illisibles")
        return 0, 0, 0


def last_run() -> dict | None:
    """Résume le dernier run, ou None si aucun résultat exploitable n'existe."""
    latest = _latest_run()
    if latest is None:
        return None
    run_dir, output, log_name = latest

    try:
        root = ET.parse(output).getroot()
    except (ET.ParseError, OSError) as exc:
        logger.warning("Dernier résultat inexploitable (%s) : %s", output, exc)
        return None

    passed, failed, skipped = _counts(root)
    suite = root.find("suite")
    return {
        "name": (suite.get("name") if suite is not None else None) or run_dir.name,
        "folder": run_dir.name,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": passed + failed + skipped,
        "status": "failed" if failed else "passed",
        "finished_at": datetime.fromtimestamp(output.stat().st_mtime).isoformat(
            timespec="seconds"
        ),
        # Chemin relatif au dossier du run : le log d'un rejeu vit dans un sous-dossier.
        "log": log_name if (run_dir / log_name).is_file() else None,
    }


def last_run_dir() -> Path | None:
    """Retourne le dossier du dernier run, ou None s'il n'y en a aucun."""
    latest = _latest_run()
    return latest[0] if latest else None

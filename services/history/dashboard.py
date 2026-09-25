"""Dashboard de tendances : les runs historisés vus sous forme de courbes.

L'historique JSONL répond « ce test est-il fiable ? ». Il ne répond pas « la suite
ralentit-elle depuis trois semaines ? », ni « quel mot-clé coûte le plus cher ? ».
C'est ce que produit `robotdashboard` (MarketSquare) : il relit les `output.xml`, les
empile dans un SQLite à lui et en sort un HTML **autonome** - donc joignable à un
livrable de recette, contrairement à une page servie par le backend.

Les deux mémoires cohabitent volontairement : le JSONL porte le verdict actionnable
affiché dans l'interface, la base du dashboard porte l'exploration visuelle. Elles
partagent leur source (`output.xml`), pas leur usage - remplacer l'une par l'autre
ferait perdre soit les courbes, soit la notion de régression à périmètre égal.

Seuls les runs déjà retenus par l'ingestion entrent ici : c'est elle qui sait écarter
les runs d'un dépôt voisin, et le dossier de rapports est partagé.
"""

import json
import subprocess
import sys
from pathlib import Path

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from services.history import store
from services.history.ingest import output_of
from services.history.retention import MAX_AGE_DAYS

logger = get_logger(__name__)

DB_FILE: Path = paths.OUTPUT_ROOT / "robot_results.db"
DASHBOARD_FILE: Path = paths.OUTPUT_ROOT / "robot_dashboard.html"

# Quels runs ont déjà été versés à la base du dashboard. Sans cette trace il faudrait
# relancer l'outil une fois par run connu à chaque consultation : il saute bien les
# résultats déjà en base, mais après avoir payé le démarrage d'un processus.
STATE_FILE: Path = paths.OUTPUT_ROOT / "robot_dashboard_state.json"

# Le paquet n'expose pas de `__main__` : `robotframework_dashboard.main` est son point
# d'entrée réel. Passer par `sys.executable` et non par le nom du script (règle PY_EXE).
MODULE = "robotframework_dashboard.main"

# Lire un gros output.xml prend quelques secondes ; au-delà, quelque chose est bloqué.
TIMEOUT_SECONDS = 180

# Nombre de runs affichés au premier chargement. Au-delà, c'est Chart.js qui peine :
# à 100 runs le rendu initial approche les dix secondes. Le filtre reste réglable.
DISPLAYED_RUNS = 20


def refresh() -> Path | None:
    """Met le dashboard à jour et retourne son fichier, ou None s'il n'a pu être produit.

    Les runs nouveaux sont versés un par un : leur lien vers le log est propre à chacun,
    et un résultat abîmé ne doit pas emporter les autres.
    """
    pushed = _pushed_runs()
    for run_id in store.stored_run_ids():
        if run_id not in pushed and _add_run(run_id):
            pushed.add(run_id)
    _save_pushed(pushed)

    _run(_purge_args(), "purge de la base")
    if not _run(_generate_args(), "génération du dashboard"):
        return None
    return DASHBOARD_FILE if DASHBOARD_FILE.is_file() else None


def _purge_args() -> list[str]:
    """Arguments de la purge de la base.

    `-g false` n'est pas décoratif : la génération est active par défaut, et sans nom de
    fichier l'outil dépose un dashboard horodaté dans le dossier courant - soit la racine
    du dépôt, où tourne le backend.
    """
    return ["-r", f"age={MAX_AGE_DAYS}d", "-g", "false", "-l", "false"]


def _generate_args() -> list[str]:
    """Arguments de la génération du HTML."""
    return [
        "-g", "true",
        "-n", str(DASHBOARD_FILE),
        "-t", "TestOps - tendances",
        "-q", str(DISPLAYED_RUNS),
        # Sans cela le HTML va chercher Chart.js sur un CDN : illisible hors ligne, et
        # bloqué sur un poste d'entreprise. Un rapport à joindre doit se suffire.
        "--offlinedependencies",
        # Rend les points des graphes cliquables vers le log du run.
        "-u", "true",
    ]


def _add_run(run_id: str) -> bool:
    """Verse un run dans la base du dashboard. Retourne False s'il n'a rien à verser."""
    output = output_of(paths.REPORTS / run_id)
    if output is None:
        return False
    return _run([
        "-o", str(output),
        # Le dashboard est servi en HTTP : un chemin de fichier local n'y serait pas
        # ouvrable par le navigateur. On stocke donc l'URL qui sert ce log.
        "--logurl", f"{API_BASE_URL}/run-log/{run_id}",
        "-u", "true",
        "-g", "false",
        "-l", "false",
    ], f"ajout du run {run_id}")


def _run(args: list[str], step: str) -> bool:
    """Lance robotdashboard sur la base du projet. Retourne False en cas d'échec."""
    command = [sys.executable, "-m", MODULE, "-d", str(DB_FILE), *args]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("[dashboard] Échec (%s) : %s", step, exc)
        return False

    if completed.returncode != 0:
        logger.warning("[dashboard] Échec (%s) : %s", step, completed.stderr.strip()[:500])
        return False
    return True


def _pushed_runs() -> set[str]:
    """Retourne les runs déjà versés, vide si la trace est absente ou illisible."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(state["pushed"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def _save_pushed(pushed: set[str]) -> None:
    """Retient les runs versés, sans jamais casser l'appelant."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"pushed": sorted(pushed)}), encoding="utf-8")
    except (OSError, TypeError) as exc:
        logger.warning("[dashboard] Trace des runs versés non écrite : %s", exc)

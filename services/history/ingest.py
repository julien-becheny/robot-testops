"""Ingestion des résultats : du dossier de rapports vers la mémoire des exécutions.

La source de vérité est **le dossier de rapports**, pas le registre de sessions - même
parti pris que `services/execution/history.py`. Un run lancé en ligne de commande, par
la CI ou par un collègue est donc historisé exactement comme un run lancé depuis
l'interface : un historique qui ne connaîtrait que les runs passés par le bouton serait
faux dès le premier `robot` en console.

L'ingestion est incrémentale et se déclenche à la lecture : les dossiers déjà vus sont
sautés, un dossier n'est donc analysé qu'une seule fois dans sa vie.
"""

from pathlib import Path

from robot.api import ExecutionResult, ResultVisitor
from robot.errors import DataError

from core.logging_config import get_logger
from core.paths import paths
from services.execution import run_meta
from services.execution.history import RESULT_LAYOUTS, run_dirs
from services.history import store

logger = get_logger(__name__)

# Un message d'échec Robot peut contenir un dump entier ; seul son début identifie la cause.
MESSAGE_MAX = 300


def ingest_new_runs() -> int:
    """Enregistre les runs pas encore vus et retourne combien ont été ajoutés."""
    known = set(store.stored_run_ids())
    watermark = store.scan_watermark()
    scanned_until = watermark

    added = 0
    for run_dir in _run_dirs():
        output = output_of(run_dir)
        if output is None:
            continue
        finished_at = output.stat().st_mtime
        if finished_at <= watermark:
            continue
        scanned_until = max(scanned_until, finished_at)
        if run_dir.name in known:
            continue
        entries = _entries_of_run(run_dir, output, finished_at)
        if not entries:
            continue
        store.append(entries)
        added += 1

    if scanned_until > watermark:
        store.set_scan_watermark(scanned_until)
    return added


def _run_dirs() -> list[Path]:
    """Retourne les dossiers de run, du plus ancien au plus récent.

    Le nom commence par un horodatage de largeur fixe : l'ordre alphabétique est donc
    l'ordre chronologique.
    """
    return sorted(run_dirs(), key=lambda entry: entry.name)


def output_of(run_dir: Path) -> Path | None:
    """Retourne le résultat qui fait foi pour ce run, ou None s'il n'a rien produit.

    L'ordre des dispositions vient de `services/execution/history.py` : la fusion d'un
    rejeu prime sur le premier passage. Retenir les deux compterait un échec que le
    rejeu a rattrapé, et ferait passer pour instable un test qui ne l'est pas.
    """
    for output_name, _log_name in RESULT_LAYOUTS:
        candidate = run_dir / output_name
        if candidate.is_file():
            return candidate
    return None


def _entries_of_run(run_dir: Path, output: Path, finished_at: float) -> list[dict]:
    """Construit une entrée par test joué, ou une liste vide si le run est inexploitable."""
    try:
        result = ExecutionResult(str(output))
    except (DataError, OSError) as exc:
        logger.warning("[history] Résultat inexploitable (%s) : %s", output, exc)
        return []

    collector = _TestCollector()
    result.suite.visit(collector)
    if not any(_relative_source(test) for test in collector.tests):
        logger.debug("[history] Run étranger au dépôt ignoré : %s", run_dir.name)
        return []

    meta = run_meta.read(run_dir)
    context = {
        "commit": meta.get("commit"),
        "environment": meta.get("environment"),
        "browser": meta.get("browser"),
        "device": meta.get("device"),
        # Sert à n'opposer que des runs de même périmètre : un smoke comparé à un run
        # complet annoncerait douze régressions imaginaires.
        "workflow": meta.get("workflow"),
        "run_id": run_dir.name,
        "run_ts": finished_at,
        "rerun": (run_dir / "Output_original").is_dir(),
    }
    return [
        {**context, **_test_entry(test)}
        for test in collector.tests
        if _relative_source(test)
    ]


def _relative_source(test) -> str | None:
    """Retourne le fichier de test relatif au dépôt, ou None s'il lui est extérieur.

    Sert deux fois. Le dossier de rapports est sous `~/rf_output`, donc **partagé** avec
    les autres projets de la machine : sans ce filtre, la santé de la suite mélangerait
    les tests d'un autre produit aux siens. Et c'est ce chemin qui identifie un test d'un
    run à l'autre.
    """
    source = getattr(test.parent, "source", None)
    if not source:
        return None
    try:
        return Path(source).resolve().relative_to(paths.PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _test_entry(test) -> dict:
    """Extrait d'un test ce qui sert à juger sa stabilité, jamais son détail d'exécution."""
    source = _relative_source(test)
    return {
        # Le nom complet Robot ne convient PAS comme clé : la suite racine y porte le nom
        # du run (`-N Smoke_Test_Chromium_Desktop`) et change avec le périmètre lancé.
        # L'historique d'un test se fragmenterait à chaque changement de configuration.
        "test": f"{source}::{test.name}",
        "name": test.name,
        "source": source,
        "status": test.status,
        "elapsed_ms": round(test.elapsed_time.total_seconds() * 1000),
        "message": test.message[:MESSAGE_MAX],
        "tags": list(test.tags),
    }


class _TestCollector(ResultVisitor):
    """Collecte les tests d'un résultat sans descendre dans les mots-clés."""

    def __init__(self) -> None:
        self.tests: list = []

    def visit_test(self, test) -> None:
        self.tests.append(test)

"""Découverte des tests et de leurs tags avec le parseur officiel Robot Framework."""

from pathlib import Path
from typing import Any, TypedDict

from robot.api import TestSuiteBuilder
from robot.errors import DataError

from core.logging_config import get_logger
from core.paths import paths

logger = get_logger(__name__)


class TestMetadata(TypedDict):
    """Structure transmise aux services de tags, campagnes et routes API."""

    name: str
    tags: list[str]
    file: str


def get_robot_files() -> list[Path]:
    """Retourne dans un ordre stable tous les fichiers de suites Robot.

    Returns:
        Les chemins des fichiers ``.robot`` présents sous ``test_suites``.
    """
    if not paths.TEST_SUITES.exists():
        return []
    return sorted(paths.TEST_SUITES.rglob("*.robot"))


def _build_metadata(test: Any) -> TestMetadata | None:
    """Convertit un test du modèle Robot vers le contrat historique de TestOps."""
    if test.source is None:
        logger.warning("Test Robot sans fichier source ignoré : %s", test.name)
        return None

    source = Path(test.source).resolve()
    try:
        relative_source = source.relative_to(paths.PROJECT_ROOT)
    except ValueError:
        logger.warning("Test Robot hors du projet ignoré : %s", source)
        return None

    return {
        "name": test.name,
        "tags": [str(tag) for tag in test.tags],
        "file": str(relative_source),
    }


def build_tests_list(files_list: list[str | Path] | None = None) -> list[TestMetadata]:
    """Construit les métadonnées des tests résolus par Robot Framework.

    La construction part du dossier complet afin d'appliquer les fichiers
    ``__init__.robot`` et les tags hérités comme lors d'une véritable exécution.
    ``files_list`` limite ensuite le résultat aux sources demandées.

    Args:
        files_list: Fichiers de tests à conserver. Tous les fichiers découverts
            sont utilisés lorsque la valeur est absente.

    Returns:
        Les dictionnaires ``name``, ``tags`` et ``file`` attendus par les services
        existants. Les tags suivent l'ordre normalisé de Robot Framework.
    """
    selected_files = files_list if files_list is not None else get_robot_files()
    selected_sources = {Path(file_path).resolve() for file_path in selected_files}
    if not selected_sources or not paths.TEST_SUITES.exists():
        return []

    try:
        suite = TestSuiteBuilder().build(paths.TEST_SUITES)
    except (DataError, OSError) as exc:
        logger.error("Découverte des tests Robot impossible : %s", exc)
        logger.debug("Détail de la découverte des tests Robot", exc_info=True)
        return []

    tests: list[TestMetadata] = []
    for test in suite.all_tests:
        if test.source is None or Path(test.source).resolve() not in selected_sources:
            continue
        metadata = _build_metadata(test)
        if metadata is not None:
            tests.append(metadata)
    return tests

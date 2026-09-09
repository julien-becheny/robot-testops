"""Garde-fous communs à toute la suite unitaire."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from services.execution import run_meta


@pytest.fixture(autouse=True)
def disposable_run_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Empêche un test unitaire d'écrire dans le dossier de rapports réel de la machine.

    Les workflows déposent la carte d'identité du run avant de lancer Robot. Sans cette
    redirection, une simple suite unitaire salirait `~/rf_output/report` de dossiers
    vides et lancerait un `git rev-parse` à chaque test.
    """
    reports = tmp_path / "report"
    monkeypatch.setattr(run_meta.paths, "REPORTS", reports)
    monkeypatch.setattr(run_meta, "current_commit", Mock(return_value="a1b2c3d"))
    return reports

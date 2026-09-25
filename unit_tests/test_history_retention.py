"""Tests unitaires de la purge des dossiers de rapport."""

import os
import time
from pathlib import Path

import pytest

from services.execution.run_meta import META_FILE
from services.history import retention

OLD = retention.MAX_AGE_DAYS + 5
RECENT = 3


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isole la racine des rapports pour que la purge ne touche jamais le vrai dossier."""
    root = tmp_path / "report"
    root.mkdir()
    monkeypatch.setattr(retention.paths, "REPORTS", root)
    return root


def _run_dir(reports: Path, name: str, age_days: float, owned: bool = True) -> Path:
    """Fabrique un dossier de run d'un âge donné, produit ou non par ce TestOps."""
    run_dir = reports / name
    run_dir.mkdir()
    (run_dir / "output.xml").write_text("<robot/>", encoding="utf-8")
    if owned:
        marker = run_dir / META_FILE
        marker.write_text('{"commit": "abc"}', encoding="utf-8")
        stamp = time.time() - age_days * retention.SECONDS_PER_DAY
        os.utime(marker, (stamp, stamp))
    return run_dir


def test_purges_an_old_run_it_produced(reports: Path) -> None:
    """Passé le délai, un rapport n'est plus consulté : l'historique en garde le verdict."""
    run_dir = _run_dir(reports, "2026_01_01-090000", OLD)

    assert retention.purge_old_runs() == 1
    assert not run_dir.exists()


def test_keeps_a_recent_run(reports: Path) -> None:
    """Purger un run encore consultable priverait d'un log qu'on vient juste de produire."""
    run_dir = _run_dir(reports, "2026_09_10-090000", RECENT)

    assert retention.purge_old_runs() == 0
    assert run_dir.is_dir()


def test_never_touches_a_run_from_another_project(reports: Path) -> None:
    """Le dossier de rapports est partagé : sans marqueur, le run est celui d'un voisin.

    C'est le garde-fou central de ce module - l'enlever détruirait le travail d'autrui.
    """
    foreign = _run_dir(reports, "2026_01_01-080000", OLD, owned=False)
    old_stamp = time.time() - OLD * retention.SECONDS_PER_DAY
    os.utime(foreign, (old_stamp, old_stamp))

    assert retention.purge_old_runs() == 0
    assert foreign.is_dir()


def test_never_touches_the_load_reports(reports: Path) -> None:
    """`report/load` n'est pas un run : les rapports de charge y survivent à leur run."""
    load_dir = reports / "load"
    load_dir.mkdir()
    report = load_dir / "k6_542b40fb.html"
    report.write_text("<html/>", encoding="utf-8")
    old_stamp = time.time() - OLD * retention.SECONDS_PER_DAY
    os.utime(load_dir, (old_stamp, old_stamp))

    assert retention.purge_old_runs() == 0
    assert report.is_file()


def test_ignores_loose_files_at_the_root(reports: Path) -> None:
    """Un fichier déposé à la racine n'est pas un dossier de run."""
    stray = reports / "notes.txt"
    stray.write_text("", encoding="utf-8")

    assert retention.purge_old_runs() == 0
    assert stray.is_file()


def test_expired_runs_deletes_nothing(reports: Path) -> None:
    """L'inventaire doit pouvoir s'afficher sans rien détruire."""
    run_dir = _run_dir(reports, "2026_01_01-090000", OLD)

    assert retention.expired_runs() == [run_dir]
    assert run_dir.is_dir()


def test_survives_a_missing_reports_root(monkeypatch: pytest.MonkeyPatch,
                                         tmp_path: Path) -> None:
    """Sur une machine neuve, aucun run n'a encore été joué."""
    monkeypatch.setattr(retention.paths, "REPORTS", tmp_path / "absent")

    assert retention.purge_old_runs() == 0

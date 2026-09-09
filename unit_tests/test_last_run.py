"""Dernier run : ce que l'accueil affirme, et ce qu'il refuse d'inventer."""

import os
from pathlib import Path

import pytest

from services.execution import history

_OUTPUT = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.4.2">
  <suite name="{name}"/>
  <statistics>
    <total><stat pass="{passed}" fail="{failed}" skip="0">All Tests</stat></total>
  </statistics>
</robot>
"""


@pytest.fixture
def reports(monkeypatch, tmp_path) -> Path:
    """Isole les rapports du poste : les tests ne doivent pas lire les vrais runs."""
    monkeypatch.setattr(history.paths, "REPORTS", tmp_path)
    return tmp_path


def _write_run(reports: Path, folder: str, *, name="Run", passed=2, failed=0,
               layout=(history.OUTPUT_FILE, history.LOG_FILE), with_log=True) -> Path:
    """Ecrit un run dans l'une des dispositions réellement produites par le dépôt."""
    output_name, log_name = layout
    run_dir = reports / folder
    output = run_dir / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        _OUTPUT.format(name=name, passed=passed, failed=failed), encoding="utf-8"
    )
    if with_log:
        (run_dir / log_name).write_text("<html></html>", encoding="utf-8")
    return run_dir


def test_no_run_yet_is_said_plainly(reports) -> None:
    """Un dépôt neuf n'a rien joué : mieux vaut le dire que d'afficher un faux verdict."""
    assert history.last_run() is None
    assert history.last_run_dir() is None


def test_the_most_recent_run_wins(reports) -> None:
    """L'accueil parle du dernier run, pas d'un run au hasard."""
    old = _write_run(reports, "2026_01_01-000000", name="Ancien")
    recent = _write_run(reports, "2026_08_24-120000", name="Recent")
    os.utime(old / history.OUTPUT_FILE, (1, 1))
    os.utime(recent / history.OUTPUT_FILE, (2_000_000_000, 2_000_000_000))

    assert history.last_run()["name"] == "Recent"


def test_a_failed_run_is_reported_as_failed(reports) -> None:
    """Annoncer « réussi » sur un run rouge ferait perdre la confiance dans la page."""
    _write_run(reports, "2026_08_24-120000", passed=11, failed=3)

    summary = history.last_run()

    assert summary["status"] == "failed"
    assert (summary["failed"], summary["passed"], summary["total"]) == (3, 11, 14)


def test_an_unreadable_result_does_not_break_the_page(reports) -> None:
    """Un output.xml tronqué (run tué) ne doit pas empêcher l'accueil de s'afficher."""
    run_dir = reports / "2026_08_24-120000"
    run_dir.mkdir(parents=True)
    (run_dir / history.OUTPUT_FILE).write_text("<robot><suite", encoding="utf-8")

    assert history.last_run() is None


def test_a_run_without_log_is_not_offered_for_opening(reports) -> None:
    """Proposer un lien vers un log absent donnerait une erreur au clic."""
    _write_run(reports, "2026_08_24-120000", with_log=False)

    assert history.last_run()["log"] is None


def test_a_rerun_result_is_found_where_it_is_actually_written(reports) -> None:
    """Avec « rejouer les échecs », la racine du run reste vide : le résultat est dessous."""
    _write_run(
        reports,
        "2026_08_25-110557",
        name="Execution_Filtree",
        layout=history.RESULT_LAYOUTS[2],
    )

    summary = history.last_run()

    assert summary["name"] == "Execution_Filtree"
    assert summary["log"] == "Output_original/log_original.html"


def test_the_merged_result_wins_over_the_first_pass(reports) -> None:
    """Après fusion, seul le résultat fusionné dit ce qu'est devenu le run."""
    _write_run(reports, "2026_08_25-110557", passed=9, failed=1,
               layout=history.RESULT_LAYOUTS[2])
    _write_run(reports, "2026_08_25-110557", passed=10, failed=0,
               layout=history.RESULT_LAYOUTS[0])

    summary = history.last_run()

    assert (summary["passed"], summary["failed"]) == (10, 0)
    assert summary["log"] == "Output_merge/log_merge.html"


def test_the_run_folder_is_served_not_its_sub_folder(reports) -> None:
    """Le log fusionné renvoie aux captures du premier passage, un dossier plus haut."""
    run_dir = _write_run(reports, "2026_08_25-110557", layout=history.RESULT_LAYOUTS[0])

    assert history.last_run_dir() == run_dir

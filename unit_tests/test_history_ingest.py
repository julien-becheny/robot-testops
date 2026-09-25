"""Tests unitaires de l'ingestion des résultats vers la mémoire des exécutions."""

import json
from pathlib import Path

import pytest

from services.execution import run_meta
from services.history import ingest, store

_OUTPUT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.4.2" generated="2026-09-06T10:15:30.000000" rpa="false" \
schemaversion="5">
<suite id="s1" name="{run_name}" source="{root}">
<suite id="s1-s1" name="Smoke" source="{source}">
<test id="s1-s1-t1" name="Connexion valide" line="10">
<tag>smoke</tag>
<status status="PASS" start="2026-09-06T10:15:31.000000" elapsed="1.5"/>
</test>
<test id="s1-s1-t2" name="Panier vide" line="20">
<tag>cart</tag>
<status status="{status}" start="2026-09-06T10:15:33.000000" elapsed="0.25">{message}\
</status>
</test>
<status status="{status}" start="2026-09-06T10:15:31.000000" elapsed="2.0"/>
</suite>
<status status="{status}" start="2026-09-06T10:15:31.000000" elapsed="2.0"/>
</suite>
</robot>
"""


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Simule un dépôt isolé : ses suites, son dossier de rapports, son historique."""
    monkeypatch.setattr(ingest.paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ingest.paths, "REPORTS", tmp_path / "report")
    monkeypatch.setattr(store, "HISTORY_FILE", tmp_path / "test_history.jsonl")
    monkeypatch.setattr(store, "STATE_FILE", tmp_path / "test_history_state.json")
    (tmp_path / "report").mkdir()
    return tmp_path


def _write_run(
    repo_root: Path,
    run_id: str,
    layout: str = "output.xml",
    status: str = "FAIL",
    message: str = "Élément introuvable",
    source: Path | None = None,
    run_name: str = "Saucedemo",
    meta: dict | None = None,
) -> Path:
    """Fabrique un dossier de run contenant un résultat Robot et son contexte."""
    run_dir = repo_root / "report" / run_id
    output = run_dir / layout
    output.parent.mkdir(parents=True, exist_ok=True)
    suite_source = source or repo_root / "test_suites" / "00_smoke.robot"
    output.write_text(
        _OUTPUT_XML.format(
            run_name=run_name,
            root=suite_source.parent,
            source=suite_source,
            status=status,
            message=message,
        ),
        encoding="utf-8",
    )
    if meta is not None:
        (run_dir / run_meta.META_FILE).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
    return run_dir


def _foreign_suite(repo_root: Path) -> Path:
    """Retourne une suite située hors du dépôt, comme celle d'un autre projet de la machine."""
    return repo_root.parent / "autre_depot" / "test_suites" / "00_smoke.robot"


def test_ingest_records_one_entry_per_test_with_its_context(repo: Path) -> None:
    """Chaque test joué devient une entrée, complétée par le contexte du run."""
    _write_run(
        repo,
        "2026_09_06-101530_chromium_desktop",
        meta={
            "commit": "a1b2c3d",
            "environment": "saucedemo",
            "browser": "chromium",
            "device": "desktop",
        },
    )

    assert ingest.ingest_new_runs() == 1

    entries = store.read_entries(runs=5)
    assert [entry["test"] for entry in entries] == [
        "test_suites/00_smoke.robot::Connexion valide",
        "test_suites/00_smoke.robot::Panier vide",
    ]
    passed, failed = entries
    assert passed["source"] == "test_suites/00_smoke.robot"
    assert passed["status"] == "PASS"
    assert passed["elapsed_ms"] == 1500
    assert passed["tags"] == ["smoke"]
    assert passed["commit"] == "a1b2c3d"
    assert passed["environment"] == "saucedemo"
    assert passed["browser"] == "chromium"
    assert passed["rerun"] is False
    assert failed["status"] == "FAIL"
    assert failed["message"] == "Élément introuvable"


def test_ingest_is_idempotent(repo: Path) -> None:
    """Un dossier déjà vu n'est jamais réanalysé : sinon chaque lecture doublerait tout."""
    _write_run(repo, "2026_09_06-101530")

    assert ingest.ingest_new_runs() == 1
    assert ingest.ingest_new_runs() == 0
    assert len(store.read_entries(runs=5)) == 2


def test_ingest_skips_the_aggregated_report_of_a_campaign(repo: Path) -> None:
    """Le rapport d'une campagne fusionne des runs déjà vus : le compter doublerait leurs tests."""
    _write_run(repo, "2026_09_06-101530_camp_chromium_desktop_ab12cd34")
    _write_run(repo, "campaign_camp_2a9dfdafd577")

    assert ingest.ingest_new_runs() == 1
    assert {entry["run_id"] for entry in store.read_entries(runs=5)} == {
        "2026_09_06-101530_camp_chromium_desktop_ab12cd34"
    }


def test_ingest_prefers_the_merged_result_of_a_rerun(repo: Path) -> None:
    """Le rejeu porte le verdict final : compter aussi le premier passage inventerait un échec."""
    run_id = "2026_09_06-101530"
    _write_run(repo, run_id, layout="Output_original/output_original.xml", status="FAIL")
    _write_run(repo, run_id, layout="Output_merge/output_merge.xml", status="PASS", message="")

    ingest.ingest_new_runs()

    entries = store.read_entries(runs=5)
    assert len(entries) == 2
    assert {entry["status"] for entry in entries} == {"PASS"}
    assert all(entry["rerun"] for entry in entries)


def test_ingest_skips_a_run_that_produced_no_result(repo: Path) -> None:
    """Un run sans résultat n'est pas marqué comme vu : il sera relu quand il en aura un."""
    (repo / "report" / "2026_09_06-101530").mkdir()

    assert ingest.ingest_new_runs() == 0
    assert store.stored_run_ids() == []
    assert store.scan_watermark() == 0.0


def test_ingest_ignores_a_corrupt_result(repo: Path) -> None:
    """Un résultat illisible se journalise, il n'interrompt pas l'ingestion des autres."""
    corrupt = repo / "report" / "2026_09_06-101530" / "output.xml"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("<robot>pas un résultat", encoding="utf-8")
    _write_run(repo, "2026_09_06-102000")

    assert ingest.ingest_new_runs() == 1
    assert store.stored_run_ids() == ["2026_09_06-102000"]


def test_ingest_ignores_runs_coming_from_another_repository(repo: Path) -> None:
    """Le dossier de rapports est partagé : mélanger deux produits rendrait tout verdict faux."""
    _write_run(repo, "2026_09_06-101530", source=_foreign_suite(repo))

    assert ingest.ingest_new_runs() == 0
    assert store.stored_run_ids() == []


def test_a_discarded_run_is_never_analysed_twice(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
) -> None:
    """Un run écarté ne laisse aucune entrée : sans repère, son XML serait relu à chaque lecture."""
    _write_run(repo, "2026_09_06-101530", source=_foreign_suite(repo))
    parsed: list[str] = []
    real_parser = ingest.ExecutionResult
    monkeypatch.setattr(
        ingest,
        "ExecutionResult",
        lambda path: parsed.append(path) or real_parser(path),
    )

    assert ingest.ingest_new_runs() == 0
    assert ingest.ingest_new_runs() == 0
    assert len(parsed) == 1


def test_the_key_of_a_test_does_not_depend_on_the_run_configuration(repo: Path) -> None:
    """La suite racine porte le nom du run (`-N`) : la retenir couperait l'historique en deux."""
    _write_run(repo, "2026_09_06-101530", run_name="Smoke_Test_Chromium_Desktop")
    _write_run(repo, "2026_09_06-102000", run_name="Smoke_Test_Firefox_Mobile")

    ingest.ingest_new_runs()

    keys = {entry["test"] for entry in store.read_entries(runs=5)}
    assert keys == {
        "test_suites/00_smoke.robot::Connexion valide",
        "test_suites/00_smoke.robot::Panier vide",
    }


def test_ingest_accepts_runs_without_context(repo: Path) -> None:
    """Les runs antérieurs à la carte d'identité restent exploitables, sans commit."""
    _write_run(repo, "2026_09_06-101530")

    ingest.ingest_new_runs()

    assert store.read_entries(runs=5)[0]["commit"] is None

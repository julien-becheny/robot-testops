"""Tests du parser officiel utilisé pour l'inventaire des suites Robot."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from robot.errors import DataError

from services.tags import parser


@pytest.fixture
def robot_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Crée une arborescence Robot temporaire et redirige les chemins du projet."""
    test_suites = tmp_path / "test_suites"
    test_suites.mkdir()
    monkeypatch.setattr(parser.paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(parser.paths, "TEST_SUITES", test_suites)
    return test_suites


def _write_robot(path: Path, content: str) -> Path:
    """Écrit une suite Robot lisible par TestSuiteBuilder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_get_robot_files_returns_nested_files_in_stable_order(robot_project: Path) -> None:
    """La découverte retourne tous les fichiers Robot dans un ordre déterministe."""
    second = _write_robot(robot_project / "z_module" / "second.robot", "*** Test Cases ***\nTest Z\n  No Operation\n")
    first = _write_robot(robot_project / "a_module" / "first.robot", "*** Test Cases ***\nTest A\n  No Operation\n")

    assert parser.get_robot_files() == [first, second]


def test_build_tests_list_resolves_global_local_and_continued_tags(robot_project: Path) -> None:
    """Les tags globaux, locaux et continués sont résolus par Robot Framework."""
    suite_file = _write_robot(
        robot_project / "module" / "tags.robot",
        """*** Settings ***
Test Tags  global
...  continued

*** Test Cases ***
Premier test
  [Tags]  local
  No Operation

Second test
  No Operation
""",
    )

    tests = parser.build_tests_list([suite_file])

    assert [test["name"] for test in tests] == ["Premier test", "Second test"]
    assert set(tests[0]["tags"]) == {"global", "continued", "local"}
    assert set(tests[1]["tags"]) == {"global", "continued"}
    assert tests[0]["file"] == str(Path("test_suites/module/tags.robot"))


def test_build_tests_list_applies_parent_init_tags(robot_project: Path) -> None:
    """Les tags hérités d'un fichier __init__.robot sont inclus comme au runtime."""
    _write_robot(
        robot_project / "module" / "__init__.robot",
        "*** Settings ***\nTest Tags  inherited\n",
    )
    suite_file = _write_robot(
        robot_project / "module" / "suite.robot",
        "*** Test Cases ***\nTest hérité\n  No Operation\n",
    )

    tests = parser.build_tests_list([suite_file])

    assert len(tests) == 1
    assert "inherited" in tests[0]["tags"]


def test_build_tests_list_filters_requested_sources(robot_project: Path) -> None:
    """Le paramètre files_list limite le résultat après résolution de l'arbre complet."""
    first = _write_robot(robot_project / "first.robot", "*** Test Cases ***\nPremier\n  No Operation\n")
    _write_robot(robot_project / "second.robot", "*** Test Cases ***\nSecond\n  No Operation\n")

    tests = parser.build_tests_list([first])

    assert [test["name"] for test in tests] == ["Premier"]


def test_build_tests_list_handles_robot_data_error(
    monkeypatch: pytest.MonkeyPatch,
    robot_project: Path,
) -> None:
    """Une suite invalide retourne une liste vide et journalise l'erreur Robot."""
    suite_file = _write_robot(robot_project / "invalid.robot", "*** Test Cases ***\nTest\n")
    builder = Mock()
    builder.build.side_effect = DataError("suite invalide")
    monkeypatch.setattr(parser, "TestSuiteBuilder", Mock(return_value=builder))

    assert parser.build_tests_list([suite_file]) == []
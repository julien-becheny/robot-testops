"""Nommage des traces Playwright : ce qui rend un fichier identifiable, et unique."""

from types import SimpleNamespace

import pytest

from libraries.resources.common import tracing


@pytest.fixture(autouse=True)
def fresh_names():
    """Le registre des noms vit le temps d'un run : chaque test repart à zéro."""
    tracing._used_names.clear()
    yield
    tracing._used_names.clear()


def _robot_context(monkeypatch, tracing_on, test_name="Un test") -> None:
    """Simule les variables Robot Framework que le helper interroge."""
    values = {"${TRACING}": tracing_on, "${TEST NAME}": test_name}
    monkeypatch.setattr(
        tracing,
        "BuiltIn",
        lambda: SimpleNamespace(
            get_variable_value=lambda key, default=None: values.get(key, default)
        ),
    )


def test_nothing_is_recorded_when_the_setting_is_off(monkeypatch) -> None:
    """Sans réglage, aucun contexte ne doit se mettre à écrire une trace."""
    _robot_context(monkeypatch, tracing_on=False)

    assert tracing.get_trace_target() is None


def test_the_file_carries_the_test_name(monkeypatch) -> None:
    """Un nom de fichier illisible ne vaut pas mieux que pas de fichier du tout."""
    _robot_context(monkeypatch, tracing_on="True", test_name="Navigation - Sidebar Menu")

    assert tracing.get_trace_target() == "browser/traces/navigation_sidebar_menu.zip"


def test_two_tests_sharing_a_name_keep_their_own_trace(monkeypatch) -> None:
    """Deux suites peuvent nommer un test pareil : le second effacerait le premier."""
    _robot_context(monkeypatch, tracing_on="True", test_name="Smoke - Login")

    first = tracing.get_trace_target()
    second = tracing.get_trace_target()

    assert first != second


def test_a_name_without_usable_characters_still_yields_a_file(monkeypatch) -> None:
    """Un nom vide donnerait un chemin invalide, et la trace serait perdue."""
    _robot_context(monkeypatch, tracing_on="True", test_name="--- ///")

    assert tracing.get_trace_target() == "browser/traces/test.zip"

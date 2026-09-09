"""Tests des commandes Robot Framework : ce que chaque run embarque, et ce qu'il écarte."""

import sys

import pytest

from api.app import app
from services.execution import commands

_TRACING_VAR = "TRACING:True"


def _set_tracing(monkeypatch, value: str) -> None:
    """Impose le réglage global sans toucher à la configuration du poste."""
    original = commands.config.get
    monkeypatch.setattr(
        commands.config,
        "get",
        lambda key, default=None: value if key == "RF_TRACING" else original(key, default),
    )


@pytest.fixture
def browser_runs(monkeypatch, tmp_path) -> dict:
    """Les commandes qui pilotent un navigateur.

    Le run randomisé écrit son fichier d'arguments : on l'isole dans tmp_path.
    """
    monkeypatch.setattr(commands.paths, "REPORTS", tmp_path)
    return {
        "smoke": lambda: commands.get_smoke_cmd("run"),
        "filtre": lambda: commands.get_tag_filtered_cmd("run", ["smoke"], []),
        "randomise": lambda: commands.get_randomized_cmd("run", ["Suite.Test"]),
        "campagne": lambda: commands.get_campaign_cmd("run", ["Suite.Test"]),
    }


def _excluded_tags(command: list[str]) -> list[str]:
    """Retourne les tags passés en `-e`."""
    return [command[index + 1] for index, arg in enumerate(command) if arg == "-e"]


def test_standard_runs_inject_the_playwright_adapter() -> None:
    """Les suites multi-moteur partent avec les autres, jouées par Playwright."""
    command = commands.get_tag_filtered_cmd("run", ["smoke"], [])

    actions = next(arg for arg in command if arg.startswith("ACTIONS:"))
    assert actions.endswith("actions_playwright.resource")


def test_smoke_run_plays_the_suite_announced_by_the_api() -> None:
    """L'accueil annonce ce que le smoke va jouer : la même suite, pas une copie du chemin."""
    command = commands.get_smoke_cmd("run")
    announced = app.test_client().get('/smoke-suite').get_json()

    assert command[-1] == str(commands.SMOKE_SUITE)
    assert announced['file'] == commands.SMOKE_SUITE.name
    assert announced['tests']


@pytest.mark.parametrize("run_name", ["smoke", "filtre", "randomise", "campagne"])
def test_a_run_records_no_trace_unless_asked(monkeypatch, browser_runs, run_name) -> None:
    """La trace se demande : un run ordinaire n'en paie ni le coût ni l'encombrement."""
    _set_tracing(monkeypatch, "off")

    assert _TRACING_VAR not in browser_runs[run_name]()


@pytest.mark.parametrize("run_name", ["smoke", "filtre", "randomise", "campagne"])
def test_the_setting_traces_every_browser_run(monkeypatch, browser_runs, run_name) -> None:
    """Un diagnostic s'active une fois : il vaut pour tous les runs, pas seulement le smoke."""
    _set_tracing(monkeypatch, "on")

    assert _TRACING_VAR in browser_runs[run_name]()


@pytest.mark.parametrize("run_name", ["smoke", "filtre", "randomise", "campagne"])
def test_every_run_uses_the_interpreter_of_this_project(browser_runs, run_name) -> None:
    """Appeler « robot » tout court laisse le PATH décider.

    Sur un poste où un autre projet a été activé, les tests partaient avec SES
    librairies et échouaient pour des raisons imaginaires.
    """
    assert browser_runs[run_name]()[:3] == [sys.executable, "-m", "robot"]

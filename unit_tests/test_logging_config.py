"""Tests de la configuration commune des journaux TestOps."""

import logging
from collections.abc import Iterator

import pytest

from core.logging_config import HANDLER_NAME, LOGGER_NAME, _resolve_level, configure_logging, get_logger


@pytest.fixture
def isolated_testops_logger() -> Iterator[logging.Logger]:
    """Isole le logger TestOps afin qu'un test ne modifie pas les autres."""
    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    original_propagate = logger.propagate
    logger.handlers = []

    yield logger

    for handler in logger.handlers:
        handler.close()
    logger.handlers = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate


def test_resolve_level_accepts_names_and_falls_back_to_info() -> None:
    """Les niveaux connus sont résolus et une valeur inconnue utilise INFO."""
    assert _resolve_level("debug") == logging.DEBUG
    assert _resolve_level(logging.WARNING) == logging.WARNING
    assert _resolve_level("niveau-inconnu") == logging.INFO


def test_configure_logging_does_not_duplicate_console_output(
    isolated_testops_logger: logging.Logger,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Deux configurations successives conservent un seul message en console."""
    configure_logging("INFO")
    configure_logging("INFO")

    handlers = [
        handler
        for handler in isolated_testops_logger.handlers
        if handler.get_name() == HANDLER_NAME
    ]
    get_logger("validation").info("message unique")

    assert len(handlers) == 1
    assert capsys.readouterr().out.count("message unique") == 1


def test_get_logger_identifies_the_calling_module() -> None:
    """Le logger enfant conserve le module d'origine dans son nom."""
    assert get_logger("api.app").name == "testops.api.app"
    assert get_logger("testops.services.execution").name == "testops.services.execution"
"""Tests du client live best-effort utilisé par le processus Locust."""

from unittest.mock import Mock

import pytest
import requests

from services.load import live_api


def test_post_live_checks_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un POST live réussi vérifie aussi son statut HTTP."""
    response = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(live_api.requests, "post", post)

    result = live_api.post_live(
        "http://127.0.0.1:5001",
        "session-1",
        "/log",
        {"message": "test"},
    )

    assert result is True
    post.assert_called_once_with(
        "http://127.0.0.1:5001/log",
        json={"message": "test", "session_id": "session-1"},
        timeout=5,
    )
    response.raise_for_status.assert_called_once_with()


def test_post_live_network_error_remains_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une panne de l'API live est journalisée sans interrompre Locust."""
    monkeypatch.setattr(
        live_api.requests,
        "post",
        Mock(side_effect=requests.ConnectionError("API indisponible")),
    )
    debug = Mock()
    monkeypatch.setattr(live_api.logger, "debug", debug)

    result = live_api.post_live(
        "http://127.0.0.1:5001",
        "session-1",
        "/log",
        {"message": "test"},
    )

    assert result is False
    debug.assert_called_once()
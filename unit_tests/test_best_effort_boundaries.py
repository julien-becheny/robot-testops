"""Tests de la frontière best-effort réseau du listener d'exécution."""

from unittest.mock import Mock

import pytest
import requests

from robot_listeners.execution_listener import ExecutionListener


def test_listener_posts_payload_and_checks_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une notification du listener vérifie la réponse HTTP reçue."""
    response = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(
        'robot_listeners.execution_listener.requests.post',
        post,
    )
    listener = ExecutionListener('session-1')

    listener.send_log('message')

    post.assert_called_once_with(
        'http://127.0.0.1:5001/log',
        json={'message': 'message', 'level': 'info', 'session_id': 'session-1'},
        timeout=3,
    )
    response.raise_for_status.assert_called_once_with()


def test_listener_network_error_remains_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une panne réseau du listener ne fait jamais échouer le test Robot."""
    monkeypatch.setattr(
        'robot_listeners.execution_listener.requests.post',
        Mock(side_effect=requests.ConnectionError('API indisponible')),
    )
    listener = ExecutionListener('session-1')

    listener.send_final_status('1 test, 1 passed')

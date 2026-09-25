"""Tests des frontières best-effort réseau et transactionnelle SQLite."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from robot_listeners.execution_listener import ExecutionListener
from services.campaigns import db as campaign_db


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


def test_campaign_connection_commits_successful_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une sortie normale du contexte SQLite valide la transaction."""
    monkeypatch.setattr(campaign_db, 'DB_PATH', tmp_path / 'campaigns.db')

    with campaign_db.get_connection() as connection:
        connection.execute('CREATE TABLE sample (value TEXT)')
        connection.execute('INSERT INTO sample VALUES (?)', ('committed',))

    with campaign_db.get_connection() as connection:
        value = connection.execute('SELECT value FROM sample').fetchone()['value']
    assert value == 'committed'


def test_campaign_connection_rolls_back_and_propagates_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une exception annule la transaction puis remonte sans être masquée."""
    monkeypatch.setattr(campaign_db, 'DB_PATH', tmp_path / 'campaigns.db')
    with campaign_db.get_connection() as connection:
        connection.execute('CREATE TABLE sample (value TEXT)')

    with (
        pytest.raises(RuntimeError, match='échec métier'),
        campaign_db.get_connection() as connection,
    ):
        connection.execute('INSERT INTO sample VALUES (?)', ('rolled-back',))
        raise RuntimeError('échec métier')

    with campaign_db.get_connection() as connection:
        count = connection.execute('SELECT COUNT(*) AS count FROM sample').fetchone()['count']
    assert count == 0

"""Le verdict d'un test circule comme une donnée, pas comme une phrase à relire."""

from unittest.mock import Mock

import pytest

from api.app import app
from api.routes import execution_routes


@pytest.fixture
def client():
    """Retourne le client Flask sans démarrer de serveur réseau."""
    return app.test_client()


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Capte la diffusion SocketIO sans ouvrir de socket."""
    emit = Mock()
    monkeypatch.setattr(execution_routes, "_emit_to_session", emit)
    return emit


def test_a_verdict_is_broadcast_to_its_own_session(client, emitted: Mock) -> None:
    """Sans le session_id, la grille attribuerait le résultat à la mauvaise configuration."""
    response = client.post('/test-result', json={
        'session_id': 'session-firefox',
        'longname': 'Web.Saucedemo.02 Cart.Panier — Ajouter un article',
        'name': 'Panier — Ajouter un article',
        'status': 'FAIL',
        'message': 'Timeout',
        'elapsed': 4200,
    })

    assert response.status_code == 200
    emitted.assert_called_once_with(
        'test-result',
        {
            'longname': 'Web.Saucedemo.02 Cart.Panier — Ajouter un article',
            'name': 'Panier — Ajouter un article',
            'status': 'FAIL',
            'message': 'Timeout',
            'elapsed': 4200,
        },
        'session-firefox',
    )


def test_the_short_name_falls_back_to_the_full_one(client, emitted: Mock) -> None:
    """Une ligne sans libellé serait vide : le nom complet vaut mieux que rien."""
    client.post('/test-result', json={
        'session_id': 'session-1',
        'longname': 'Suite.Test',
        'status': 'PASS',
    })

    assert emitted.call_args.args[1]['name'] == 'Suite.Test'


def test_a_verdict_without_full_name_is_refused(client, emitted: Mock) -> None:
    """Le nom complet est la clé de la ligne : sans lui, la cellule serait orpheline."""
    response = client.post('/test-result', json={'session_id': 's', 'status': 'PASS'})

    assert response.status_code == 400
    emitted.assert_not_called()


def test_a_verdict_without_status_is_refused(client, emitted: Mock) -> None:
    """Un statut vide s'afficherait « non joué » : un échec deviendrait invisible."""
    response = client.post('/test-result', json={
        'session_id': 's',
        'longname': 'Suite.Test',
        'status': '',
    })

    assert response.status_code == 400
    emitted.assert_not_called()


def test_a_non_string_message_stays_a_contract_error(client, emitted: Mock) -> None:
    """Une erreur de contrat reste une réponse 400 et non une panne interne."""
    response = client.post('/test-result', json={
        'session_id': 's',
        'longname': 'Suite.Test',
        'status': 'FAIL',
        'message': ['pas', 'une', 'chaîne'],
    })

    assert response.status_code == 400
    emitted.assert_not_called()

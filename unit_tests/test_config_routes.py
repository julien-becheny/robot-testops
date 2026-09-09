"""Tests du contrat HTTP public de la configuration TestOps."""

from unittest.mock import Mock

import pytest

from api.app import app
from core.config import MASKED_CONFIG_VALUE


@pytest.fixture
def client():
    """Retourne le client Flask sans démarrer de serveur réseau."""
    return app.test_client()


def test_get_config_masks_password_but_keeps_login_visible(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Le navigateur reçoit le login mais jamais la valeur du mot de passe."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "reload", Mock())
    monkeypatch.setattr(
        config_routes.config,
        "get_public_all",
        Mock(return_value={
            "RF_LOGIN": "utilisateur",
            "RF_PASSWORD": MASKED_CONFIG_VALUE,
            "RF_BASE_URL": "https://example.test",
        }),
    )

    response = client.get('/config-vars')

    assert response.status_code == 200
    assert response.get_json() == {
        "RF_BASE_URL": "https://example.test",
        "RF_LOGIN": "utilisateur",
        "RF_PASSWORD": MASKED_CONFIG_VALUE,
    }


@pytest.mark.parametrize("payload", [None, [], {}, {"key": "RF_BASE_URL"}])
def test_update_config_rejects_invalid_payload(client, payload) -> None:
    """Un body absent, non objet ou incomplet est refusé avant la sauvegarde."""
    response = client.post('/config-vars', json=payload)

    assert response.status_code == 400


def test_update_config_rejects_unknown_key(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une variable arbitraire ne peut pas être ajoutée depuis le navigateur."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "is_editable_key", Mock(return_value=False))
    save = Mock()
    monkeypatch.setattr(config_routes.config, "set", save)

    response = client.post('/config-vars', json={"key": "INCONNUE", "value": "x"})

    assert response.status_code == 400
    save.assert_not_called()


def test_update_config_rejects_masked_password(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Le marqueur public ne peut jamais devenir la valeur stockée du secret."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "is_editable_key", Mock(return_value=True))
    monkeypatch.setattr(config_routes.config, "is_sensitive_key", Mock(return_value=True))
    save = Mock()
    monkeypatch.setattr(config_routes.config, "set", save)

    response = client.post(
        '/config-vars',
        json={"key": "RF_PASSWORD", "value": MASKED_CONFIG_VALUE},
    )

    assert response.status_code == 400
    save.assert_not_called()


def test_update_password_returns_only_masked_value(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une sauvegarde de mot de passe ne réexpédie jamais sa valeur brute."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "is_editable_key", Mock(return_value=True))
    monkeypatch.setattr(config_routes.config, "is_sensitive_key", Mock(return_value=True))
    save = Mock(return_value=True)
    monkeypatch.setattr(config_routes.config, "set", save)
    monkeypatch.setattr(
        config_routes.config,
        "get_public_value",
        Mock(return_value=MASKED_CONFIG_VALUE),
    )

    response = client.post(
        '/config-vars',
        json={"key": "RF_PASSWORD", "value": "nouvelle-valeur"},
    )

    assert response.status_code == 200
    assert response.get_json()["value"] == MASKED_CONFIG_VALUE
    assert "nouvelle-valeur" not in response.get_data(as_text=True)
    save.assert_called_once_with("RF_PASSWORD", "nouvelle-valeur")


def test_clear_password_returns_null_public_value(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """L'effacement explicite stocke null et le confirme sans secret."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "is_editable_key", Mock(return_value=True))
    monkeypatch.setattr(config_routes.config, "is_sensitive_key", Mock(return_value=True))
    save = Mock(return_value=True)
    monkeypatch.setattr(config_routes.config, "set", save)
    monkeypatch.setattr(config_routes.config, "get_public_value", Mock(return_value=None))

    response = client.post('/config-vars', json={"key": "RF_PASSWORD", "value": None})

    assert response.status_code == 200
    assert response.get_json()["value"] is None
    save.assert_called_once_with("RF_PASSWORD", None)


def test_save_failure_returns_stable_public_error(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une erreur de persistance ne révèle aucun détail interne au navigateur."""
    from api.routes import config_routes

    monkeypatch.setattr(config_routes.config, "is_editable_key", Mock(return_value=True))
    monkeypatch.setattr(config_routes.config, "is_sensitive_key", Mock(return_value=False))
    monkeypatch.setattr(config_routes.config, "set", Mock(return_value=False))

    response = client.post('/config-vars', json={"key": "RF_BASE_URL", "value": "x"})

    assert response.status_code == 500
    assert response.get_json() == {"error": "Sauvegarde de la configuration impossible"}


def test_get_environments_expose_le_referentiel_et_la_cible_active(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """L'interface a besoin des environnements déclarés et de celui sélectionné."""
    from api.routes import config_routes

    declares = [{
        "id": "recette",
        "label": "Recette",
        "base": "https://recette.client.fr",
        "modules": ["travaux"],
    }]
    monkeypatch.setattr(config_routes.environments, "list_environments", Mock(return_value=declares))
    monkeypatch.setattr(config_routes.environments, "active_environment", Mock(return_value="recette"))

    response = client.get('/environments')

    assert response.status_code == 200
    assert response.get_json() == {"environments": declares, "active": "recette"}


def test_update_environment_refuse_une_cible_hors_referentiel(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Le menu de l'interface n'est pas une protection : l'API est appelable directement."""
    from api.routes import config_routes

    save = Mock(return_value=True)
    monkeypatch.setattr(config_routes.config, "set", save)
    monkeypatch.setattr(config_routes.environments, "get_environment", Mock(return_value=None))

    response = client.post(
        '/config-vars',
        json={"key": "RF_ENVIRONMENT", "value": "https://cible-non-autorisee.example"},
    )

    assert response.status_code == 400
    save.assert_not_called()
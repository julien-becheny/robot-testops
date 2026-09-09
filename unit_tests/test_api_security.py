"""Tests des valeurs réseau sûres utilisées par défaut par l'API TestOps."""

import pytest

import api.app as app_module
from api.socketio_instance import DEFAULT_ALLOWED_ORIGINS, _allowed_origins, allowed_origins


def test_api_address_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'API reste locale et utilise le port historique sans configuration."""
    monkeypatch.setattr(app_module.config, "get", lambda _key, default=None: default)

    assert app_module._api_host() == "127.0.0.1"
    assert app_module._api_port() == 5001


@pytest.mark.parametrize("configured_port", [None, "invalid", 0, 65_536])
def test_api_port_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    configured_port: object,
) -> None:
    """Une valeur de port absente, non numérique ou hors limites est refusée."""
    monkeypatch.setattr(
        app_module.config,
        "get",
        lambda key, default=None: configured_port if key == "API_PORT" else default,
    )

    assert app_module._api_port() == 5001


def test_allowed_origins_fall_back_to_local_frontends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une configuration CORS mal formée rétablit les origines locales sûres."""
    monkeypatch.setattr(app_module.config, "get", lambda _key, default=None: object())

    assert _allowed_origins() == list(DEFAULT_ALLOWED_ORIGINS)


def test_cors_accepts_configured_origin_and_rejects_unknown_origin() -> None:
    """Flask autorise une origine déclarée et n'en-tête pas une origine inconnue."""
    configured_origin = allowed_origins[0]
    unknown_origin = "https://example.invalid"
    assert unknown_origin not in allowed_origins

    client = app_module.app.test_client()
    allowed_response = client.get("/", headers={"Origin": configured_origin})
    denied_response = client.get("/", headers={"Origin": unknown_origin})

    assert allowed_response.headers["Access-Control-Allow-Origin"] == configured_origin
    assert "Access-Control-Allow-Origin" not in denied_response.headers
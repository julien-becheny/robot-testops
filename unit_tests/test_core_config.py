"""Tests unitaires du gestionnaire de configuration TestOps."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.config import MASKED_CONFIG_VALUE, Config, _default_config


def _isolated_config(config_file: Path) -> Config:
    """Construit une instance de test indépendante du singleton global."""
    instance = object.__new__(Config)
    instance.config_file = config_file
    instance._config_vars = {}
    instance._initialized = True
    return instance


def test_missing_file_creates_safe_default_config(tmp_path: Path) -> None:
    """Un premier démarrage crée un JSON complet avec des valeurs locales sûres."""
    config_file = tmp_path / "config" / "variables_config.json"
    instance = _isolated_config(config_file)

    instance._load_config()

    assert config_file.exists()
    assert instance.get("API_HOST") == "127.0.0.1"
    assert instance.get("LOG_LEVEL") == "INFO"
    assert json.loads(config_file.read_text(encoding="utf-8")) == _default_config()


def test_valid_json_is_loaded_without_adding_unspecified_values(tmp_path: Path) -> None:
    """Un fichier valide reste la source de vérité sans ajout implicite de clés."""
    config_file = tmp_path / "variables_config.json"
    config_file.write_text('{"RF_BROWSER": "firefox"}', encoding="utf-8")
    instance = _isolated_config(config_file)

    instance._load_config()

    assert instance.get_all() == {"RF_BROWSER": "firefox"}


def test_malformed_json_uses_defaults_without_overwriting_source(tmp_path: Path) -> None:
    """Un JSON mal formé reste disponible pour diagnostic et active les défauts."""
    config_file = tmp_path / "variables_config.json"
    malformed_content = '{"RF_BROWSER":'
    config_file.write_text(malformed_content, encoding="utf-8")
    instance = _isolated_config(config_file)

    instance._load_config()

    assert instance.get("RF_BROWSER") == "chromium"
    assert config_file.read_text(encoding="utf-8") == malformed_content


def test_bom_prefixed_json_is_loaded(tmp_path: Path) -> None:
    """Le Bloc-notes et `Set-Content -Encoding UTF8` écrivent un BOM : le fichier reste lisible."""
    config_file = tmp_path / "variables_config.json"
    config_file.write_text('\ufeff{"RF_BROWSER": "firefox"}', encoding="utf-8")
    instance = _isolated_config(config_file)

    instance._load_config()

    assert instance.get_all() == {"RF_BROWSER": "firefox"}


def test_utf16_json_written_by_powershell_5_is_loaded(tmp_path: Path) -> None:
    """`>` et `Out-File` de PowerShell 5 écrivent en UTF-16 : le fichier reste lisible."""
    config_file = tmp_path / "variables_config.json"
    config_file.write_text('{"RF_BROWSER": "firefox"}', encoding="utf-16")
    instance = _isolated_config(config_file)

    instance._load_config()

    assert instance.get_all() == {"RF_BROWSER": "firefox"}


def test_an_ansi_file_is_kept_and_never_overwritten(tmp_path: Path) -> None:
    """`Set-Content` sans `-Encoding` écrit en ANSI : le démarrage ne tombe pas, le fichier reste."""
    config_file = tmp_path / "variables_config.json"
    ansi_content = '{"RF_SLOW_MO": "déjà réglé"}'.encode("cp1252")
    config_file.write_bytes(ansi_content)
    instance = _isolated_config(config_file)

    instance._load_config()

    assert instance.get("RF_BROWSER") == "chromium"
    assert instance.set("RF_SLOW_MO", "0:00:01") is False
    assert config_file.read_bytes() == ansi_content


def test_a_save_never_overwrites_a_file_that_could_not_be_read(tmp_path: Path) -> None:
    """Un fichier illisible porte peut-être des secrets saisis à la main : jamais remplacé."""
    config_file = tmp_path / "variables_config.json"
    unreadable_content = '{"RF_SECRET_SAUCEDEMO": "saisi à la main",'  # pragma: allowlist secret
    config_file.write_text(unreadable_content, encoding="utf-8")
    instance = _isolated_config(config_file)
    instance._load_config()

    assert instance.set("RF_SLOW_MO", "0:00:01") is False

    assert config_file.read_text(encoding="utf-8") == unreadable_content
    assert instance.get("RF_SLOW_MO") is None


def test_save_config_persists_valid_values(tmp_path: Path) -> None:
    """Une configuration sérialisable remplace correctement le fichier JSON."""
    config_file = tmp_path / "variables_config.json"
    instance = _isolated_config(config_file)
    instance._config_vars = {"RF_BROWSER": "webkit", "API_PORT": "5002"}

    assert instance._save_config() is True
    assert json.loads(config_file.read_text(encoding="utf-8")) == instance.get_all()


def test_failed_set_restores_memory_and_preserves_disk(tmp_path: Path) -> None:
    """Une valeur non sérialisable ne crée aucune divergence mémoire-disque."""
    config_file = tmp_path / "variables_config.json"
    instance = _isolated_config(config_file)
    instance._config_vars = {"stable": "valeur"}
    assert instance._save_config() is True

    assert instance.set("invalide", object()) is False

    assert instance.get_all() == {"stable": "valeur"}
    assert json.loads(config_file.read_text(encoding="utf-8")) == {"stable": "valeur"}


def test_failed_delete_restores_removed_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une suppression non sauvegardée rétablit la valeur en mémoire."""
    config_file = tmp_path / "variables_config.json"
    instance = _isolated_config(config_file)
    instance._config_vars = {"clé": "valeur"}
    monkeypatch.setattr(instance, "_save_config", Mock(return_value=False))

    assert instance.delete("clé") is False
    assert instance.get("clé") == "valeur"


def test_string_representation_masks_sensitive_values(tmp_path: Path) -> None:
    """La vue textuelle n'expose ni mot de passe, ni jeton, ni clé d'API."""
    instance = _isolated_config(tmp_path / "variables_config.json")
    instance._config_vars = {
        "RF_PASSWORD": "mot-de-passe",  # pragma: allowlist secret
        "ACCESS_TOKEN": "jeton",
        "API_KEY": "clé",  # pragma: allowlist secret
        "RF_BROWSER": "chromium",
    }

    rendered = str(instance)

    assert "mot-de-passe" not in rendered
    assert "jeton" not in rendered
    assert "clé\n" not in rendered
    assert rendered.count(MASKED_CONFIG_VALUE) == 3
    assert "RF_BROWSER: chromium" in rendered


def test_public_config_keeps_login_visible_and_masks_secrets(tmp_path: Path) -> None:
    """La vue HTTP conserve le login mais masque mot de passe et token."""
    instance = _isolated_config(tmp_path / "variables_config.json")
    instance._config_vars = {
        "RF_LOGIN": "utilisateur",
        "RF_PASSWORD": "mot-de-passe",  # pragma: allowlist secret
        "ACCESS_TOKEN": "jeton",
    }

    assert instance.get_public_all() == {
        "RF_LOGIN": "utilisateur",
        "RF_PASSWORD": MASKED_CONFIG_VALUE,
        "ACCESS_TOKEN": MASKED_CONFIG_VALUE,
    }
"""Tests unitaires du référentiel des environnements."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import environments

_YAML = """
recette:
  label: Recette
  base: https://recette.client.fr/app
  tier: recette
  modules:
    travaux: /travaux
    cartographie: https://gis-recette.client.fr/carto
  accounts:
    STANDARD:
      username: agent_test
      password_ref: RECETTE_AGENT
preprod:
  base: https://preprod.client.fr/app/
  modules:
    travaux: travaux
"""


@pytest.fixture
def referentiel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pointe le module sur un référentiel de test, sans secret configuré."""
    fichier = tmp_path / "environments.yaml"
    fichier.write_text(_YAML, encoding="utf-8")
    monkeypatch.setattr(environments, "ENVIRONMENTS_FILE", fichier)
    monkeypatch.setattr(environments, "config", SimpleNamespace(get=lambda key, default=None: default))
    return fichier


def test_url_composee_depuis_la_base_de_l_environnement(referentiel: Path) -> None:
    """Le même module vise un host différent selon l'environnement."""
    assert environments.resolve_module_url("recette", "travaux") == (
        "https://recette.client.fr/app/travaux"
    )
    assert environments.resolve_module_url("preprod", "travaux") == (
        "https://preprod.client.fr/app/travaux"
    )


def test_chemin_absolu_remplace_la_base(referentiel: Path) -> None:
    """Un module hébergé sur son propre host garde son URL complète."""
    assert environments.resolve_module_url("recette", "cartographie") == (
        "https://gis-recette.client.fr/carto"
    )


def test_module_inconnu_echoue_sans_repli(referentiel: Path) -> None:
    """Sans erreur, un test viserait une page arbitraire et passerait à tort."""
    with pytest.raises(ValueError, match="Module 'inexistant' non déclaré"):
        environments.resolve_module_url("recette", "inexistant")


def test_le_niveau_d_installation_est_publie(referentiel: Path) -> None:
    """L'interface colore la cible d'après ce niveau : il doit sortir du référentiel.

    Un environnement muet retombe sur `demo` : le niveau ne se devine pas depuis
    l'identifiant, sinon une prod mal nommée passerait pour anodine.
    """
    declares = {env["id"]: env["tier"] for env in environments.list_environments()}

    assert declares == {"recette": "recette", "preprod": "demo"}


def test_un_niveau_inconnu_est_refuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Une faute de frappe sur 'prod' désarmerait la garde sans que personne ne le voie."""
    fichier = tmp_path / "environments.yaml"
    fichier.write_text(
        "prod:\n  base: https://client.fr\n  tier: production\n", encoding="utf-8"
    )
    monkeypatch.setattr(environments, "ENVIRONMENTS_FILE", fichier)

    with pytest.raises(ValueError, match="'tier'"):
        environments.list_environments()


def test_environnement_inconnu_est_refuse(referentiel: Path) -> None:
    """get_environment fait office de liste blanche pour les entrées d'API."""
    assert environments.get_environment("prod_client") is None
    with pytest.raises(ValueError, match="Environnement 'prod_client' inconnu"):
        environments.resolve_module_url("prod_client", "travaux")


def test_compte_resolu_avec_le_secret_configure(
    referentiel: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le mot de passe vient de variables_config.json, pas du référentiel versionné."""
    monkeypatch.setattr(
        environments,
        "config",
        SimpleNamespace(get=lambda key, default=None: "motdepasse" if key == "RF_SECRET_RECETTE_AGENT" else default),
    )

    assert environments.resolve_account("recette", "STANDARD") == {
        "username": "agent_test",
        "password": "motdepasse",  # pragma: allowlist secret
    }


def test_secret_manquant_indique_la_cle_sans_divulguer_de_valeur(referentiel: Path) -> None:
    """Le message doit guider la configuration sans exposer de secret."""
    with pytest.raises(ValueError) as erreur:
        environments.resolve_account("recette", "STANDARD")

    assert "RF_SECRET_RECETTE_AGENT" in str(erreur.value)


def test_profil_inconnu_echoue(referentiel: Path) -> None:
    """Un profil non déclaré ne doit pas retomber sur un compte par défaut."""
    with pytest.raises(ValueError, match="Profil 'ADMIN' non déclaré"):
        environments.resolve_account("recette", "ADMIN")


def test_mot_de_passe_en_clair_dans_le_referentiel_est_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le référentiel est versionné : un secret y serait publié dans git."""
    fichier = tmp_path / "environments.yaml"
    fichier.write_text(
        "recette:\n"
        "  base: https://recette.client.fr\n"
        "  accounts:\n"
        "    STANDARD:\n"
        "      username: agent\n"
        "      password: motdepasse\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    monkeypatch.setattr(environments, "ENVIRONMENTS_FILE", fichier)

    with pytest.raises(ValueError, match="mot de passe en clair"):
        environments.get_environment("recette")


def test_base_non_http_est_refusee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Une base file:// ou vide ferait viser une cible imprévue."""
    fichier = tmp_path / "environments.yaml"
    fichier.write_text("recette:\n  base: file:///etc/passwd\n", encoding="utf-8")
    monkeypatch.setattr(environments, "ENVIRONMENTS_FILE", fichier)

    with pytest.raises(ValueError, match="http:// ou https://"):
        environments.get_environment("recette")


def test_environnement_actif_suit_la_configuration(
    referentiel: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RF_ENVIRONMENT pilote la cible ; une valeur inconnue ne bloque pas le run."""
    monkeypatch.setattr(
        environments, "config", SimpleNamespace(get=lambda key, default=None: "preprod")
    )
    assert environments.active_environment() == "preprod"

    monkeypatch.setattr(
        environments, "config", SimpleNamespace(get=lambda key, default=None: "disparu")
    )
    assert environments.active_environment() == "recette"


def test_referentiel_du_depot_est_valide() -> None:
    """Garde-fou : le fichier livré doit rester lisible et complet."""
    declares = environments.list_environments()

    assert declares, "config/environments.yaml ne déclare aucun environnement"
    for environnement in declares:
        assert environnement["base"].startswith(("http://", "https://"))
        assert environnement["modules"]

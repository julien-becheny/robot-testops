"""Tests de l'index des tests : contenu servi à la place d'une exploration, et fraîcheur."""

import json
from pathlib import Path

from services.coverage import tests_index

_REFERENTIEL = """
module: demo
label: Module de demonstration
plateformes: [web]
ecrans:
  - id: demo.panier
    label: Panier
    type: page
fonctionnalites:
  - id: demo.commande.finalisation
    label: Finaliser une commande
    criticite: critique
"""

_RESOURCE = """*** Keywords ***
Ouvrir Le Panier
  Aller Au Panier

Aller Au Panier
  Wait For Screen  demo.panier  css=#panier
"""

_SUITE = """*** Settings ***
Test Tags  demo

*** Test Cases ***
Test Achat
  [Documentation]  Achete un article et verifie la commande.
  [Tags]  feat:demo.commande.finalisation
  Ouvrir Le Panier
  Valider La Commande
"""


def _build_repo(root: Path, suite: str = _SUITE) -> None:
    (root / "functional_map").mkdir()
    (root / "functional_map" / "demo.yaml").write_text(_REFERENTIEL, encoding="utf-8")
    (root / "test_suites").mkdir()
    (root / "test_suites" / "demo.robot").write_text(suite, encoding="utf-8")
    (root / "resources").mkdir()
    (root / "resources" / "kw_demo.resource").write_text(_RESOURCE, encoding="utf-8")


def _build_index(root: Path) -> dict:
    return tests_index.build_index(
        root / "test_suites", root / "resources", root / "functional_map"
    )


def _is_stale(root: Path, index: dict) -> bool:
    return tests_index.is_stale(
        index, root / "test_suites", root / "resources", root / "functional_map"
    )


def test_index_decrit_le_test_sans_relire_la_suite(tmp_path: Path) -> None:
    """L'entrée porte de quoi répondre : où, quels tags, quoi vérifié, quoi traversé."""
    _build_repo(tmp_path)

    index = _build_index(tmp_path)

    assert len(index["tests"]) == 1
    entry = index["tests"][0]
    assert entry["nom"] == "Test Achat"
    assert entry["fichier"].endswith("demo.robot")
    assert entry["ligne"] == 5
    assert entry["doc"] == "Achete un article et verifie la commande."
    assert "demo" in entry["tags"]
    assert entry["feat"] == ["demo.commande.finalisation"]
    assert entry["ecrans"] == ["demo.panier"]


def test_les_keywords_restent_lisibles_et_dans_l_ordre_d_appel(tmp_path: Path) -> None:
    """Le rapport de couverture normalise les appels ; l'index garde l'orthographe écrite.

    Un nom normalisé (`ouvrirlepanier`) ne se recherche pas et ne se lit pas.
    """
    _build_repo(tmp_path)

    entry = _build_index(tmp_path)["tests"][0]

    assert entry["keywords"] == ["Ouvrir Le Panier", "Valider La Commande"]


def test_le_champ_texte_reprend_les_libelles_du_referentiel(tmp_path: Path) -> None:
    """Le champ prévu pour une recherche par le sens parle français, pas identifiants."""
    _build_repo(tmp_path)

    texte = _build_index(tmp_path)["tests"][0]["texte"]

    assert "Test Achat" in texte
    assert "Achete un article" in texte
    assert "Finaliser une commande" in texte  # libellé de la fonctionnalité
    assert "Panier" in texte  # libellé de l'écran traversé
    assert "demo.commande.finalisation" not in texte


def test_un_index_frais_n_est_pas_signale_perime(tmp_path: Path) -> None:
    """Sans changement de source, l'index reste valable : pas de régénération inutile."""
    _build_repo(tmp_path)

    index = _build_index(tmp_path)

    assert _is_stale(tmp_path, index) is False


def test_une_suite_modifiee_perime_l_index(tmp_path: Path) -> None:
    """Un index périmé et muet serait pire que pas d'index : il doit se dénoncer."""
    _build_repo(tmp_path)
    index = _build_index(tmp_path)

    (tmp_path / "test_suites" / "demo.robot").write_text(
        _SUITE + "\nTest Retour\n  Ouvrir Le Panier\n", encoding="utf-8"
    )

    assert _is_stale(tmp_path, index) is True


def test_un_fichier_ajoute_perime_l_index(tmp_path: Path) -> None:
    """La péremption doit voir l'ajout, pas seulement la modification d'un fichier connu."""
    _build_repo(tmp_path)
    index = _build_index(tmp_path)

    (tmp_path / "test_suites" / "autre.robot").write_text(
        "*** Test Cases ***\nTest Autre\n  No Operation\n", encoding="utf-8"
    )

    assert _is_stale(tmp_path, index) is True


def test_l_empreinte_ignore_la_date_de_modification(tmp_path: Path) -> None:
    """Une copie ou un clone changent les dates sans changer le contenu : rien n'est périmé.

    L'empreinte porte sur le contenu - une date aurait fait crier l'outil après chaque
    `git clone`, et on aurait appris à ignorer l'alerte.
    """
    _build_repo(tmp_path)
    index = _build_index(tmp_path)
    suite = tmp_path / "test_suites" / "demo.robot"

    suite.write_text(suite.read_text(encoding="utf-8"), encoding="utf-8")

    assert _is_stale(tmp_path, index) is False


def test_un_index_produit_par_un_format_anterieur_est_perime(tmp_path: Path) -> None:
    """Non-régression : l'empreinte suit les sources, pas la forme de l'artefact.

    Observé en réel - en sortant les keywords de l'index, les sources n'avaient pas bougé :
    l'ancien fichier restait en place, annoncé « déjà à jour », avec une section que le
    générateur ne produisait plus.
    """
    _build_repo(tmp_path)
    index = _build_index(tmp_path)

    index["format"] = tests_index.FORMAT - 1

    assert _is_stale(tmp_path, index) is True


def test_index_absent_ou_illisible_est_traite_comme_absent(tmp_path: Path) -> None:
    """Une écriture interrompue ne doit pas faire planter le lecteur, juste régénérer."""
    manquant = tmp_path / "jamais_ecrit.json"
    tronque = tmp_path / "tronque.json"
    tronque.write_text('{"tests": [', encoding="utf-8")

    assert tests_index.load_index(manquant) is None
    assert tests_index.load_index(tronque) is None


def test_ecriture_puis_relecture_conservent_l_index(tmp_path: Path) -> None:
    """Le fichier écrit est du JSON lisible, en UTF-8 (accents des libellés)."""
    _build_repo(tmp_path)
    index = _build_index(tmp_path)
    cible = tmp_path / "results" / "tests_index.json"

    tests_index.write_index(index, cible)

    assert json.loads(cible.read_text(encoding="utf-8")) == index
    assert tests_index.load_index(cible) == index


def test_refresh_ne_regenere_pas_un_index_deja_a_jour(tmp_path: Path) -> None:
    """Le hook de commit s'appuie dessus : sans changement, l'appel doit être quasi gratuit."""
    cible = tmp_path / "tests_index.json"

    _, premier, regenere = tests_index.refresh_index(cible)
    _, second, regenere_bis = tests_index.refresh_index(cible)

    assert regenere is True
    assert regenere_bis is False
    assert second["genere_le"] == premier["genere_le"]

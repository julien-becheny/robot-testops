"""Tests du catalogue des briques : contrat des keywords, forme des données, portée."""

from pathlib import Path

from services.coverage import catalogue

_RESOURCE = """*** Keywords ***
Ouvrir Le Panier
  [Documentation]  Ouvre le panier depuis n'importe quelle page.
  ...  Detail qui n'a pas sa place dans un catalogue.
  [Arguments]  ${Profil}=STANDARD  ${Timeout}=10
  Aller Au Panier
"""

_SUITE = """*** Test Cases ***
Un Test
  Ouvrir Le Panier


*** Keywords ***
Helper Local
  [Documentation]  Utilisable uniquement dans cette suite.
  No Operation
"""

_DONNEES = """
TD_DEMO:
  CLIENT:
    NOM: "Dupont"
    PRENOM: "Jean"
  PASSAGES:
    - DEBUT: "01/01/2026"
      FIN: "31/01/2026"
"""

_OBJETS = """
TO_PANIER:
  BTN_VALIDER: "css=#valider"
  LBL_TOTAL: "css=.total"
"""


def _build_repo(root: Path) -> None:
    for nom in ("test_suites", "resources", "test_data", "test_objects"):
        (root / nom).mkdir(exist_ok=True)
    (root / "test_suites" / "demo.robot").write_text(_SUITE, encoding="utf-8")
    (root / "resources" / "kw_demo.resource").write_text(_RESOURCE, encoding="utf-8")
    (root / "test_data" / "td_demo.yml").write_text(_DONNEES, encoding="utf-8")
    (root / "test_objects" / "to_panier.yml").write_text(_OBJETS, encoding="utf-8")


def _build(root: Path) -> dict:
    return catalogue.build_catalogue(
        root / "test_suites", root / "resources", root / "test_data", root / "test_objects"
    )


def _keywords(root: Path) -> dict:
    return {entree["nom"]: entree for entree in _build(root)["keywords"]}


def test_le_contrat_d_appel_est_complet(tmp_path: Path) -> None:
    """Nom, arguments, emplacement : de quoi écrire l'appel sans ouvrir le fichier."""
    _build_repo(tmp_path)

    keyword = _keywords(tmp_path)["Ouvrir Le Panier"]

    assert keyword["args"] == ["${Profil}=STANDARD", "${Timeout}=10"]
    assert keyword["fichier"].endswith("kw_demo.resource")
    assert keyword["ligne"] == 2


def test_la_documentation_est_reduite_a_son_resume(tmp_path: Path) -> None:
    """Par convention Robot, la première ligne résume ; le reste gonflerait le catalogue."""
    _build_repo(tmp_path)

    keyword = _keywords(tmp_path)["Ouvrir Le Panier"]

    assert keyword["doc"] == "Ouvre le panier depuis n'importe quelle page."


def test_la_portee_distingue_un_keyword_partage_d_un_keyword_local(tmp_path: Path) -> None:
    """Un keyword défini dans un `.robot` n'est visible que là : le proposer ailleurs casse."""
    _build_repo(tmp_path)

    keywords = _keywords(tmp_path)

    assert keywords["Ouvrir Le Panier"]["portee"] == catalogue.PARTAGEE
    assert keywords["Helper Local"]["portee"] == catalogue.SUITE


def test_le_catalogue_ne_contient_pas_le_corps_des_keywords(tmp_path: Path) -> None:
    """C'est le parti pris de taille : le contrat, jamais l'implémentation."""
    _build_repo(tmp_path)

    keyword = _keywords(tmp_path)["Ouvrir Le Panier"]

    assert "Aller Au Panier" not in str(keyword)


def test_les_donnees_exposent_leur_forme_pas_leurs_valeurs(tmp_path: Path) -> None:
    """Connaître les chemins suffit pour écrire ; recopier les valeurs n'apprend rien."""
    _build_repo(tmp_path)

    donnees = _build(tmp_path)["donnees"][0]

    assert donnees["variable"] == "TD_DEMO"
    assert "CLIENT.NOM" in donnees["cles"]
    assert "Dupont" not in str(donnees)


def test_une_liste_est_reduite_a_son_premier_element(tmp_path: Path) -> None:
    """Trois cents passages ont la même forme : un suffit, marqué `[]`."""
    _build_repo(tmp_path)

    cles = _build(tmp_path)["donnees"][0]["cles"]

    assert "PASSAGES[].DEBUT" in cles
    assert "PASSAGES[].FIN" in cles


def test_les_objets_d_interface_listent_leurs_cles(tmp_path: Path) -> None:
    """Écrire `${TO_PANIER}[BTN_VALIDER]` suppose de savoir que cette clé existe."""
    _build_repo(tmp_path)

    objets = _build(tmp_path)["objets"][0]

    assert objets["variable"] == "TO_PANIER"
    assert objets["cles"] == ["BTN_VALIDER", "LBL_TOTAL"]


def test_une_source_modifiee_perime_le_catalogue(tmp_path: Path) -> None:
    """Même garde-fou que l'index : une photo doit dire qu'elle a vieilli."""
    _build_repo(tmp_path)
    construit = _build(tmp_path)
    dossiers = (
        tmp_path / "test_suites",
        tmp_path / "resources",
        tmp_path / "test_data",
        tmp_path / "test_objects",
    )

    assert catalogue.is_stale(construit, *dossiers) is False

    (tmp_path / "test_objects" / "to_panier.yml").write_text(
        _OBJETS + '  BTN_VIDER: "css=#vider"\n', encoding="utf-8"
    )

    assert catalogue.is_stale(construit, *dossiers) is True


def test_catalogue_absent_ou_illisible_est_traite_comme_absent(tmp_path: Path) -> None:
    """Une écriture interrompue ne fait pas planter le lecteur, elle déclenche un rebuild."""
    tronque = tmp_path / "tronque.json"
    tronque.write_text('{"keywords": [', encoding="utf-8")

    assert catalogue.load_catalogue(tmp_path / "absent.json") is None
    assert catalogue.load_catalogue(tronque) is None

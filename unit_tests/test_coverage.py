"""Tests de l'outil de couverture fonctionnelle : référentiel, marqueurs, verdicts."""

from pathlib import Path

from services.coverage import analyzer as coverage
from services.coverage import html_report

_REFERENTIEL = """
module: demo
label: Module de demonstration
plateformes: [web]
ecrans:
  - id: demo.panier
    label: Panier
    type: page
  - id: demo.jamais_atteint
    label: Popup orpheline
    type: popup
fonctionnalites:
  - id: demo.commande.finalisation
    label: Finaliser une commande
    criticite: critique
  - id: demo.commande.annulation
    label: Annuler une commande
    criticite: majeure
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
  [Tags]  feat:demo.commande.finalisation
  Ouvrir Le Panier
"""


def _build_repo(root: Path, referentiel: str = _REFERENTIEL, suite: str = _SUITE) -> None:
    (root / "functional_map").mkdir()
    (root / "functional_map" / "demo.yaml").write_text(referentiel, encoding="utf-8")
    (root / "test_suites").mkdir()
    (root / "test_suites" / "demo.robot").write_text(suite, encoding="utf-8")
    (root / "resources").mkdir()
    (root / "resources" / "kw_demo.resource").write_text(_RESOURCE, encoding="utf-8")


def _analyse(root: Path) -> tuple[coverage.Referentiel, list, dict]:
    referentiel = coverage.load_referentiel(root / "functional_map")
    tests, keywords, _ = coverage.collect_code(root / "test_suites", root / "resources")
    return referentiel, tests, keywords


def test_referentiel_valide_est_charge_sans_erreur(tmp_path: Path) -> None:
    """Un référentiel conforme fournit ses écrans et ses fonctionnalités."""
    _build_repo(tmp_path)

    referentiel = coverage.load_referentiel(tmp_path / "functional_map")

    assert not referentiel.findings
    assert set(referentiel.ecrans) == {"demo.panier", "demo.jamais_atteint"}
    assert referentiel.fonctionnalites["demo.commande.finalisation"].criticite == "critique"


def test_identifiant_hors_module_est_refuse(tmp_path: Path) -> None:
    """Un identifiant qui ne porte pas le préfixe du module casse l'unicité : il est rejeté."""
    referentiel_invalide = _REFERENTIEL.replace("id: demo.panier", "id: panier")
    _build_repo(tmp_path, referentiel=referentiel_invalide)

    referentiel = coverage.load_referentiel(tmp_path / "functional_map")

    assert [f.code for f in referentiel.findings] == ["MAP_INVALIDE"]
    assert "demo." in referentiel.findings[0].message


def test_identifiant_en_double_est_refuse(tmp_path: Path) -> None:
    """Deux entrées ne peuvent pas partager le même identifiant."""
    referentiel_double = _REFERENTIEL.replace("id: demo.jamais_atteint", "id: demo.panier")
    _build_repo(tmp_path, referentiel=referentiel_double)

    referentiel = coverage.load_referentiel(tmp_path / "functional_map")

    assert any("double" in f.message for f in referentiel.findings)


def test_ecran_marque_par_un_keyword_appele_indirectement_est_couvert(tmp_path: Path) -> None:
    """La couverture d'écran suit la chaîne d'appels : test -> keyword -> keyword -> marqueur."""
    _build_repo(tmp_path)
    referentiel, tests, keywords = _analyse(tmp_path)

    rapport = coverage.build_report(referentiel, tests, keywords)
    ecrans = {e["id"]: e for e in rapport["modules"][0]["ecrans"]}

    assert ecrans["demo.panier"]["statut"] == "couvert"
    assert ecrans["demo.panier"]["atteint_par"] == ["Test Achat"]


def test_entree_sans_test_est_signalee_non_couverte(tmp_path: Path) -> None:
    """Le référentiel sert de dénominateur : ce qu'aucun test ne touche apparaît en non couvert."""
    _build_repo(tmp_path)
    referentiel, tests, keywords = _analyse(tmp_path)

    rapport = coverage.build_report(referentiel, tests, keywords)
    module = rapport["modules"][0]
    ecrans = {e["id"]: e["statut"] for e in module["ecrans"]}
    features = {f["id"]: f["statut"] for f in module["fonctionnalites"]}

    assert ecrans["demo.jamais_atteint"] == "non_couvert"
    assert features["demo.commande.annulation"] == "non_couvert"
    assert rapport["perimetre"] == {"modules": 1, "ecrans": 2, "fonctionnalites": 2}


def test_rapport_n_expose_aucun_taux_de_couverture(tmp_path: Path) -> None:
    """Pas de score agrégé : il rapporterait les tests à un référentiel qu'on sait incomplet."""
    _build_repo(tmp_path)
    referentiel, tests, keywords = _analyse(tmp_path)

    rapport = coverage.build_report(referentiel, tests, keywords)

    assert "totaux" not in rapport
    assert set(rapport["perimetre"]) == {"modules", "ecrans", "fonctionnalites"}


def test_ecran_inconnu_est_une_erreur_avec_suggestion(tmp_path: Path) -> None:
    """Une faute de frappe sur un identifiant d'écran est bloquée, pas ignorée."""
    _build_repo(tmp_path)
    resource = tmp_path / "resources" / "kw_demo.resource"
    resource.write_text(_RESOURCE.replace("demo.panier", "demo.panie"), encoding="utf-8")
    referentiel, tests, keywords = _analyse(tmp_path)

    findings = coverage.check_references(referentiel, tests, keywords)

    assert [f.code for f in findings] == ["ECRAN_INCONNU"]
    assert "proche de : demo.panier" in findings[0].message


def test_tag_de_fonctionnalite_inconnu_est_une_erreur(tmp_path: Path) -> None:
    """Un tag `feat:` qui ne correspond à rien dans le référentiel est refusé."""
    suite = _SUITE.replace("feat:demo.commande.finalisation", "feat:demo.commande.inventee")
    _build_repo(tmp_path, suite=suite)
    referentiel, tests, keywords = _analyse(tmp_path)

    findings = coverage.check_references(referentiel, tests, keywords)

    assert [f.code for f in findings] == ["FEAT_INCONNU"]


def test_appel_dynamique_est_signale_au_lieu_d_etre_ignore(tmp_path: Path) -> None:
    """Un chemin invisible pour l'analyse statique est déclaré, jamais passé sous silence."""
    suite = _SUITE.replace("  Ouvrir Le Panier\n", "  Run Keyword  Ouvrir Le Panier\n")
    _build_repo(tmp_path, suite=suite)

    _, _, warnings = coverage.collect_code(tmp_path / "test_suites", tmp_path / "resources")

    assert [w.code for w in warnings] == ["APPEL_DYNAMIQUE"]


def test_tag_de_suite_couvre_tous_ses_tests(tmp_path: Path) -> None:
    """Un `feat:` declare en `Test Tags` vaut pour chaque test de la suite."""
    suite = _SUITE.replace("Test Tags  demo", "Test Tags  demo  feat:demo.commande.annulation")
    _build_repo(tmp_path, suite=suite)
    referentiel, tests, keywords = _analyse(tmp_path)

    rapport = coverage.build_report(referentiel, tests, keywords)
    features = {f["id"]: f["verifiee_par"] for f in rapport["modules"][0]["fonctionnalites"]}

    assert features["demo.commande.annulation"] == ["Test Achat"]


def test_un_keyword_homonyme_se_resout_dans_les_ressources_importees(tmp_path: Path) -> None:
    """Deux modules définissent `Se Connecter` : la suite n'atteint que l'écran du sien."""
    _build_repo(tmp_path)
    resources = tmp_path / "resources"
    (resources / "kw_a.resource").write_text(
        "*** Keywords ***\nSe Connecter\n  Wait For Screen  demo.jamais_atteint  css=#a\n",
        encoding="utf-8",
    )
    (resources / "kw_b.resource").write_text(
        "*** Settings ***\nResource  ${CURDIR}/kw_demo.resource\n\n"
        "*** Keywords ***\nSe Connecter\n  Aller Au Panier\n",
        encoding="utf-8",
    )
    (tmp_path / "test_suites" / "demo.robot").write_text(
        "*** Settings ***\nResource  ../resources/kw_b.resource\n\n"
        "*** Test Cases ***\nTest Connexion\n  Se Connecter\n",
        encoding="utf-8",
    )
    referentiel, tests, keywords = _analyse(tmp_path)

    rapport = coverage.build_report(referentiel, tests, keywords)
    ecrans = {e["id"]: e["atteint_par"] for e in rapport["modules"][0]["ecrans"]}

    assert ecrans["demo.panier"] == ["Test Connexion"]
    assert ecrans["demo.jamais_atteint"] == []


def test_chaque_definition_homonyme_est_verifiee(tmp_path: Path) -> None:
    """Un écran inconnu dans une seconde définition du même keyword n'échappe pas au contrôle."""
    _build_repo(tmp_path)
    (tmp_path / "resources" / "kw_z.resource").write_text(
        "*** Keywords ***\nAller Au Panier\n  Wait For Screen  demo.inconnu  css=#z\n",
        encoding="utf-8",
    )
    referentiel, tests, keywords = _analyse(tmp_path)

    findings = coverage.check_references(referentiel, tests, keywords)

    assert [f.code for f in findings] == ["ECRAN_INCONNU"]


def test_rapport_html_est_autonome(tmp_path: Path) -> None:
    """Le fichier partagé doit s'ouvrir hors ligne : aucune ressource externe."""
    _build_repo(tmp_path)
    referentiel, tests, keywords = _analyse(tmp_path)

    page = html_report.render_html(coverage.build_report(referentiel, tests, keywords))

    assert "Popup orpheline" in page
    assert "src=\"http" not in page
    assert "href=\"http" not in page


def test_rapport_html_neutralise_le_contenu_injecte(tmp_path: Path) -> None:
    """Un libellé contenant du balisage ne doit pas pouvoir fermer le script de la page."""
    piege = _REFERENTIEL.replace("label: Panier", 'label: "Panier </script><script>x=1</script>"')
    _build_repo(tmp_path, referentiel=piege)
    referentiel, tests, keywords = _analyse(tmp_path)

    page = html_report.render_html(coverage.build_report(referentiel, tests, keywords))

    assert "</script><script>" not in page
    assert "\\u003c/script" in page

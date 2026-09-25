"""Tests du diagnostic de locator - ce qu'il dit, et quand il se tait."""

from robot_listeners.locator_diagnostic import classer, locator_attendu, rapport


def test_le_premier_argument_positionnel_est_le_locator() -> None:
    """La sonde a besoin de la forme écrite dans le test, variable comprise."""
    assert locator_attendu("Click", ["${TO_LOGIN}[BTN_LOGIN]"]) == "${TO_LOGIN}[BTN_LOGIN]"


def test_un_keyword_qui_ne_vise_pas_d_element_est_ignore() -> None:
    """`New Page` prend une URL : la sonder produirait un diagnostic sur une adresse."""
    assert locator_attendu("New Page", ["https://exemple.test"]) is None


def test_un_locator_nomme_est_reconnu() -> None:
    """`Click  selector=…` désigne le même élément que la forme positionnelle."""
    assert locator_attendu("Click", ["selector=input#login"]) == "input#login"


def test_un_keyword_sans_argument_ne_declenche_rien() -> None:
    """Cas limite : la liste d'arguments peut être vide."""
    assert locator_attendu("Click", []) is None


def test_le_candidat_le_plus_proche_arrive_en_tete() -> None:
    """Cas vécu du spike : `input#login-btn` doit remonter `#login-button`, pas un champ voisin."""
    candidats = [
        {"tag": "input", "id": "user-name", "testid": "username", "nom": "Username"},
        {"tag": "input", "id": "login-button", "testid": "login-button", "nom": "Login"},
        {"tag": "input", "id": "password", "testid": "password", "nom": "Password"},
    ]

    classes = classer("input#login-btn", candidats)

    assert classes[0][1]["id"] == "login-button"
    assert classes[0][0] > classes[1][0]


def test_le_classement_est_tronque() -> None:
    """Un diagnostic qui liste la page entière ne diagnostique plus rien."""
    candidats = [{"tag": "a", "id": f"lien-{n}", "testid": "", "nom": ""} for n in range(30)]

    assert len(classer("input#login", candidats, limite=3)) == 3


def test_le_rapport_dit_qu_aucune_reparation_n_a_lieu() -> None:
    """Le lecteur doit savoir que le vert n'a pas été acheté : le test reste rouge."""
    texte = rapport("Browser.Click", "${TO}[BTN]", "input#x", 0, [])

    assert "Aucune réparation n'est tentée" in texte
    assert "ne désigne plus rien" in texte


def test_le_rapport_distingue_l_ancrage_ambigu() -> None:
    """Plusieurs éléments visés, c'est la violation du mode strict qui arrive."""
    texte = rapport("Browser.Click", "${TO}[BTN]", ".ligne", 4, [])

    assert "4 éléments correspondent" in texte

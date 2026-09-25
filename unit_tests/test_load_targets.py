"""Coherence de la liste blanche des cibles de charge avec les scenarios des deux moteurs."""

from pathlib import Path

from services.load.targets import LOAD_TARGETS, get_target, list_targets

# Le locustfile est lu en texte, jamais importe : `import locust` declenche
# monkey.patch_all(), qui remplacerait la bibliotheque standard de tout le
# processus pytest.
_LOAD = Path(__file__).resolve().parent.parent / "services" / "load"
LOCUSTFILE = _LOAD / "locustfile_testops.py"
K6_SCENARIO = _LOAD / "k6_scenario.js"


def _dispatch_source() -> str:
    """Retourne le corps du dictionnaire `_SCENARIO` du locustfile."""
    source = LOCUSTFILE.read_text(encoding="utf-8")
    return source.split("_SCENARIO = {", 1)[1].split("}", 1)[0]


def _k6_dispatch_source() -> str:
    """Retourne le corps du dictionnaire `SCENARIO` du scenario k6."""
    source = K6_SCENARIO.read_text(encoding="utf-8")
    return source.split("const SCENARIO = {", 1)[1].split("};", 1)[0]


def test_every_declared_target_has_a_scenario() -> None:
    """Une cible sans scenario retombe silencieusement sur celui par defaut.

    Le run se deroule alors entierement, mais interroge des routes que la cible
    n'expose pas : des centaines d'erreurs, sans rien qui en nomme la cause.
    """
    dispatch = _dispatch_source()
    orphelines = [tid for tid in LOAD_TARGETS if f'"{tid}"' not in dispatch]

    assert not orphelines, (
        f"Cibles declarees sans scenario branche : {orphelines}. "
        "Ajouter l'entree correspondante dans _SCENARIO du locustfile."
    )


def test_every_declared_target_has_a_k6_scenario() -> None:
    """Les deux moteurs ont leur propre dispatch : n'en verifier qu'un rassure a tort.

    Cas rencontre : les cibles du banc etaient branchees cote Locust seulement.
    Un test a debit impose retombait sur le scenario par defaut et interrogeait
    `/search` sur un serveur statique.
    """
    dispatch = _k6_dispatch_source()
    orphelines = [tid for tid in LOAD_TARGETS if f"{tid}:" not in dispatch]

    assert not orphelines, (
        f"Cibles declarees sans scenario k6 : {orphelines}. "
        "Ajouter l'entree correspondante dans SCENARIO de k6_scenario.js."
    )


def test_an_unknown_target_is_refused() -> None:
    """La liste blanche est ce qui interdit d'envoyer de la charge n'importe ou."""
    assert get_target("site-d-un-tiers") is None


def test_a_stress_is_not_cut_short_at_the_first_threshold_breach() -> None:
    """Un stress arrete au premier depassement du seuil n'est qu'un capacity.

    Il doit poursuivre la montee pour montrer ce que le capacity ne peut pas dire :
    la degradation est-elle progressive ou un effondrement, le debit s'ecroule-t-il,
    et le service revient-il quand la charge retombe.
    """
    source = LOCUSTFILE.read_text(encoding="utf-8")
    tick = source.split("def tick(self):", 1)[1].split("\n\n", 1)[0]

    assert 'STOP_ON_BREACH = TEST_TYPE != "stress"' in source
    assert "STOP_ON_BREACH" in tick, (
        "La shape coupe le test des qu'un point de rupture est pose, quel que soit "
        "le type : le stress ne verrait jamais la surcharge."
    )


def test_listed_targets_expose_what_the_interface_needs() -> None:
    attendus = {"id", "label", "description", "base_url"}
    cibles = list_targets()

    assert cibles, "La liste blanche ne doit jamais etre vide."
    for cible in cibles:
        assert set(cible) == attendus
        assert cible["base_url"].startswith(("http://", "https://"))

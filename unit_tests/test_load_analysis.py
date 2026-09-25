"""Tests unitaires du moteur de regles d'analyse des tests de charge."""

import os

from services.load import analysis, runner_common


def _capacity_result(**overrides) -> dict:
    """Resultat d'un run de capacite au vert (aucune rupture, aucune erreur)."""
    result = {
        "test_type": "capacity",
        "min_ms": 101,
        "p50_ms": 190,
        "p95_ms": 390,
        "p99_ms": 510,
        "max_ms": 3916.2,
        "ttfb_p95_ms": 396.5,
        "error_rate": 0,
        "checks_rate": 1,
        "vus_max": 600,
        "vus_target_max": 600,
        "vus_deficit_pct": 0.0,
        "seuil_p95_ms": 800,
        "breach": None,
        "thresholds_ok": True,
        "injector_cpu_max": 40.0,
        "injector_cpu_warning": False,
    }
    result.update(overrides)
    return result


def _titles(findings: list) -> list:
    return [f["title"] for f in findings]


def test_saturated_injector_is_reported_first_as_critical() -> None:
    """Un injecteur sature produit un constat critique en tete de l'analyse."""
    result = _capacity_result(injector_cpu_max=98.0, injector_cpu_warning=True)

    findings = analysis.analyze(result, {"p95_ms": 800}, "capacity")

    assert findings[0]["level"] == "crit"
    assert "injecteur saturé" in findings[0]["title"]
    assert "98 %" in findings[0]["title"]


def test_saturated_injector_invalidates_capacity_conclusion() -> None:
    """La capacite n'est plus annoncee comme tenue quand la mesure est faussee."""
    result = _capacity_result(injector_cpu_max=95.0, injector_cpu_warning=True)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800}, "capacity"))

    assert any("Capacité non concluante" in title for title in titles)
    assert not any("Capacité non atteinte" in title for title in titles)


def test_healthy_injector_keeps_capacity_conclusion() -> None:
    """Sans saturation, le verdict de capacite d'origine est conserve."""
    titles = _titles(analysis.analyze(_capacity_result(), {"p95_ms": 800}, "capacity"))

    assert any("Capacité non atteinte" in title for title in titles)
    assert not any("injecteur saturé" in title for title in titles)


def test_cpu_warning_flag_alone_triggers_the_rule() -> None:
    """L'alerte CPU emise par Locust suffit, meme sans releve de charge exploitable."""
    result = _capacity_result(injector_cpu_max=0.0, injector_cpu_warning=True)

    assert analysis._injector_saturated(result) is True
    assert any("injecteur saturé" in title for title in _titles(
        analysis.analyze(result, {}, "capacity")))


def test_breach_detail_warns_when_injector_saturated() -> None:
    """Une rupture mesuree par un injecteur sature est signalee comme suspecte."""
    breach = {"t": 120.0, "users": 300, "p95_ms": 900, "rps": 250.0, "error_rate": 0}
    result = _capacity_result(breach=breach, thresholds_ok=False,
                              injector_cpu_max=97.0, injector_cpu_warning=True)

    detail = next(f["detail"] for f in analysis.analyze(result, {}, "capacity")
                  if f["title"].startswith("Point de rupture"))

    assert "peut venir de la machine de test" in detail


def test_next_step_is_silenced_when_injector_saturated() -> None:
    """Aucune conclusion sur le systeme tant que la mesure n'est pas fiable."""
    result = _capacity_result(test_type="load", injector_cpu_max=99.0,
                              injector_cpu_warning=True)

    assert analysis._rule_next_step(result, {}, "load") is None
    assert analysis._rule_next_step(_capacity_result(test_type="load"), {}, "load") is not None


def test_status_downgrades_to_warn_when_injector_saturated() -> None:
    """Un run par ailleurs vert devient « a surveiller » si l'injecteur a sature."""
    saturated = _capacity_result(injector_cpu_max=98.0, injector_cpu_warning=True)

    assert analysis.compute_status(saturated, {"p95_ms": 800}) == "warn"
    assert analysis.compute_status(_capacity_result(), {"p95_ms": 800}) == "ok"


def test_status_keeps_failure_over_injector_warning() -> None:
    """Un seuil non tenu reste un echec, meme avec un injecteur sature."""
    result = _capacity_result(thresholds_ok=False, injector_cpu_max=98.0,
                              injector_cpu_warning=True)

    assert analysis.compute_status(result, {"p95_ms": 800}) == "fail"


def test_legacy_result_without_cpu_field_is_not_saturated() -> None:
    """Un run historique, sans releve CPU, ne declenche aucune alerte injecteur."""
    result = _capacity_result()
    result.pop("injector_cpu_max")
    result.pop("injector_cpu_warning")

    assert analysis._injector_saturated(result) is False
    assert analysis.compute_status(result, {"p95_ms": 800}) == "ok"


def test_run_too_short_to_sample_cpu_is_not_saturated() -> None:
    """Sans echantillon CPU exploitable (run court), aucune alerte n'est levee."""
    result = _capacity_result(injector_cpu_max=None, injector_cpu_warning=False)

    assert analysis._injector_saturated(result) is False
    assert analysis.compute_status(result, {"p95_ms": 800}) == "ok"


def _calibration_result(**overrides) -> dict:
    """Resultat d'un calibrage : l'injecteur a sature comme prevu."""
    result = _capacity_result(
        test_type="calibration",
        injector_cpu_max=88.0,
        injector_capacity_rps=1900.0,
        min_ms=3,
        p95_ms=20,
        vus_max=250,
        breach={"t": 90.0, "users": 250, "p95_ms": 20, "rps": 1900.0,
                "error_rate": 0, "cause": "cpu", "cpu": 88.0},
    )
    result.update(overrides)
    return result


def test_calibration_reports_capacity_and_safety_margin() -> None:
    """Le calibrage annonce le debit atteint et la marge a conserver."""
    findings = analysis.analyze(_calibration_result(), {}, "calibration")

    assert any("Capacité de l'injecteur : ~1900 req/s" in f["title"] for f in findings)
    assert any("~633 req/s" in f["detail"] for f in findings)


def test_calibration_does_not_treat_saturation_as_a_defect() -> None:
    """Saturer l'injecteur est l'objectif : ni constat critique, ni verdict degrade."""
    result = _calibration_result(injector_cpu_warning=True, injector_cpu_max=95.0)

    titles = _titles(analysis.analyze(result, {}, "calibration"))

    assert not any("Mesure non fiable" in title for title in titles)
    assert not any("Capacité non" in title for title in titles)
    assert analysis.compute_status(result, {}) == "ok"


def test_calibration_without_saturation_suggests_pushing_further() -> None:
    """Sans saturation, l'injecteur garde de la reserve et on le dit."""
    result = _calibration_result(breach=None, injector_cpu_max=60.0)

    finding = analysis.analyze(result, {}, "calibration")[0]

    assert finding["level"] == "good"
    assert "non saturé" in finding["title"]


def test_calibration_warns_when_the_target_gave_up_first() -> None:
    """Des erreurs pendant le calibrage signalent une cible trop lente pour qualifier."""
    titles = _titles(analysis.analyze(
        _calibration_result(error_rate=0.04), {}, "calibration"))

    assert any("cible a cédé" in title for title in titles)
    assert analysis.compute_status(_calibration_result(error_rate=0.04), {}) == "warn"


def test_calibration_does_not_blame_the_target_for_injector_saturation() -> None:
    """Une latence qui grimpe sans erreur vient de l'injecteur : c'est le but du test."""
    titles = _titles(analysis.analyze(
        _calibration_result(min_ms=2, p95_ms=400, error_rate=0), {}, "calibration"))

    assert not any("cible a cédé" in title for title in titles)


def test_injector_close_to_its_limit_is_flagged_as_a_warning() -> None:
    """Entre 75 et 90 % de CPU, la mesure tient encore mais la marge est signalee."""
    findings = analysis.analyze(_capacity_result(injector_cpu_max=80.0), {}, "capacity")
    finding = next(f for f in findings if "injecteur" in f["title"])

    assert finding["level"] == "warn"
    assert "Marge faible" in finding["title"]
    assert analysis.compute_status(_capacity_result(injector_cpu_max=80.0), {}) == "ok"


def test_missing_virtual_users_invalidate_the_conclusion() -> None:
    """Une charge non appliquee est signalee et retire le verdict positif."""
    result = _capacity_result(vus_max=520, vus_deficit_pct=13.0)

    findings = analysis.analyze(result, {"p95_ms": 800}, "capacity")
    titles = _titles(findings)

    assert any("Charge appliquée inférieure" in title for title in titles)
    assert any("520 atteints sur 600" in f["detail"] for f in findings)
    assert not any("Capacité non atteinte" in title for title in titles)
    assert analysis.compute_status(result, {"p95_ms": 800}) == "warn"


def test_small_virtual_user_gap_stays_silent() -> None:
    """Un ecart marginal de VUs ne declenche rien (bruit de spawn)."""
    result = _capacity_result(vus_max=598, vus_deficit_pct=0.3)

    assert analysis._load_not_applied(result) is False
    assert analysis.compute_status(result, {"p95_ms": 800}) == "ok"


def test_dominant_floor_is_explained_and_silences_the_ttfb_rule() -> None:
    """Quand la requete la plus rapide fait deja 92 % du p95, on parle de plancher."""
    result = _capacity_result(min_ms=101, p95_ms=110, ttfb_p95_ms=109)

    findings = analysis.analyze(result, {"p95_ms": 800}, "capacity")
    titles = _titles(findings)

    assert any("plancher incompressible" in title for title in titles)
    assert not any("dominé par le serveur" in title for title in titles)


def test_server_bound_run_still_reports_the_ttfb_rule() -> None:
    """Si le plancher est faible, l'analyse conclut bien au traitement serveur."""
    result = _capacity_result(min_ms=20, p95_ms=390, ttfb_p95_ms=380)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800}, "capacity"))

    assert any("dominé par le serveur" in title for title in titles)
    assert not any("plancher incompressible" in title for title in titles)


def test_a_handful_of_requests_disqualifies_the_high_percentiles() -> None:
    """Sur dix requetes, une seule valeur isolee fixe le p95, le p99 et le max.

    Cas rencontre en reel : un smoke sur nginx (neuf requetes a 2 ms, une a
    104 ms) concluait « le goulot est cote backend » pour un serveur statique.
    """
    result = _capacity_result(
        test_type="smoke", reqs_total=10, min_ms=1.2, p50_ms=2,
        p95_ms=100, p99_ms=100, ttfb_p95_ms=103.7,
    )

    titles = _titles(analysis.analyze(result, {"p95_ms": 800, "p99_ms": 50}, "smoke"))

    assert any("Percentiles peu fiables" in title for title in titles)
    assert any("10 requêtes" in title for title in titles)
    assert not any("dominé par le serveur" in title for title in titles)
    assert not any("Queue de distribution" in title for title in titles)


def test_enough_requests_keeps_the_percentile_verdicts() -> None:
    """Passe le seuil d'effectif, les regles sur percentiles reprennent la parole."""
    result = _capacity_result(reqs_total=5000, min_ms=20, p95_ms=390, ttfb_p95_ms=380)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800}, "capacity"))

    assert not any("Percentiles peu fiables" in title for title in titles)
    assert any("dominé par le serveur" in title for title in titles)


def test_bad_tail_alone_points_to_an_intermittent_incident() -> None:
    """p95 tenu mais p99 hors seuil : une requete sur cent decroche, pas le service."""
    params = {"p95_ms": 800, "p99_ms": 1600}
    result = _capacity_result(test_type="load", p95_ms=390, p99_ms=2400,
                              thresholds_ok=False)

    finding = next(f for f in analysis.analyze(result, params, "load")
                   if "Queue de distribution" in f["title"])

    assert finding["level"] == "warn"
    assert "p99 2400 ms > 1600 ms" in finding["title"]
    assert "intermittent" in finding["detail"]
    assert analysis.compute_status(result, params) == "fail"


def test_both_percentiles_over_threshold_point_to_a_global_cause() -> None:
    """Les deux seuils sautent ensemble : ce n'est plus la queue, c'est tout le trafic."""
    result = _capacity_result(test_type="load", p95_ms=1200, p99_ms=2400,
                              thresholds_ok=False)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800, "p99_ms": 1600}, "load"))

    assert any("Service lent sur tout le trafic" in title for title in titles)
    assert not any("Queue de distribution" in title for title in titles)


def test_tail_rule_stays_silent_without_a_p99_threshold() -> None:
    """Sans seuil p99 declare (smoke, calibrage, run historique), la regle se tait."""
    result = _capacity_result(test_type="load", p95_ms=390, p99_ms=9000)

    assert analysis._rule_tail(result, {"p95_ms": 800}, "load") is None


def test_local_target_shares_the_machine_with_the_injector() -> None:
    """Une cible locale est signalee : injecteur et serveur se disputent le CPU."""
    titles = _titles(analysis.analyze(_capacity_result(target_is_local=True), {}, "capacity"))

    assert any("Cible locale" in title for title in titles)
    assert not any("Cible locale" in title for title in _titles(
        analysis.analyze(_capacity_result(), {}, "capacity")))


def test_self_limited_load_is_reported_and_downgrades_the_verdict() -> None:
    """Un debit qui decroche rend le p95 optimiste : constat d'alerte et verdict nuance."""
    result = _capacity_result(test_type="load", throughput_shortfall_pct=62.0,
                              throughput_actual_rps=715.0, throughput_nominal_rps=1904.0,
                              throughput_users=200)

    finding = next(f for f in analysis.analyze(result, {"p95_ms": 800}, "load")
                   if "auto-limitée" in f["title"])

    assert finding["level"] == "warn"
    assert "-62 %" in finding["title"]
    assert "715 req/s produits contre 1904 attendus à 200 utilisateurs" in finding["title"]
    assert analysis.compute_status(result, {"p95_ms": 800}) == "warn"


def test_self_limited_load_silences_the_positive_conclusion() -> None:
    """« Charge nominale tenue » n'a pas de sens si la charge s'est effondree."""
    result = _capacity_result(test_type="load", throughput_shortfall_pct=45.0)

    assert analysis._rule_next_step(result, {}, "load") is None
    assert analysis._rule_next_step(_capacity_result(test_type="load"), {}, "load") is not None


def test_self_limitation_is_only_informative_on_a_stress() -> None:
    """Depasser le plafond est le but d'un stress : constat informatif, verdict inchange."""
    result = _capacity_result(test_type="stress", throughput_shortfall_pct=70.0)

    finding = next(f for f in analysis.analyze(result, {"p95_ms": 1500}, "stress")
                   if "auto-limitée" in f["title"])

    assert finding["level"] == "info"
    assert analysis.compute_status(result, {"p95_ms": 1500}) == "ok"


def test_small_throughput_shortfall_stays_silent() -> None:
    """Quelques pour cent d'ecart sont du bruit de mesure, pas une auto-limitation."""
    result = _capacity_result(test_type="load", throughput_shortfall_pct=8.0)

    assert not any("auto-limitée" in title
                   for title in _titles(analysis.analyze(result, {"p95_ms": 800}, "load")))
    assert analysis.compute_status(result, {"p95_ms": 800}) == "ok"


def _open_result(**overrides) -> dict:
    """Resultat d'un run a debit impose (modele ouvert, moteur k6)."""
    result = {
        "engine": "k6",
        "model": "open",
        "test_type": "open_load",
        "min_ms": 50.3,
        "p50_ms": 62,
        "p95_ms": 120,
        "ttfb_p95_ms": 60,
        "error_rate": 0,
        "checks_rate": 1,
        "reqs_per_sec": 100,
        "rate_target": 100,
        "vus_max": 30,
        "max_vus_allowed": 400,
        "dropped_iterations": 0,
        "dropped_pct": 0,
        "seuil_p95_ms": 800,
        "thresholds_ok": True,
    }
    result.update(overrides)
    return result


def test_open_model_reports_the_requests_that_never_left() -> None:
    """Le signal propre au modele ouvert : ce que l'injecteur n'a PAS pu envoyer."""
    result = _open_result(dropped_iterations=2572, dropped_pct=46.8, p95_ms=5058,
                          reqs_per_sec=75, rate_target=200, vus_max=400,
                          thresholds_ok=False)

    finding = next(f for f in analysis.analyze(result, {}, "open_load")
                   if "Débit non tenu" in f["title"])

    assert finding["level"] == "crit"
    assert "46.8 %" in finding["title"]
    assert "plafond de 400 VUs" in finding["detail"]


def test_open_model_blames_the_system_when_virtual_users_remained() -> None:
    """Sans plafond atteint, le retard vient du systeme teste, pas du reglage."""
    result = _open_result(dropped_iterations=400, dropped_pct=20.0, vus_max=150)

    detail = next(f["detail"] for f in analysis.analyze(result, {}, "open_load")
                  if "Débit non tenu" in f["title"])

    assert "ne suit pas le rythme" in detail
    assert "plafond" not in detail


def test_open_model_confirms_a_load_really_applied() -> None:
    """Debit tenu = temps de reponse non optimistes : c'est l'interet du modele ouvert."""
    findings = analysis.analyze(_open_result(), {}, "open_load")

    assert any("Débit tenu" in f["title"] and f["level"] == "good" for f in findings)
    assert analysis.compute_status(_open_result(), {}) == "ok"


def test_open_model_status_warns_when_the_flow_was_not_delivered() -> None:
    """Un run dont le debit n'a pas ete applique ne peut pas etre annonce comme reussi."""
    result = _open_result(dropped_pct=12.0, dropped_iterations=300)

    assert analysis.compute_status(result, {}) == "warn"


def test_closed_model_rules_stay_out_of_an_open_run() -> None:
    """Compter des VUs manquants ou une auto-limitation n'a aucun sens à debit impose."""
    result = _open_result(vus_deficit_pct=40.0, throughput_shortfall_pct=80.0)

    titles = _titles(analysis.analyze(result, {}, "open_load"))

    assert not any("auto-limitée" in title for title in titles)
    assert not any("Charge appliquée inférieure" in title for title in titles)


def test_saturated_injector_is_reported_on_an_open_run_too() -> None:
    """La machine de test peut fausser un run k6 comme un run Locust : meme alerte."""
    result = _open_result(injector_cpu_max=97.0, injector_cpu_warning=True)

    titles = _titles(analysis.analyze(result, {}, "open_load"))

    assert any("injecteur saturé" in title for title in titles)
    assert analysis.compute_status(result, {}) == "warn"


def test_open_model_blames_the_injector_when_the_machine_saturated() -> None:
    """Des requetes non parties SANS plafond de VUs atteint, mais CPU au plafond."""
    result = _open_result(dropped_pct=20.0, dropped_iterations=400, vus_max=150,
                          injector_cpu_max=97.0, injector_cpu_warning=True)

    detail = next(f["detail"] for f in analysis.analyze(result, {}, "open_load")
                  if "Débit non tenu" in f["title"])

    assert "vient sans doute de l'injecteur" in detail


def test_open_model_blames_the_target_when_the_injector_was_fine() -> None:
    """Meme retard, injecteur au repos : c'est le systeme teste qui ne suit pas."""
    result = _open_result(dropped_pct=20.0, dropped_iterations=400, vus_max=150,
                          injector_cpu_max=30.0, injector_cpu_warning=False)

    detail = next(f["detail"] for f in analysis.analyze(result, {}, "open_load")
                  if "Débit non tenu" in f["title"])

    assert "ne suit pas le rythme" in detail


def test_open_capacity_reports_the_absorbed_throughput() -> None:
    """La capacite du modele ouvert s'exprime en req/s absorbees, pas en utilisateurs."""
    result = _open_result(test_type="open_capacity", rate_target=500, dropped_pct=8.0,
                          dropped_iterations=210, thresholds_ok=False,
                          breach={"t": 96.0, "rps": 78.0, "p95_ms": 2400,
                                  "dropped": 210, "cause": "dropped"})

    findings = analysis.analyze(result, {}, "open_capacity")
    titles = _titles(findings)

    assert any("Capacité d'absorption : ~78 req/s" in title for title in titles)
    # Le decrochage EST le resultat cherche : pas de doublon avec « Debit non tenu ».
    assert not any("Débit non tenu" in title for title in titles)


def test_open_capacity_without_stall_invites_to_push_further() -> None:
    """Sans decrochage, le plafond teste n'est pas la limite du systeme."""
    result = _open_result(test_type="open_capacity", rate_target=500)

    finding = next(f for f in analysis.analyze(result, {}, "open_capacity")
                   if "Capacité" in f["title"])

    assert finding["level"] == "good"
    assert "500 req/s" in finding["title"]


def test_open_capacity_verdict_message_speaks_of_throughput() -> None:
    """Le message final d'un decrochage ne parle pas d'utilisateurs actifs."""
    result = {"breach": {"t": 96.0, "rps": 78.0, "cause": "dropped"}}

    assert "78 req/s" in runner_common.verdict_log(result)


def test_calibration_verdict_message_speaks_of_the_injector_not_the_latency() -> None:
    """Sur un calibrage, le run s'arrete sur le CPU : citer le seuil p95 serait faux.

    Cas rencontre en reel : « Rupture a ~50 users actifs - p95 25 ms (> 800 ms) »,
    alors que 25 ms n'a jamais depasse 800 ms.
    """
    result = {
        "breach": {"t": 20.0, "users": 50, "p95_ms": 25, "rps": 1796.7,
                   "cause": "cpu", "cpu": 100.0},
        "seuil_p95_ms": 800,
    }

    message = runner_common.verdict_log(result)

    assert "100 % de CPU" in message
    assert "1797 req/s" in message
    assert "800" not in message
    assert "25 ms" not in message


def test_a_run_that_never_reached_the_service_silences_every_performance_rule() -> None:
    """Cas reel : mauvaise cible choisie, rien n'ecoutait, 100 % d'echecs.

    Les temps mesures etaient alors la vitesse du refus de connexion (4 ms), et
    l'analyse en concluait « payload volumineux » et « point de rupture atteint ».
    """
    result = {
        "error_rate": 1.0, "checks_rate": 0.0, "thresholds_ok": False,
        "p50_ms": 4, "p95_ms": 10, "p99_ms": 12, "min_ms": 0.5, "ttfb_p95_ms": 0,
        "reqs_total": 6300, "reqs_per_sec": 42.3,
        "breach": {"t": 60.0, "users": 60, "p95_ms": 10, "rps": 42.3},
    }

    findings = analysis.analyze(result, {"p95_ms": 10000, "p99_ms": 12000}, "stress")
    titles = _titles(findings)

    assert findings[0]["level"] == "crit"
    assert "injoignable" in findings[0]["title"]
    assert not any("r\u00e9seau/transfert" in t or "Point de rupture" in t for t in titles)


def test_a_normal_error_rate_leaves_the_performance_rules_alone() -> None:
    """Le garde-fou ne doit pas bailloner l'analyse d'un run qui a bien tourne."""
    result = _capacity_result(error_rate=0.002, ttfb_p95_ms=970, p95_ms=1000, min_ms=80)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800}, "capacity"))

    assert any("serveur" in title for title in titles)


def test_a_calibration_against_a_dead_target_is_a_failure() -> None:
    """Sans reponse, le debit mesure n'est que la vitesse de l'erreur."""
    result = {"test_type": "calibration", "error_rate": 1.0, "injector_capacity_rps": 4000}

    assert analysis.compute_status(result, {}) == "fail"


def test_a_saturated_link_is_named_as_the_limiting_factor() -> None:
    """Au-dela de 70 % du lien, c'est le cable qui plafonne le debit, pas le serveur."""
    result = _capacity_result(network_usage_pct=82.0, link_speed_mbps=100)

    findings = analysis.analyze(result, {"p95_ms": 800}, "capacity")
    finding = next(f for f in findings if "Réseau" in f["title"])

    assert finding["level"] == "warn"
    assert "82 %" in finding["title"]
    assert "100 Mb/s" in finding["title"]


def test_a_quiet_link_stays_silent() -> None:
    """A 4 % du lien, le reseau n'a rien a dire : une alerte permanente ne serait plus lue."""
    result = _capacity_result(network_usage_pct=4.0, link_speed_mbps=1000)

    titles = _titles(analysis.analyze(result, {"p95_ms": 800}, "capacity"))

    assert not any("Réseau" in title for title in titles)


def test_injector_conditions_are_recorded_with_the_result(monkeypatch) -> None:
    """Sans le parallelisme, deux runs du meme scenario sont incomparables."""
    monkeypatch.setattr(runner_common, "link_speed_mbps", lambda _: 1000)
    result = {"data_received_rate": 12_500_000}  # 100 Mb/s sur un lien a 1000

    runner_common.describe_injector(
        result, {"base_url": "http://cible.local"}, {"processes": 6}
    )

    assert result["injector_processes"] == 6
    assert result["injector_cores"] == os.cpu_count()
    assert result["network_usage_pct"] == 10.0
    assert result["target_is_local"] is False


def test_an_engine_without_processes_reports_none(monkeypatch) -> None:
    """k6 repartit la charge en interne : annoncer « 1 processus » serait trompeur."""
    monkeypatch.setattr(runner_common, "link_speed_mbps", lambda _: None)
    result = {}

    runner_common.describe_injector(result, {"base_url": "https://cible.test"}, {})

    assert result["injector_processes"] is None
    assert result["link_speed_mbps"] is None
    assert "network_usage_pct" not in result

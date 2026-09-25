"""Tests du rapport HTML partageable d'un run de charge."""

import html

from services.load import html_report, runner_common


def _texte(page: str) -> str:
    """Le rendu tel que le lecteur le voit : sans lui, une apostrophe echappee en
    `&#x27;` ferait passer n'importe quelle assertion « absent de la page »."""
    return html.unescape(page)


def _run(**result_fields) -> dict:
    result = {
        "engine": "locust", "status": "ok", "p50_ms": 17, "p95_ms": 23,
        "reqs_total": 265_407, "reqs_per_sec": 8866.9, "error_rate": 0.0,
        "duration_s": 600.0, "vus_max": 200,
    }
    result.update(result_fields)
    return html_report.build_run(
        "cible_demo",
        {"label": "Cible de demo", "base_url": "http://cible.local"},
        result_fields.pop("test_type", "load"),
        {"vus": 200, "think_time": 1},
        result,
    )


def test_the_verdict_leads_with_a_sentence_anyone_can_read() -> None:
    """Celui qui ne lit qu'une ligne doit repartir avec le chiffre et son sens."""
    page = _texte(html_report.render(_run(status="ok")))

    assert "Objectifs tenus" in page
    assert "95 % des requêtes répondent en moins de 23 ms" in page
    assert "8 867 req/s" in page.replace("\u202f", " ")


def test_a_calibration_says_it_measures_the_injector_not_the_application() -> None:
    """Confondre les deux ferait passer la capacite de l'outil pour celle du produit."""
    run = _run(test_type="calibration", injector_capacity_rps=1796.7)
    run["test_type"] = "calibration"

    page = _texte(html_report.render(run))

    assert "qualifie l'outil de mesure, pas l'application" in page


def test_a_short_run_says_nothing_about_endurance() -> None:
    """Un run de 30 s ne peut pas reveler une fuite memoire : le rapport doit le dire."""
    page = _texte(html_report.render(_run(duration_s=30.0)))

    assert "fuite mémoire" in page
    assert "test d'endurance" in page


def test_a_long_run_drops_the_endurance_caveat() -> None:
    """La limite ne vaut que si elle est vraie : sinon plus personne ne lit la section."""
    page = _texte(html_report.render(_run(duration_s=1800.0)))

    assert "test d'endurance" not in page


def test_a_saturated_injector_warns_that_the_numbers_include_its_own_wait() -> None:
    page = _texte(html_report.render(_run(injector_cpu_warning=True)))

    assert "machine d'injection a saturé" in page


def test_a_tiny_sample_warns_that_the_percentile_is_unstable() -> None:
    page = _texte(html_report.render(_run(reqs_total=10)))

    assert "que sur 10 requêtes" in page


def test_a_run_without_think_time_forbids_comparing_user_counts() -> None:
    """Sans pause, « 200 utilisateurs » ne correspond a aucun effectif reel."""
    run = html_report.build_run(
        "cible_demo", {"label": "Cible de demo", "base_url": "http://cible.local"},
        "load", {"think_time": 0}, {"status": "ok", "p95_ms": 23, "duration_s": 600},
    )

    page = _texte(html_report.render(run))

    assert "comparable à aucun effectif réel" in page


def test_a_failed_run_never_advertises_flattering_response_times() -> None:
    """Cas reel : « 95 % des requetes repondent en moins de 10 ms » sur 100 % d'echecs.

    Ce document est destine a circuler : une accroche pareille est pire qu'inutile.
    """
    page = _texte(html_report.render(_run(error_rate=1.0, p95_ms=10, status="fail")))

    assert "100 % des requêtes ont échoué" in page
    assert "n'est exploitable" in page
    assert "répondent en moins de" not in page


def test_a_stress_is_never_declared_a_success_or_a_failure() -> None:
    """Cas reel : « Objectifs tenus » sur un service qui repondait en 4,4 secondes.

    Le seuil avait ete monte a 10 s pour laisser le test aller au bout ; le rapport
    en concluait un succes, ce qu'un lecteur exterieur aurait pris pour argent comptant.
    """
    run = _run(status="ok", p95_ms=4400, min_ms=81, vus_max=60, reqs_per_sec=11.6)
    run["test_type"] = "stress"

    page = _texte(html_report.render(run))

    assert "Comportement en surcharge" in page
    assert "Objectifs tenus" not in page
    assert "54 fois son temps au repos" in page
    assert 'class="verdict neutre"' in page


def test_an_open_model_run_speaks_of_throughput_not_of_users() -> None:
    """Cas reel : « sous 25 utilisateurs simultanes » sur un test a debit impose.

    Ces 25 sont un detail interne de k6, pas une charge choisie : les afficher
    laisse croire qu'on a mesure la tenue a 25 utilisateurs.
    """
    run = _run(p95_ms=1017, reqs_per_sec=7.9, vus_max=25, rate_target=40, status="fail")
    run["test_type"] = "open_capacity"

    page = _texte(html_report.render(run))

    assert "débit imposé jusqu'à 40 req/s" in page
    assert "utilisateurs simultanés" not in page


def test_a_stress_at_imposed_rate_is_judged_like_any_other_stress() -> None:
    """Le modele de charge change, pas la nature du test."""
    run = _run(status="fail", p95_ms=9000, rate_target=40, thresholds_ok=False)
    run["test_type"] = "open_stress"

    page = _texte(html_report.render(run))

    assert "Comportement en surcharge" in page
    assert "Objectifs non tenus" not in page
    assert 'class="verdict neutre"' in page


def test_a_stress_that_really_breaks_keeps_its_red_flag() -> None:
    """Ralentir est attendu, rejeter ne l'est pas : la distinction doit rester visible."""
    run = _run(status="fail", p95_ms=9000, error_rate=0.12)
    run["test_type"] = "stress"

    page = _texte(html_report.render(run))

    assert "Comportement en surcharge" in page
    assert 'class="verdict fail"' in page


def test_requests_that_never_left_are_not_reported_as_absence_of_errors() -> None:
    """Cas reel : « aucune erreur » avec 55 % des requetes jamais envoyees.

    Exact au sens HTTP, faux du point de vue de l'utilisateur : rien ne lui est
    revenu. C'est la premiere phrase du rapport, celle qui circule seule.
    """
    run = _run(p95_ms=35412, reqs_per_sec=11.7, rate_target=40,
               dropped_pct=54.9, error_rate=0.0, status="fail")
    run["test_type"] = "open_stress"

    page = _texte(html_report.render(run))

    assert "55 % des requêtes n'ont jamais pu partir" in page
    assert "aucune erreur" not in page


def test_values_coming_from_the_interface_cannot_inject_markup() -> None:
    """Les parametres viennent du navigateur : ils ne doivent jamais etre du HTML."""
    run = html_report.build_run(
        "x", {"label": "<img src=x onerror=alert(1)>", "base_url": "http://cible.local"},
        "load", {"think_time": "<script>alert(1)</script>"},
        {"status": "ok", "p95_ms": 23, "duration_s": 600},
    )

    page = html_report.render(run)

    assert "<img src=x" not in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;img src=x" in page


def test_the_written_report_names_the_test_type_in_plain_words(tmp_path, monkeypatch) -> None:
    """\u00ab capacity \u00bb ne veut rien dire pour le destinataire du rapport."""
    monkeypatch.setattr(runner_common, "REPORTS_DIR", tmp_path)
    result = {"status": "fail", "p95_ms": 810, "duration_s": 137}

    runner_common.write_report(
        "abc123", "cible_demo", {"label": "Cible de demo", "base_url": "http://cible.local"},
        "capacity", {}, result,
    )

    page = _texte((tmp_path / "rapport_abc123.html").read_text(encoding="utf-8"))

    assert "Capacit\u00e9 - paliers" in page
    assert result["summary_report_url"] == "/load-report/rapport_abc123.html"

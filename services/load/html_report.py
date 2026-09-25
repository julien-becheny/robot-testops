"""Rapport HTML d'un run de charge, destiné à être lu hors de TestOps.

L'interface s'adresse à qui a lancé le test et connaît le contexte. Ce rapport
s'adresse aux autres - exploitation, architecture, direction technique : il se lit
sans explication, se joint à un mail et s'imprime. D'où l'absence de JavaScript.

La page est ordonnée en quatre couches, chacun s'arrêtant où son intérêt s'arrête :
le verdict, les conditions de la mesure, les chiffres, puis ce que la mesure ne dit
pas - la couche qui manque à la plupart des rapports de performance.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

_VERDICTS = {
    "ok": ("Objectifs tenus", "Les seuils fixés avant le test sont respectés."),
    "warn": ("Résultat à nuancer", "Rien n'a cédé, mais les conditions limitent la portée de la mesure."),
    "fail": ("Objectifs non tenus", "Au moins un seuil fixé avant le test a été dépassé."),
}

# Un stress dépasse VOLONTAIREMENT la capacité : prononcer un succès ou un échec sur
# ses seuils n'a pas de sens, et « objectifs tenus » sur un service à quatre secondes
# de temps de réponse serait trompeur pour qui reçoit ce document sans le contexte.
_VERDICT_STRESS = (
    "Comportement en surcharge",
    "Un stress pousse le système au-delà de sa capacité : il ne se juge pas en objectifs "
    "tenus, mais à la façon dont le service cède - ralentissement ou rejet - et à sa "
    "capacité à revenir quand la charge retombe.",
)

_STRESS = {"stress", "open_stress"}

_NIVEAUX = {"crit": "Point bloquant", "warn": "Point de vigilance", "info": "Remarque"}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _ms(value: Any) -> str:
    v = _num(value)
    if v is None:
        return "-"
    # Sous 10 ms, l'arrondi entier deforme : un plancher a 1,7 ms deviendrait 2 ms.
    if v < 10:
        return f"{v:.1f} ms".replace(".", ",")
    return f"{v:,.0f} ms".replace(",", "\u202f")


def _rps(value: Any) -> str:
    v = _num(value)
    return f"{v:,.0f} req/s".replace(",", "\u202f") if v is not None else "-"


def _count(value: Any) -> str:
    v = _num(value)
    return f"{v:,.0f}".replace(",", "\u202f") if v is not None else "-"


def _pct(value: Any, digits: int = 2) -> str:
    v = _num(value)
    return f"{v * 100:.{digits}f} %".replace(".", ",") if v is not None else "-"


def _duration(seconds: Any) -> str:
    v = _num(seconds)
    if v is None:
        return "-"
    minutes, secs = divmod(int(v), 60)
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


def _headline(result: dict, test_type: str) -> str:
    """La phrase que retient celui qui ne lira rien d'autre."""
    err = _num(result.get("error_rate")) or 0
    # Annoncer un temps de réponse flatteur quand tout a échoué rendrait le rapport nuisible.
    if err >= 0.5:
        return (f"{_pct(err, 0)} des requêtes ont échoué. Les temps affichés plus bas ne "
                "mesurent que la vitesse à laquelle les erreurs sont revenues : aucun "
                "chiffre de performance de ce rapport n'est exploitable.")
    if test_type == "calibration":
        capacity = result.get("injector_capacity_rps")
        return (f"La machine d'injection plafonne à {_rps(capacity)}. "
                "Ce chiffre qualifie l'outil de mesure, pas l'application testée.")
    p95 = _ms(result.get("p95_ms"))
    debit = _rps(result.get("reqs_per_sec"))
    erreurs = "aucune erreur" if err == 0 else f"{_pct(err)} d'erreurs"
    vus = _num(result.get("vus_max"))
    charge = f" sous {int(vus)} utilisateurs simultanés" if vus else ""
    # Modèle ouvert : les utilisateurs sont un détail interne de l'injecteur, la
    # charge choisie est un débit d'arrivée.
    if test_type.startswith("open_"):
        vise = _num(result.get("rate_target"))
        demande = f" jusqu'à {vise:.0f} req/s" if vise else ""
        perdu = _num(result.get("dropped_pct")) or 0
        # « Aucune erreur » serait exact et trompeur : une requête jamais émise ne
        # produit pas d'erreur HTTP, mais l'utilisateur n'a rien reçu non plus.
        if perdu >= 1:
            return (f"Sous un débit imposé{demande}, le système n'en absorbe que {debit} : "
                    f"{perdu:.0f} % des requêtes n'ont jamais pu partir.")
        return (f"Sous un débit imposé{demande}, 95 % des requêtes répondent en {p95} "
                f"et le système en absorbe {debit}, {erreurs}.")
    if test_type in _STRESS:
        floor, p95_v = _num(result.get("min_ms")), _num(result.get("p95_ms"))
        facteur = (f", soit {p95_v / floor:.0f} fois son temps au repos"
                   if floor and p95_v else "")
        return (f"{charge.strip().capitalize()}, 95 % des requêtes répondent en "
                f"{p95}{facteur}, à {debit}, {erreurs}.")
    return f"95 % des requêtes répondent en moins de {p95}{charge}, à {debit}, {erreurs}."


def _conditions(run: dict) -> list[tuple[str, str]]:
    """Ce qui rend le chiffre reproductible - et donc discutable."""
    result = run.get("result") or {}
    params = run.get("params") or {}
    rows = [
        ("Application testée", f"{run.get('target_label') or run.get('target')} - {run.get('base_url', '')}"),
        ("Type de test", run.get("test_type_label") or run.get("test_type", "")),
        ("Date de la mesure", run.get("generated_at", "")),
        ("Durée du run", _duration(result.get("duration_s"))),
        ("Outil d'injection", {"locust": "Locust", "k6": "k6"}.get(result.get("engine"), result.get("engine", ""))),
    ]
    processes, cores = result.get("injector_processes"), result.get("injector_cores")
    if processes or cores:
        rows.append(("Machine d'injection",
                     f"{processes} processus sur {cores} cœurs" if processes else f"{cores} cœurs"))
    if result.get("link_speed_mbps"):
        usage = result.get("network_usage_pct")
        part = f", occupé à {_num(usage):.0f} %" if _num(usage) is not None else ""
        rows.append(("Lien réseau", f"{result['link_speed_mbps']} Mb/s{part}"))
    seuil = result.get("seuil_p95_ms")
    if seuil:
        rows.append(("Seuil fixé avant le test", f"95 % des requêtes sous {_ms(seuil)}"))
    if params.get("think_time") is not None:
        rows.append(("Temps de réflexion simulé", f"{params['think_time']} s entre deux requêtes"))
    return rows


def _figures(result: dict) -> list[tuple[str, str, str]]:
    """Les chiffres, du plus parlant au plus technique."""
    cells = [
        ("Temps de réponse médian", _ms(result.get("p50_ms")), "la moitié des requêtes est plus rapide"),
        ("95ᵉ centile", _ms(result.get("p95_ms")), "l'expérience des 5 % les moins bien servis"),
        ("99ᵉ centile", _ms(result.get("p99_ms")), "le pire ressenti régulier"),
        ("Plancher", _ms(result.get("min_ms")), "la requête la plus rapide, hors charge"),
        ("Débit soutenu", _rps(result.get("reqs_per_sec")), "requêtes absorbées par seconde"),
        ("Requêtes émises", _count(result.get("reqs_total")), "volume total de la mesure"),
        ("Taux d'erreur", _pct(result.get("error_rate")), "requêtes sans réponse valide"),
    ]
    if _num(result.get("checks_rate")) is not None:
        cells.append(("Réponses conformes", _pct(result.get("checks_rate"), 1),
                      "le contenu reçu est celui attendu"))
    if _num(result.get("ttfb_p95_ms")) is not None:
        cells.append(("Attente serveur (p95)", _ms(result.get("ttfb_p95_ms")),
                      "temps de réflexion du serveur seul, hors transfert"))
    return cells


def _limits(run: dict) -> list[str]:
    """Ce que la mesure ne dit pas : la couche qui empêche de la sur-interpréter."""
    result = run.get("result") or {}
    params = run.get("params") or {}
    limits = [
        "La mesure est prise du point de vue du client. Elle ne contient aucune métrique du "
        "système testé - processeur, base de données, files d'attente : elle constate un "
        "symptôme, elle ne désigne pas une cause.",
        "Le trafic est synthétique et répète un même geste. Il ne reproduit ni la "
        "répartition réelle des usages, ni le volume de données réel en base, qui pèsent "
        "tous deux sur les temps observés.",
    ]
    duration = _num(result.get("duration_s"))
    if duration is not None and duration < 300:
        limits.append(
            f"Le run a duré {_duration(duration)}. Les défauts qui se révèlent avec le temps - "
            "fuite mémoire, connexions jamais rendues, cache qui expire - ne peuvent pas y "
            "apparaître : ils demandent un test d'endurance.")
    if str(params.get("think_time", "")).strip() in {"0", "0.0"}:
        limits.append(
            "Les utilisateurs simulés n'observent aucune pause entre deux requêtes. Le nombre "
            "d'utilisateurs affiché n'est donc comparable à aucun effectif réel : seul le débit "
            "en requêtes par seconde peut être rapproché de la production.")
    if result.get("target_is_local"):
        limits.append(
            "L'injecteur et l'application testée tournaient sur la même machine : ils se "
            "disputaient le même processeur. Les temps mesurés incluent cette concurrence.")
    if result.get("injector_cpu_warning"):
        limits.append(
            "La machine d'injection a saturé pendant le run. Une part des temps mesurés est "
            "de l'attente dans l'outil de mesure, pas dans l'application.")
    total = _num(result.get("reqs_total"))
    if total is not None and total < 100:
        limits.append(
            f"La mesure ne porte que sur {int(total)} requêtes. Un 95ᵉ centile calculé sur si peu "
            "d'échantillons se déplace entièrement au gré d'une ou deux requêtes lentes.")
    usage = _num(result.get("network_usage_pct"))
    if usage is not None and usage >= 70:
        limits.append(
            f"Le trafic occupait {usage:.0f} % du lien réseau. À ce niveau, c'est la bande "
            "passante qui plafonne le débit, et non le serveur.")
    return limits


_STYLE = """
  :root { --bg:#eceff4; --card:#fff; --txt:#1b2430; --dim:#5d6875; --line:#e3e8ef;
          --ok:#12783c; --ok-bg:#e9f7ee; --warn:#8a6100; --warn-bg:#fff6e3;
          --ko:#b3261e; --ko-bg:#fdecec; --info:#0b6ea9; --info-bg:#eef6fd; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt); font-size:15px; line-height:1.55;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  .page { max-width:920px; margin:32px auto; background:var(--card); border-radius:14px;
          box-shadow:0 1px 3px rgba(20,30,45,.08),0 12px 32px rgba(20,30,45,.07);
          padding:0 0 12px; overflow:hidden; }
  .verdict { padding:26px 34px; border-left:6px solid var(--dim); background:#f6f8fb; }
  .verdict.ok { border-left-color:var(--ok); background:var(--ok-bg); }
  .verdict.warn { border-left-color:var(--warn); background:var(--warn-bg); }
  .verdict.fail { border-left-color:var(--ko); background:var(--ko-bg); }
  .kicker { font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--dim); }
  .verdict h1 { font-size:27px; margin:7px 0 10px; }
  .verdict.ok h1 { color:var(--ok); } .verdict.warn h1 { color:var(--warn); }
  .verdict.fail h1 { color:var(--ko); }
  .headline { font-size:18px; margin:0; }
  .why { color:var(--dim); font-size:13.5px; margin:9px 0 0; }
  .block { padding:24px 34px 26px; }
  .block + .block { border-top:1px solid var(--line); }
  .block.cond { background:var(--info-bg); }
  .block.caveat { background:var(--warn-bg); }
  h2 { display:flex; align-items:center; gap:10px; font-size:15px; margin:0 0 16px; }
  .num { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px;
         border-radius:50%; font-size:12.5px; font-weight:700; color:#fff; background:var(--dim); }
  .cond .num { background:var(--info); } .figs .num { background:#067a8c; }
  .read .num { background:#5a4ab5; } .caveat .num { background:var(--warn); }
  table { width:100%; border-collapse:collapse; }
  td { padding:8px 0; border-bottom:1px solid rgba(27,36,48,.08); vertical-align:top; }
  tr:last-child td { border-bottom:none; }
  td:first-child { color:var(--dim); width:40%; padding-right:18px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(205px,1fr)); gap:11px; }
  .fig { border:1px solid var(--line); border-left:3px solid #067a8c; border-radius:9px;
         padding:13px 15px; background:var(--card); }
  .fig .lbl { color:var(--dim); font-size:12px; }
  .fig .val { font-size:24px; font-weight:600; margin:3px 0 3px; color:#0a5f6e; }
  .fig .hint { color:var(--dim); font-size:12px; line-height:1.4; }
  .find { border-radius:9px; padding:13px 16px; margin-bottom:9px; border-left:4px solid var(--dim);
          background:#f6f8fb; }
  .find.crit { border-left-color:var(--ko); background:var(--ko-bg); }
  .find.warn { border-left-color:var(--warn); background:var(--warn-bg); }
  .find.info { border-left-color:var(--info); background:var(--info-bg); }
  .find .lvl { font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }
  .find.crit .lvl { color:var(--ko); } .find.warn .lvl { color:var(--warn); }
  .find.info .lvl { color:var(--info); }
  .find .ttl { font-weight:600; margin:3px 0 5px; }
  .find .dtl { color:#3f4a58; font-size:14px; }
  ul.limits { padding-left:19px; margin:0; }
  ul.limits li { margin-bottom:10px; font-size:14px; color:#4a4330; }
  ul.limits li:last-child { margin-bottom:0; }
  footer { padding:18px 34px 6px; color:var(--dim); font-size:12px; border-top:1px solid var(--line); }
  @media print {
    body { background:#fff; }
    .page { box-shadow:none; margin:0; max-width:none; border-radius:0; }
    .block, .verdict, footer { padding-left:0; padding-right:0; }
    .block, .find, section { break-inside:avoid; }
  }
"""


def render(run: dict) -> str:
    """Produit la page HTML autonome d'un run de charge."""
    result = run.get("result") or {}
    status = result.get("status", "warn")
    test_type = run.get("test_type", "")
    if test_type in _STRESS:
        titre, pourquoi = _VERDICT_STRESS
        # Dépasser les seuils EST l'objectif : seules de vraies erreurs méritent l'alerte.
        ton = "fail" if (_num(result.get("error_rate")) or 0) > 0.01 else "neutre"
    else:
        titre, pourquoi = _VERDICTS.get(status, _VERDICTS["warn"])
        ton = status
    cible = run.get("target_label") or run.get("target") or "application"

    conditions = "".join(
        f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in _conditions(run) if v)
    figures = "".join(
        f'<div class="fig"><div class="lbl">{_e(lbl)}</div>'
        f'<div class="val">{_e(val)}</div><div class="hint">{_e(hint)}</div></div>'
        for lbl, val, hint in _figures(result))
    findings = "".join(
        f'<div class="find {_e(f.get("level", "info"))}">'
        f'<div class="lvl">{_e(_NIVEAUX.get(f.get("level"), "Remarque"))}</div>'
        f'<div class="ttl">{_e(f.get("title"))}</div>'
        f'<div class="dtl">{_e(f.get("detail"))}</div></div>'
        for f in result.get("analysis") or [])
    limits = "".join(f"<li>{_e(item)}</li>" for item in _limits(run))

    blocks = [
        f'<section class="block cond"><h2><span class="num">1</span>'
        f"Conditions de la mesure</h2><table>{conditions}</table></section>",
        f'<section class="block figs"><h2><span class="num">2</span>'
        f'Chiffres relevés</h2><div class="grid">{figures}</div></section>',
    ]
    if findings:
        blocks.append(f'<section class="block read"><h2><span class="num">3</span>'
                      f"Lecture du résultat</h2>{findings}</section>")
    blocks.append(f'<section class="block caveat"><h2><span class="num">{len(blocks) + 1}</span>'
                  f'Ce que cette mesure ne dit pas</h2><ul class="limits">{limits}</ul></section>')

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test de charge - {_e(cible)}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="page">
  <div class="verdict {_e(ton)}">
    <div class="kicker">Test de charge - {_e(cible)}</div>
    <h1>{_e(titre)}</h1>
    <p class="headline">{_e(_headline(result, test_type))}</p>
    <p class="why">{_e(pourquoi)}</p>
  </div>
{"".join(blocks)}
  <footer>
    Rapport produit automatiquement par TestOps à partir du run du {_e(run.get("generated_at", ""))}.
    Les chiffres proviennent du résumé complet de l'outil d'injection, pas d'un échantillon.
  </footer>
</div>
</body>
</html>
"""


def build_run(target_id: str, target: dict, test_type: str, params: dict,
              result: dict, test_type_label: str = "") -> dict:
    """Assemble le contexte d'un run sous la forme attendue par `render`."""
    return {
        "target": target_id,
        "target_label": target.get("label", target_id),
        "base_url": target.get("base_url", ""),
        "test_type": test_type,
        "test_type_label": test_type_label or test_type,
        "params": params or {},
        "result": result or {},
        "generated_at": datetime.now().strftime("%d/%m/%Y à %H:%M"),
    }

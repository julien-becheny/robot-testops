"""Rapport HTML autonome : un fichier unique, sans dépendance, partageable par lien."""

from __future__ import annotations

import json
from pathlib import Path

from core.paths import paths

_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Couverture fonctionnelle des tests automatisés</title>
<style>
  :root { --bg:#0d1117; --panel:rgba(255,255,255,.03); --line:rgba(255,255,255,.09);
          --txt:#e6edf3; --dim:#8b949e; --ok:#3fb950; --ko:#f85149; --a1:#05bef7; --a2:#05f7c3; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt); font-size:15px;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:1080px; margin:0 auto; padding:32px 20px 64px; }
  h1 { font-size:24px; margin:0 0 4px; }
  .sub { color:var(--dim); font-size:13px; margin-bottom:24px; }
  .tools { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:20px; }
  input[type=search] { flex:1 1 280px; background:var(--panel); color:var(--txt);
        border:1px solid var(--line); border-radius:8px; padding:10px 12px; font-size:14px; }
  input[type=search]:focus { outline:none; border-color:var(--a1); }
  .chip { border:1px solid var(--line); background:transparent; color:var(--dim);
          border-radius:999px; padding:7px 14px; font-size:13px; cursor:pointer; }
  .chip.on { color:#04121a; background:linear-gradient(90deg,var(--a1),var(--a2)); border-color:transparent; }
  h2 { font-size:17px; margin:28px 0 4px; }
  h3 { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--dim);
       margin:20px 0 8px; font-weight:600; }
  .row { border:1px solid var(--line); border-radius:8px; background:var(--panel);
         margin-bottom:6px; padding:10px 14px; }
  .row > summary { display:flex; align-items:center; gap:10px; cursor:pointer; list-style:none; }
  .row > summary::-webkit-details-marker { display:none; }
  .dot { width:9px; height:9px; border-radius:50%; flex:none; }
  .dot.ok { background:var(--ok); } .dot.ko { background:var(--ko); }
  .lbl { flex:1; }
  .id { color:var(--dim); font-size:12px; font-family:ui-monospace,Consolas,monospace; }
  .tag { font-size:11px; color:var(--dim); border:1px solid var(--line);
         border-radius:4px; padding:2px 6px; }
  .cnt { font-size:12px; color:var(--dim); }
  .tests { margin:10px 0 2px 19px; padding-left:14px; border-left:1px solid var(--line); }
  .tests li { color:var(--dim); font-size:13px; margin:3px 0; list-style:none; }
  .none { color:var(--ko); font-size:13px; margin:10px 0 2px 19px; }
  .help { border:1px solid var(--line); border-radius:10px; padding:16px 18px;
          margin-top:36px; color:var(--dim); font-size:13px; line-height:1.6; }
  .help b { color:var(--txt); }
  .empty { color:var(--dim); padding:20px 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Couverture fonctionnelle des tests automatisés</h1>
  <div class="sub" id="sub"></div>

  <div class="tools">
    <input type="search" id="q" placeholder="Rechercher un écran, une popup, une fonctionnalité…" autocomplete="off">
    <button class="chip on" data-f="all">Tout</button>
    <button class="chip" data-f="non_couvert">Non couvert</button>
    <button class="chip" data-f="couvert">Couvert</button>
  </div>

  <div id="content"></div>

  <div class="help">
    <b>Comment lire ce rapport.</b><br>
    <b>Écran / popup couvert</b> = au moins un test automatisé passe dessus au cours de son scénario.<br>
    <b>Fonctionnalité couverte</b> = au moins un test déclare la vérifier explicitement - c'est plus fort
    que « traverser » : le test contrôle le résultat attendu.<br>
    <b>Non couvert</b> = l'élément existe dans le référentiel et aucun test ne l'atteint. C'est une
    absence réelle de test, pas un oubli de l'outil.<br>
    Ce rapport est issu du <b>code des tests</b>, pas d'une exécution : il dit ce qui est testé,
    pas si les tests passent actuellement.
  </div>
</div>
<script>
const DATA = __DATA__;
let filter = "all";

const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function perimetre() {
  const p = DATA.perimetre;
  document.getElementById("sub").textContent =
    `Généré le __GENERATED__ - référentiel : ${p.ecrans} écrans et popups, ${p.fonctionnalites} `
    + `fonctionnalités décrits. Ce qui n'y figure pas n'est pas évalué.`;
}

// La recherche porte sur le vocabulaire fonctionnel, JAMAIS sur les noms de tests :
// sinon un écran remonte pour un mot présent dans un test qui ne fait que le traverser.
const matches = (item, q) =>
  !q || (item.label + " " + item.id + " " + (item.type || "") + " " + (item.criticite || ""))
        .toLowerCase().includes(q);

function rows(items, key) {
  return items.map(item => {
    const ok = item.statut === "couvert";
    const tests = item[key] || [];
    const meta = [item.type, item.criticite].filter(Boolean)
      .map(v => `<span class="tag">${esc(v)}</span>`).join(" ");
    const body = ok
      ? `<ul class="tests">${tests.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`
      : `<div class="none">Aucun test automatisé.</div>`;
    return `<details class="row">
      <summary>
        <span class="dot ${ok ? "ok" : "ko"}"></span>
        <span class="lbl">${esc(item.label)} <span class="id">${esc(item.id)}</span></span>
        ${meta}
        <span class="cnt">${ok ? tests.length + " test" + (tests.length > 1 ? "s" : "") : "non couvert"}</span>
      </summary>${body}</details>`;
  }).join("");
}

function render() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const keep = item => matches(item, q) && (filter === "all" || item.statut === filter);
  let html = "";
  for (const mod of DATA.modules) {
    const ecrans = mod.ecrans.filter(keep);
    const feats = mod.fonctionnalites.filter(keep);
    if (!ecrans.length && !feats.length) continue;
    html += `<h2>${esc(mod.label)}</h2>`;
    if (ecrans.length) html += `<h3>Écrans et popups</h3>` + rows(ecrans, "atteint_par");
    if (feats.length) html += `<h3>Fonctionnalités</h3>` + rows(feats, "verifiee_par");
  }
  document.getElementById("content").innerHTML =
    html || `<div class="empty">Aucun résultat pour cette recherche.</div>`;
}

document.getElementById("q").addEventListener("input", render);
document.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", () => {
  document.querySelectorAll(".chip").forEach(c => c.classList.remove("on"));
  chip.classList.add("on");
  filter = chip.dataset.f;
  render();
}));

perimetre();
render();
</script>
</body>
</html>
"""


def render_html(report: dict) -> str:
    payload = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    generated = report.get("genere_le", "").replace("T", " à ")
    return _TEMPLATE.replace("__DATA__", payload).replace("__GENERATED__", generated)


def write_html(report: dict, destination: Path | None = None) -> Path:
    destination = destination or paths.RESULTS / "functional_coverage.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(report), encoding="utf-8")
    return destination

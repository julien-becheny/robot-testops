"""
Logique metier des campagnes de test (CRUD + construction de la matrice + stats).

Une campagne = tests (resolus par tags, figes a la creation) x cibles (choisies a
la creation). Chaque couple (test, cible) = une CELLULE a l'etat todo|passed|failed.
On grignote les cellules « todo » (l'execution arrive dans un increment suivant),
sans jamais rejouer une cellule « passed ».

La « cible » est abstraite (champ platform) : aujourd'hui web (navigateur+appareil),
demain natif (android/ios + device) sans refonte du modele.
"""

import json
import uuid
from datetime import datetime

from services.campaigns.db import get_connection
from services.tags.manager import get_matching_tests

ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}
ALLOWED_DEVICES = {"desktop", "tablet", "mobile"}
_STATUSES = {"created", "active", "closed"}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _normalize_targets(targets):
    """Valide/deduplique les cibles. Cible web = {platform:web, browser, device}."""
    normalized, seen = [], set()
    for t in targets or []:
        platform = str(t.get("platform", "web")).lower()
        browser = str(t.get("browser", "")).lower()
        device = str(t.get("device", "")).lower()
        if platform != "web":
            raise ValueError(f"Plateforme non supportee pour l'instant : {platform}")
        if browser not in ALLOWED_BROWSERS:
            raise ValueError(f"Navigateur invalide : {browser or '(vide)'}")
        if device not in ALLOWED_DEVICES:
            raise ValueError(f"Appareil invalide : {device or '(vide)'}")
        key = (platform, browser, device)
        if key not in seen:
            seen.add(key)
            normalized.append({"platform": platform, "browser": browser, "device": device})
    if not normalized:
        raise ValueError("Au moins une cible (navigateur + appareil) est requise.")
    return normalized


def create_campaign(name, include_tags=None, exclude_tags=None, targets=None, config=None):
    """Cree une campagne : resout les tests par tags, croise avec les cibles, fige la matrice."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Le nom de la campagne est requis.")
    include_tags = include_tags or []
    exclude_tags = exclude_tags or []
    targets = _normalize_targets(targets)
    config = config or {}

    tests = get_matching_tests(include_tags, exclude_tags)  # [{name, tags, file}]

    campaign_id = f"camp_{uuid.uuid4().hex[:12]}"
    now = _now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, tags_include, tags_exclude, targets, "
            "config, created_at, updated_at) VALUES (?, ?, 'created', ?, ?, ?, ?, ?, ?)",
            (campaign_id, name, json.dumps(include_tags), json.dumps(exclude_tags),
             json.dumps(targets), json.dumps(config), now, now),
        )
        cells = [
            (campaign_id, test.get("name", ""), test.get("file", ""),
             tgt["platform"], tgt["browser"], tgt["device"], "todo", now)
            for test in tests for tgt in targets
        ]
        if cells:
            conn.executemany(
                "INSERT INTO campaign_cells (campaign_id, test_name, test_file, platform, "
                "browser, device, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", cells)
    return get_campaign(campaign_id)


def list_campaigns():
    """Toutes les campagnes (plus recentes d'abord) avec leur progression."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [{**_campaign_row(c), "progress": _progress(conn, c["id"])} for c in rows]


def get_campaign(campaign_id):
    """Une campagne + sa progression (None si introuvable)."""
    with get_connection() as conn:
        c = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not c:
            return None
        return {**_campaign_row(c), "progress": _progress(conn, campaign_id)}


def get_campaign_cells(campaign_id):
    """La matrice (cellules) d'une campagne."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM campaign_cells WHERE campaign_id = ? "
            "ORDER BY test_name, browser, device", (campaign_id,)).fetchall()
        return [dict(r) for r in rows]


def set_status(campaign_id, status):
    """Transition de statut (created|active|closed). None si introuvable."""
    if status not in _STATUSES:
        raise ValueError(f"Statut invalide : {status}")
    with get_connection() as conn:
        cur = conn.execute("UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?",
                           (status, _now(), campaign_id))
        if cur.rowcount == 0:
            return None
    return get_campaign(campaign_id)


def delete_campaign(campaign_id):
    """Supprime une campagne (et ses cellules, via cascade). True si supprimee."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        return cur.rowcount > 0


def reset_failed_cells(campaign_id):
    """Remet les cellules « failed » a « todo » (rejouer les echecs).

    Renvoie le nombre de cellules remises, ou None si la campagne est introuvable.
    """
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM campaigns WHERE id = ?", (campaign_id,)).fetchone():
            return None
        cur = conn.execute(
            "UPDATE campaign_cells SET status = 'todo', updated_at = ? "
            "WHERE campaign_id = ? AND status = 'failed'", (_now(), campaign_id))
        return cur.rowcount


def _campaign_row(c):
    return {
        "id": c["id"], "name": c["name"], "status": c["status"],
        "tags_include": json.loads(c["tags_include"]),
        "tags_exclude": json.loads(c["tags_exclude"]),
        "targets": json.loads(c["targets"]),
        "config": json.loads(c["config"]),
        "created_at": c["created_at"], "updated_at": c["updated_at"],
    }


def _progress(conn, campaign_id):
    """Progression : % joue (couverture) et % valide (succes) sur la matrice."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM campaign_cells WHERE campaign_id = ? GROUP BY status",
        (campaign_id,)).fetchall()
    counts = {"todo": 0, "passed": 0, "failed": 0}
    for r in rows:
        counts[r["status"]] = r["n"]
    total = counts["todo"] + counts["passed"] + counts["failed"]
    played = counts["passed"] + counts["failed"]
    return {
        "total": total, "todo": counts["todo"],
        "passed": counts["passed"], "failed": counts["failed"], "played": played,
        "pct_played": round(100 * played / total, 1) if total else 0.0,
        "pct_passed": round(100 * counts["passed"] / total, 1) if total else 0.0,
    }

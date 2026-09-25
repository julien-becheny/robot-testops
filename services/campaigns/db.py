"""
Couche persistance SQLite pour les campagnes de test.

SQLite (et pas un fichier JSON) : agregats simples en SQL et pas de corruption en
ecriture concurrente (plusieurs sessions d'execution en parallele). La base vit
hors du repo (paths.OUTPUT_ROOT) pour survivre aux nettoyages.
"""

import sqlite3
from contextlib import contextmanager

from core.paths import paths

DB_PATH = paths.OUTPUT_ROOT / "campaigns.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'created',   -- created | active | closed
    tags_include  TEXT NOT NULL DEFAULT '[]',        -- JSON array
    tags_exclude  TEXT NOT NULL DEFAULT '[]',        -- JSON array
    targets       TEXT NOT NULL DEFAULT '[]',        -- JSON [{platform,browser,device}]
    config        TEXT NOT NULL DEFAULT '{}',        -- JSON (rerun, env, test_count...)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_cells (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id      TEXT NOT NULL,
    test_name        TEXT NOT NULL,
    test_file        TEXT,
    platform         TEXT NOT NULL DEFAULT 'web',    -- web | android | ios (extensible)
    browser          TEXT,                            -- web : chromium|firefox|webkit
    device           TEXT,                            -- web : desktop|tablet|mobile ; natif : nom
    status           TEXT NOT NULL DEFAULT 'todo',    -- todo | passed | failed
    last_session_id  TEXT,
    report_path      TEXT,
    updated_at       TEXT,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cells_campaign ON campaign_cells(campaign_id);
CREATE INDEX IF NOT EXISTS idx_cells_status ON campaign_cells(campaign_id, status);
"""


@contextmanager
def get_connection():
    """Connexion SQLite ouverte par appel (thread-safe) : rows en dict, cascade ON.

    Commit automatique en sortie ; rollback si exception.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Cree les tables si absentes (idempotent)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


# Initialise au chargement du module (le backend l'importe au demarrage).
init_db()

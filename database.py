"""
database.py - SQLite schema and connection helpers for FIR-X
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "firx.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── Districts & Police Stations ──────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS districts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS police_stations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        district_id INTEGER NOT NULL REFERENCES districts(id),
        UNIQUE(name, district_id)
    );

    -- ── FIR Master ───────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS firs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fir_number      TEXT NOT NULL UNIQUE,
        date_of_fir     TEXT NOT NULL,          -- ISO date YYYY-MM-DD
        date_of_offence TEXT,
        police_station_id INTEGER NOT NULL REFERENCES police_stations(id),
        section_of_law  TEXT,
        crime_type      TEXT NOT NULL,
        modus_operandi  TEXT,
        location        TEXT,                   -- place/scene of offence from CSV
        description     TEXT,                   -- raw_text narrative
        status          TEXT DEFAULT 'Open' CHECK(status IN ('Open','Under Investigation','Chargesheeted','Closed')),
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );

    -- ── Accused ──────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS accused (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fir_id          INTEGER NOT NULL REFERENCES firs(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        alias           TEXT,
        age             INTEGER,
        gender          TEXT CHECK(gender IN ('Male','Female','Other','Unknown')),
        address         TEXT,
        district_id     INTEGER REFERENCES districts(id),   -- home district
        occupation      TEXT,
        prior_offences  INTEGER DEFAULT 0,
        aadhar_number   TEXT,
        mobile_number   TEXT
    );

    -- ── Victims ──────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS victims (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fir_id          INTEGER NOT NULL REFERENCES firs(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        age             INTEGER,
        gender          TEXT CHECK(gender IN ('Male','Female','Other','Unknown')),
        address         TEXT,
        occupation      TEXT,
        injury_type     TEXT CHECK(injury_type IN ('None','Minor','Grievous','Fatal','Unknown')),
        mobile_number   TEXT
    );

    -- ── Alerts ───────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        type        TEXT NOT NULL,   -- 'repeat_offender'|'mo_spike'|'district_spread'|'crime_spike'
        severity    TEXT NOT NULL DEFAULT 'Medium' CHECK(severity IN ('High','Medium','Low')),
        title       TEXT NOT NULL,
        detail      TEXT,
        entity_name TEXT,            -- accused name / crime type / MO text
        fir_count   INTEGER,
        is_read     INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    -- ── Audit Log ─────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS fir_audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        fir_id      INTEGER NOT NULL REFERENCES firs(id) ON DELETE CASCADE,
        action      TEXT NOT NULL,   -- 'created'|'updated'|'status_changed'|'deleted'
        actor       TEXT DEFAULT 'officer',
        old_status  TEXT,
        new_status  TEXT,
        note        TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    -- ── Indexes ──────────────────────────────────────────────────────────────
    CREATE INDEX IF NOT EXISTS idx_firs_station  ON firs(police_station_id);
    CREATE INDEX IF NOT EXISTS idx_firs_date     ON firs(date_of_fir);
    CREATE INDEX IF NOT EXISTS idx_firs_crime    ON firs(crime_type);
    CREATE INDEX IF NOT EXISTS idx_accused_name  ON accused(name);
    CREATE INDEX IF NOT EXISTS idx_accused_fir   ON accused(fir_id);
    CREATE INDEX IF NOT EXISTS idx_victims_fir   ON victims(fir_id);
    CREATE INDEX IF NOT EXISTS idx_alerts_read   ON alerts(is_read);
    CREATE INDEX IF NOT EXISTS idx_audit_fir     ON fir_audit_log(fir_id);
    """)

    conn.commit()

    # ── Live migrations for existing DBs ──────────────────────────────────────
    cols = [r[1] for r in conn.execute("PRAGMA table_info(firs)").fetchall()]
    if "location" not in cols:
        conn.execute("ALTER TABLE firs ADD COLUMN location TEXT")
        conn.commit()

    # ── Live migration: fir_audit_log ─────────────────────────────────────────
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if "fir_audit_log" not in tables:
        conn.execute("""
            CREATE TABLE fir_audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fir_id      INTEGER NOT NULL REFERENCES firs(id) ON DELETE CASCADE,
                action      TEXT NOT NULL,
                actor       TEXT DEFAULT 'officer',
                old_status  TEXT,
                new_status  TEXT,
                note        TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX idx_audit_fir ON fir_audit_log(fir_id)")
        conn.commit()

    conn.close()
    print("[DB] Schema initialised ->", DB_PATH)


# ── Helpers ──────────────────────────────────────────────────────────────────

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def get_or_create_district(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM districts WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO districts(name) VALUES(?)", (name,))
    return cur.lastrowid


def get_or_create_station(conn, station_name: str, district_name: str) -> int:
    dist_id = get_or_create_district(conn, district_name)
    row = conn.execute(
        "SELECT id FROM police_stations WHERE name=? AND district_id=?",
        (station_name, dist_id)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO police_stations(name, district_id) VALUES(?,?)",
        (station_name, dist_id)
    )
    return cur.lastrowid


def audit_log(conn, fir_id: int, action: str,
              old_status: str = None, new_status: str = None,
              note: str = None, actor: str = "officer"):
    """Write one audit trail entry. Does NOT commit — caller must commit."""
    conn.execute(
        """INSERT INTO fir_audit_log
             (fir_id, action, actor, old_status, new_status, note)
           VALUES (?,?,?,?,?,?)""",
        (fir_id, action, actor, old_status, new_status, note),
    )


def fir_full(conn, fir_id: int) -> dict | None:
    """Return a complete FIR record with station, district, accused and victims."""
    fir = row_to_dict(conn.execute("""
        SELECT f.*,
               ps.name  AS station_name,
               d.name   AS district_name
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        WHERE  f.id = ?
    """, (fir_id,)).fetchone())

    if fir is None:
        return None

    fir["accused"] = rows_to_list(
        conn.execute("SELECT * FROM accused WHERE fir_id=?", (fir_id,)).fetchall()
    )
    fir["victims"] = rows_to_list(
        conn.execute("SELECT * FROM victims WHERE fir_id=?", (fir_id,)).fetchall()
    )
    return fir


if __name__ == "__main__":
    init_db()

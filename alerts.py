"""
alerts.py  -  FIR-X Alert Engine
Runs rules against the DB and inserts alerts for:
  1. repeat_offender  - accused with >= 3 FIRs
  2. district_spread  - accused active in >= 3 districts
  3. mo_spike         - same modus operandi used in 3+ different districts in last 60 days
  4. crime_spike      - any crime type up >= 40% month-over-month (last 2 complete months)

Call run_alert_engine(conn) after every CSV import or FIR creation.
Existing identical alerts (same type + entity_name) are not duplicated.
"""

from datetime import datetime, timedelta


def _already_exists(conn, alert_type: str, entity_name: str) -> bool:
    row = conn.execute(
        "SELECT id FROM alerts WHERE type=? AND entity_name=?",
        (alert_type, entity_name),
    ).fetchone()
    return row is not None


def _insert(conn, alert_type: str, severity: str, title: str,
            detail: str, entity_name: str, fir_count: int):
    if _already_exists(conn, alert_type, entity_name):
        # Update fir_count and un-read if count grew
        conn.execute(
            """UPDATE alerts SET fir_count=?, is_read=0, created_at=datetime('now')
               WHERE type=? AND entity_name=?""",
            (fir_count, alert_type, entity_name),
        )
    else:
        conn.execute(
            """INSERT INTO alerts (type,severity,title,detail,entity_name,fir_count)
               VALUES (?,?,?,?,?,?)""",
            (alert_type, severity, title, detail, entity_name, fir_count),
        )


def run_alert_engine(conn):
    """Run all rules. Call after any DB mutation. Commits internally."""

    # ── Rule 1: Repeat offenders (>= 3 FIRs) ─────────────────────────────────
    rows = conn.execute("""
        SELECT a.name,
               COUNT(DISTINCT a.fir_id) AS cnt,
               GROUP_CONCAT(DISTINCT d.name) AS districts,
               GROUP_CONCAT(DISTINCT f.crime_type) AS crimes
        FROM   accused a
        JOIN   firs f ON f.id=a.fir_id
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d ON d.id=ps.district_id
        GROUP  BY a.name
        HAVING cnt >= 3
    """).fetchall()

    for r in rows:
        severity = "High" if r["cnt"] >= 5 else "Medium"
        _insert(conn,
                "repeat_offender", severity,
                f"Repeat Offender: {r['name']}",
                f"Linked to {r['cnt']} FIRs across {r['districts']}. Crimes: {r['crimes']}.",
                r["name"], r["cnt"])

    # ── Rule 2: Inter-district spread (>= 3 districts) ────────────────────────
    rows = conn.execute("""
        SELECT a.name,
               COUNT(DISTINCT d.id) AS dcnt,
               COUNT(DISTINCT a.fir_id) AS fcnt,
               GROUP_CONCAT(DISTINCT d.name) AS districts
        FROM   accused a
        JOIN   firs f ON f.id=a.fir_id
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d ON d.id=ps.district_id
        GROUP  BY a.name
        HAVING dcnt >= 3
    """).fetchall()

    for r in rows:
        _insert(conn,
                "district_spread", "High",
                f"Inter-District Offender: {r['name']}",
                f"Active across {r['dcnt']} districts: {r['districts']}. Total FIRs: {r['fcnt']}.",
                r["name"], r["fcnt"])

    # ── Rule 3: MO spike — same MO in >= 3 districts in last 60 days ──────────
    cutoff = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT f.modus_operandi AS mo,
               COUNT(DISTINCT d.id) AS dcnt,
               COUNT(*) AS cnt,
               GROUP_CONCAT(DISTINCT d.name) AS districts
        FROM   firs f
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d ON d.id=ps.district_id
        WHERE  f.modus_operandi IS NOT NULL
          AND  f.modus_operandi != ''
          AND  f.date_of_fir >= ?
        GROUP  BY f.modus_operandi
        HAVING dcnt >= 3
    """, (cutoff,)).fetchall()

    for r in rows:
        _insert(conn,
                "mo_spike", "High",
                f"MO Spreading Across Districts: {r['mo'][:60]}",
                f"Used in {r['cnt']} FIRs across {r['dcnt']} districts ({r['districts']}) in last 60 days.",
                r["mo"], r["cnt"])

    # ── Rule 4: Crime spike >= 40% MoM ────────────────────────────────────────
    # Compare last complete month vs the one before it
    rows = conn.execute("""
        SELECT crime_type,
               strftime('%Y-%m', date_of_fir) AS month,
               COUNT(*) AS cnt
        FROM   firs
        GROUP  BY crime_type, month
        ORDER  BY month DESC
    """).fetchall()

    # Build {crime_type: [(month, cnt), ...]}
    by_crime: dict = {}
    for r in rows:
        by_crime.setdefault(r["crime_type"], []).append((r["month"], r["cnt"]))

    for crime, months in by_crime.items():
        if len(months) < 2:
            continue
        last_cnt  = months[0][1]
        prev_cnt  = months[1][1]
        if prev_cnt > 0:
            pct = (last_cnt - prev_cnt) / prev_cnt * 100
            if pct >= 40:
                _insert(conn,
                        "crime_spike", "Medium",
                        f"Crime Spike: {crime}",
                        f"{crime} rose {pct:.0f}% from {months[1][0]} ({prev_cnt}) to {months[0][0]} ({last_cnt}).",
                        crime, last_cnt)

    conn.commit()

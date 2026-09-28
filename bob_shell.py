#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bob_shell.py - FIR-X Crime Intelligence Shell
Bob-powered CLI for analysing CCTNS/FIR data.

Usage:
    python bob_shell.py                     # interactive menu
    python bob_shell.py --report all        # print full intelligence report
    python bob_shell.py --report repeat     # repeat offenders only
    python bob_shell.py --report interdist  # inter-district offenders only
    python bob_shell.py --report hotspots   # crime hotspots
    python bob_shell.py --report mo         # top modus operandi
    python bob_shell.py --report patterns   # rising crime patterns
    python bob_shell.py --search "Ravi"     # search accused by name
"""

import argparse, sys, os
from datetime import datetime
from database import get_conn, init_db

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from tabulate import tabulate
except ImportError:
    def tabulate(data, headers=(), tablefmt="simple", **kw):
        lines = ["\t".join(str(h) for h in headers)]
        for row in data:
            lines.append("\t".join(str(c) for c in row))
        return "\n".join(lines)

# ── ANSI colours ─────────────────────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def c(text, colour): return f"{colour}{text}{RESET}"
def header(title):
    w = 72
    print()
    print(c("-" * w, DIM))
    print(c(f"  {title}", BOLD + CYAN))
    print(c("-" * w, DIM))

def banner():
    print(c("""
  +------------------------------------------+
  |   F I R - X   CRIME INTELLIGENCE          |
  |   Bob Shell  |  CCTNS / FIR Analytics     |
  +------------------------------------------+
""", CYAN + BOLD))
    print(c("  Crime Intelligence Shell  |  CCTNS FIR Analytics", BLUE))
    print(c("  " + datetime.now().strftime("%A, %d %B %Y  %H:%M:%S"), DIM))
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYTICS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def db_summary(conn):
    header("📊  DATABASE SUMMARY")
    n_firs    = conn.execute("SELECT COUNT(*) FROM firs").fetchone()[0]
    n_open    = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Open'").fetchone()[0]
    n_invest  = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Under Investigation'").fetchone()[0]
    n_cs      = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Chargesheeted'").fetchone()[0]
    n_closed  = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Closed'").fetchone()[0]
    n_accused = conn.execute("SELECT COUNT(*) FROM accused").fetchone()[0]
    n_victims = conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0]
    n_dist    = conn.execute("SELECT COUNT(*) FROM districts").fetchone()[0]
    n_sta     = conn.execute("SELECT COUNT(*) FROM police_stations").fetchone()[0]

    rows = [
        ["Total FIRs",          c(str(n_firs), BOLD)],
        ["  → Open",            c(str(n_open), RED)],
        ["  → Under Investigation", c(str(n_invest), YELLOW)],
        ["  → Chargesheeted",   c(str(n_cs), CYAN)],
        ["  → Closed",          c(str(n_closed), GREEN)],
        ["Total Accused",       str(n_accused)],
        ["Total Victims",       str(n_victims)],
        ["Districts Covered",   str(n_dist)],
        ["Police Stations",     str(n_sta)],
    ]
    print(tabulate(rows, tablefmt="simple"))


def repeated_offenders(conn, top=15):
    header("🔁  REPEAT OFFENDERS")
    rows = conn.execute("""
        SELECT a.name,
               a.alias,
               COUNT(DISTINCT a.fir_id)             AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type)  AS crimes,
               GROUP_CONCAT(DISTINCT d.name)         AS districts,
               MAX(a.prior_offences)                 AS prior
        FROM   accused a
        JOIN   firs f    ON f.id = a.fir_id
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        GROUP  BY a.name
        HAVING fir_count > 1
        ORDER  BY fir_count DESC
        LIMIT  ?
    """, (top,)).fetchall()

    if not rows:
        print(c("  No repeat offenders found in current dataset.", DIM))
        return

    table = []
    for i, r in enumerate(rows, 1):
        name  = c(r[0], BOLD + RED)
        alias = f"({r[1]})" if r[1] else ""
        cnt   = c(str(r[2]), RED + BOLD)
        table.append([i, f"{name} {alias}", cnt, r[3] or "—", r[4] or "—", r[5]])

    print(tabulate(table,
        headers=["#", "Name (Alias)", "FIRs", "Crime Types", "Districts Active", "Prior Offences"],
        tablefmt="rounded_outline"))
    print(c(f"\n  ⚠  {len(rows)} repeat offenders identified", YELLOW))


def inter_district_offenders(conn, top=15):
    header("🗺️   INTER-DISTRICT OFFENDERS")
    rows = conn.execute("""
        SELECT a.name,
               COUNT(DISTINCT d.id)                  AS dist_count,
               GROUP_CONCAT(DISTINCT d.name)          AS districts,
               COUNT(DISTINCT a.fir_id)               AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type)    AS crimes
        FROM   accused a
        JOIN   firs f    ON f.id = a.fir_id
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        GROUP  BY a.name
        HAVING dist_count > 1
        ORDER  BY dist_count DESC, fir_count DESC
        LIMIT  ?
    """, (top,)).fetchall()

    if not rows:
        print(c("  No inter-district offenders found.", DIM))
        return

    table = []
    for i, r in enumerate(rows, 1):
        name   = c(r[0], BOLD + YELLOW)
        dcnt   = c(str(r[1]), YELLOW + BOLD)
        table.append([i, name, dcnt, r[2] or "—", r[3], r[4] or "—"])

    print(tabulate(table,
        headers=["#", "Name", "Districts", "District List", "Total FIRs", "Crime Types"],
        tablefmt="rounded_outline"))
    print(c(f"\n  ⚠  {len(rows)} offenders operated across multiple districts", YELLOW))


def crime_hotspots(conn, top=15):
    header("🔥  CRIME HOTSPOTS")
    rows = conn.execute("""
        SELECT d.name         AS district,
               ps.name        AS station,
               COUNT(*)       AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type) AS crimes
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        GROUP  BY d.id, ps.id
        ORDER  BY fir_count DESC
        LIMIT  ?
    """, (top,)).fetchall()

    if not rows:
        print(c("  No data available.", DIM))
        return

    max_cnt = rows[0][2]
    table   = []
    for i, r in enumerate(rows, 1):
        bar   = "█" * int(r[2] / max_cnt * 20)
        cnt   = c(str(r[2]), RED if i <= 3 else YELLOW if i <= 7 else RESET)
        table.append([i, c(r[0], BOLD), r[1], cnt, bar, r[3] or "—"])

    print(tabulate(table,
        headers=["#", "District", "Police Station", "FIRs", "Intensity", "Top Crimes"],
        tablefmt="rounded_outline"))


def top_modus_operandi(conn, top=10):
    header("🎭  TOP MODUS OPERANDI")
    rows = conn.execute("""
        SELECT modus_operandi,
               COUNT(*) AS count,
               GROUP_CONCAT(DISTINCT crime_type) AS crimes,
               GROUP_CONCAT(DISTINCT d.name)     AS districts
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        WHERE  modus_operandi IS NOT NULL AND modus_operandi != ''
        GROUP  BY modus_operandi
        ORDER  BY count DESC
        LIMIT  ?
    """, (top,)).fetchall()

    if not rows:
        print(c("  No modus operandi data available.", DIM))
        return

    max_cnt = rows[0][1]
    table   = []
    for i, r in enumerate(rows, 1):
        bar   = "▓" * int(r[1] / max_cnt * 18)
        cnt   = c(str(r[1]), BOLD)
        table.append([i, r[0], cnt, bar, r[2] or "—"])

    print(tabulate(table,
        headers=["#", "Modus Operandi", "Cases", "Frequency", "Associated Crimes"],
        tablefmt="rounded_outline"))


def rising_crime_patterns(conn):
    header("📈  RISING CRIME PATTERNS  (Monthly Trend)")
    rows = conn.execute("""
        SELECT strftime('%Y-%m', date_of_fir) AS month,
               crime_type,
               COUNT(*) AS count
        FROM   firs
        GROUP  BY month, crime_type
        ORDER  BY month ASC
    """).fetchall()

    if not rows:
        print(c("  No pattern data available.", DIM))
        return

    # Pivot: month × crime_type
    months     = sorted(set(r[0] for r in rows))
    crime_types= sorted(set(r[1] for r in rows))
    data       = {(r[0], r[1]): r[2] for r in rows}

    # Compute month-over-month growth per crime type
    growth = {}
    for ct in crime_types:
        vals = [data.get((m, ct), 0) for m in months]
        if len(vals) >= 2 and vals[-2] > 0:
            growth[ct] = round((vals[-1] - vals[-2]) / vals[-2] * 100, 1)
        else:
            growth[ct] = 0.0

    # Print mini sparklines (last 6 months)
    last6 = months[-6:]
    table = []
    for ct in sorted(crime_types, key=lambda x: -sum(data.get((m, x), 0) for m in last6)):
        vals = [data.get((m, ct), 0) for m in last6]
        spark = " ".join(_spark(v, max(vals) if max(vals) > 0 else 1) for v in vals)
        total = sum(data.get((m, ct), 0) for m in months)
        g = growth[ct]
        trend = c(f"▲ {g}%", GREEN) if g > 10 else c(f"▼ {abs(g)}%", RED) if g < -10 else c(f"→ {g}%", YELLOW)
        table.append([ct, str(total), spark, trend])

    print(f"  Period: {months[0] if months else '—'}  →  {months[-1] if months else '—'}  ({len(months)} months)")
    print()
    print(tabulate(table,
        headers=["Crime Type", "Total FIRs", f"Last {len(last6)} Months (sparkline)", "MoM Trend"],
        tablefmt="rounded_outline"))

    # Rising crimes
    rising = [(ct, growth[ct]) for ct in crime_types if growth[ct] > 15]
    if rising:
        print()
        print(c("  🚨 RAPIDLY RISING CRIMES (>15% MoM growth):", RED + BOLD))
        for ct, g in sorted(rising, key=lambda x: -x[1]):
            print(f"      {c('▲', RED)}  {ct}  +{g}%")


def _spark(val, max_val):
    """ASCII spark bar character based on relative value."""
    chars = ["▁","▂","▃","▄","▅","▆","▇","█"]
    if max_val == 0: return "▁"
    idx = int(val / max_val * (len(chars) - 1))
    return chars[idx]


def search_accused(conn, name_query):
    header(f"🔎  SEARCH ACCUSED: \"{name_query}\"")
    rows = conn.execute("""
        SELECT a.name, a.alias, a.age, a.gender,
               f.fir_number, f.crime_type, f.date_of_fir,
               ps.name AS station, d.name AS district
        FROM   accused a
        JOIN   firs f             ON f.id  = a.fir_id
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        WHERE  a.name LIKE ? OR a.alias LIKE ?
        ORDER  BY a.name, f.date_of_fir DESC
    """, (f"%{name_query}%", f"%{name_query}%")).fetchall()

    if not rows:
        print(c(f"  No accused matching '{name_query}' found.", DIM))
        return

    table = [[r[0], r[1] or "—", r[2] or "—", r[3], r[4], r[5], r[6], r[7], r[8]] for r in rows]
    print(tabulate(table,
        headers=["Name", "Alias", "Age", "Gender", "FIR Number", "Crime", "Date", "Station", "District"],
        tablefmt="rounded_outline"))
    print(c(f"\n  Found {len(rows)} record(s)", GREEN))


def full_report(conn):
    db_summary(conn)
    repeated_offenders(conn)
    inter_district_offenders(conn)
    crime_hotspots(conn)
    top_modus_operandi(conn)
    rising_crime_patterns(conn)


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE MENU
# ═══════════════════════════════════════════════════════════════════════════════

MENU_OPTIONS = {
    "1": ("[1] Database Summary",             lambda c: db_summary(c)),
    "2": ("[2] Repeat Offenders",             lambda c: repeated_offenders(c)),
    "3": ("[3] Inter-District Offenders",     lambda c: inter_district_offenders(c)),
    "4": ("[4] Crime Hotspots",               lambda c: crime_hotspots(c)),
    "5": ("[5] Top Modus Operandi",           lambda c: top_modus_operandi(c)),
    "6": ("[6] Rising Crime Patterns",        lambda c: rising_crime_patterns(c)),
    "7": ("[7] Search Accused by Name",       None),
    "8": ("[8] Full Intelligence Report",     lambda c: full_report(c)),
    "0": ("[0] Exit",                         None),
}


def interactive_menu():
    banner()
    init_db()
    conn = get_conn()

    while True:
        print()
        print(c("  +========================================+", DIM))
        print(c("  |  ", DIM) + c("FIR-X INTELLIGENCE MENU", BOLD + CYAN) + c("           |", DIM))
        print(c("  +========================================+", DIM))
        for k, (label, _) in MENU_OPTIONS.items():
            print(f"   {c(k, YELLOW)}  {label}")
        print()

        choice = input(c("  >> Enter option: ", BOLD)).strip()

        if choice == "0":
            print(c("\n  Session closed. Stay vigilant.", DIM))
            print()
            conn.close()
            sys.exit(0)
        elif choice == "7":
            q = input(c("  Enter accused name/alias to search: ", BOLD)).strip()
            if q:
                search_accused(conn, q)
        elif choice in MENU_OPTIONS:
            _, fn = MENU_OPTIONS[choice]
            if fn:
                fn(conn)
        else:
            print(c("  Invalid option. Try again.", RED))


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FIR-X Bob Shell – Crime Intelligence CLI")
    parser.add_argument("--report", choices=["all","repeat","interdist","hotspots","mo","patterns","summary"],
                        help="Run a specific report non-interactively")
    parser.add_argument("--search", metavar="NAME", help="Search accused by name")
    parser.add_argument("--top",    type=int, default=15, help="Limit results (default 15)")
    args = parser.parse_args()

    init_db()
    conn = get_conn()

    if args.search:
        banner()
        search_accused(conn, args.search)
    elif args.report:
        banner()
        dispatch = {
            "all":      lambda: full_report(conn),
            "summary":  lambda: db_summary(conn),
            "repeat":   lambda: repeated_offenders(conn, args.top),
            "interdist":lambda: inter_district_offenders(conn, args.top),
            "hotspots": lambda: crime_hotspots(conn, args.top),
            "mo":       lambda: top_modus_operandi(conn, args.top),
            "patterns": lambda: rising_crime_patterns(conn),
        }
        dispatch[args.report]()
        print()
    else:
        interactive_menu()

    conn.close()

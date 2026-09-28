"""
app.py  -  FIR-X Flask backend
Run: python app.py
"""

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import sqlite3, os, json, re, urllib.request, urllib.error
from database import get_conn, init_db, rows_to_list, row_to_dict, fir_full, get_or_create_station, audit_log, get_or_create_district
from csv_import import import_csv, preview_csv
from alerts import run_alert_engine
from geocode import get_coords
from pdf_export import fir_report, analytics_report

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ── Initialise DB on startup ─────────────────────────────────────────────────
init_db()


# ── Serve frontend ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ═══════════════════════════════════════════════════════════════════════════════
#  FIR  CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/firs", methods=["GET"])
def list_firs():
    conn = get_conn()
    q = request.args

    filters, params = [], []

    if q.get("search"):
        term = f"%{q['search']}%"
        filters.append("""(f.fir_number LIKE ? OR f.crime_type LIKE ?
                         OR d.name LIKE ? OR ps.name LIKE ?
                         OR f.modus_operandi LIKE ?)""")
        params.extend([term, term, term, term, term])

    if q.get("district"):
        filters.append("d.name = ?")
        params.append(q["district"])

    if q.get("crime_type"):
        filters.append("f.crime_type = ?")
        params.append(q["crime_type"])

    if q.get("status"):
        filters.append("f.status = ?")
        params.append(q["status"])

    if q.get("from_date"):
        filters.append("f.date_of_fir >= ?")
        params.append(q["from_date"])

    if q.get("to_date"):
        filters.append("f.date_of_fir <= ?")
        params.append(q["to_date"])

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    sql = f"""
        SELECT f.id, f.fir_number, f.date_of_fir, f.crime_type,
               f.modus_operandi, f.location, f.status,
               ps.name AS station_name, d.name AS district_name
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        {where}
        ORDER BY f.date_of_fir DESC
        LIMIT ? OFFSET ?
    """
    page  = max(int(q.get("page", 1)), 1)
    limit = int(q.get("limit", 20))
    params.extend([limit, (page - 1) * limit])

    rows  = rows_to_list(conn.execute(sql, params).fetchall())

    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        {where}
    """
    total = conn.execute(count_sql, params[:-2]).fetchone()["cnt"]
    conn.close()
    return jsonify({"data": rows, "total": total, "page": page, "limit": limit})


@app.route("/api/firs/<int:fir_id>", methods=["GET"])
def get_fir(fir_id):
    conn = get_conn()
    fir  = fir_full(conn, fir_id)
    conn.close()
    if not fir:
        return jsonify({"error": "Not found"}), 404
    return jsonify(fir)


@app.route("/api/firs", methods=["POST"])
def create_fir():
    data = request.json
    conn = get_conn()
    try:
        station_id = get_or_create_station(
            conn,
            data["police_station"],
            data["district"]
        )
        cur = conn.execute("""
            INSERT INTO firs
              (fir_number, date_of_fir, date_of_offence,
               police_station_id, section_of_law,
               crime_type, modus_operandi, location, description, status)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            data["fir_number"],
            data["date_of_fir"],
            data.get("date_of_offence"),
            station_id,
            data.get("section_of_law"),
            data["crime_type"],
            data.get("modus_operandi"),
            data.get("location"),
            data.get("description"),
            data.get("status", "Open"),
        ))
        fir_id = cur.lastrowid
        audit_log(conn, fir_id, "created", new_status=data.get("status", "Open"))

        for acc in data.get("accused", []):
            dist_id = None
            if acc.get("district"):
                dist_id = get_or_create_district(conn, acc["district"])
            conn.execute("""
                INSERT INTO accused
                  (fir_id, name, alias, age, gender, address,
                   district_id, occupation, prior_offences, aadhar_number, mobile_number)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fir_id,
                acc["name"],
                acc.get("alias"),
                acc.get("age"),
                acc.get("gender", "Unknown"),
                acc.get("address"),
                dist_id,
                acc.get("occupation"),
                acc.get("prior_offences", 0),
                acc.get("aadhar_number"),
                acc.get("mobile_number"),
            ))

        for vic in data.get("victims", []):
            conn.execute("""
                INSERT INTO victims
                  (fir_id, name, age, gender, address,
                   occupation, injury_type, mobile_number)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                fir_id,
                vic["name"],
                vic.get("age"),
                vic.get("gender", "Unknown"),
                vic.get("address"),
                vic.get("occupation"),
                vic.get("injury_type", "Unknown"),
                vic.get("mobile_number"),
            ))

        conn.commit()
        run_alert_engine(conn)
        fir = fir_full(conn, fir_id)
        conn.close()
        return jsonify(fir), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 400


@app.route("/api/firs/<int:fir_id>", methods=["PUT"])
def update_fir(fir_id):
    data = request.json
    conn = get_conn()
    try:
        existing = row_to_dict(conn.execute("SELECT * FROM firs WHERE id=?", (fir_id,)).fetchone())
        if not existing:
            conn.close()
            return jsonify({"error": "Not found"}), 404

        station_id = get_or_create_station(
            conn,
            data.get("police_station", ""),
            data.get("district", "")
        )

        conn.execute("""
            UPDATE firs SET
              fir_number=?, date_of_fir=?, date_of_offence=?,
              police_station_id=?, section_of_law=?,
              crime_type=?, modus_operandi=?, location=?, description=?, status=?,
              updated_at=datetime('now')
            WHERE id=?
        """, (
            data.get("fir_number", existing["fir_number"]),
            data.get("date_of_fir", existing["date_of_fir"]),
            data.get("date_of_offence", existing.get("date_of_offence")),
            station_id,
            data.get("section_of_law", existing.get("section_of_law")),
            data.get("crime_type", existing["crime_type"]),
            data.get("modus_operandi", existing.get("modus_operandi")),
            data.get("location", existing.get("location")),
            data.get("description", existing.get("description")),
            data.get("status", existing["status"]),
            fir_id,
        ))

        # replace accused + victims lists if provided
        old_status = existing.get("status")
        new_status = data.get("status", old_status)
        note = "status changed" if old_status != new_status else "updated"
        audit_log(conn, fir_id, "status_changed" if old_status != new_status else "updated",
                  old_status=old_status, new_status=new_status, note=note)

        if "accused" in data:
            conn.execute("DELETE FROM accused WHERE fir_id=?", (fir_id,))
            for acc in data["accused"]:
                dist_id = None
                if acc.get("district"):
                    dist_id = get_or_create_district(conn, acc["district"])
                conn.execute("""
                    INSERT INTO accused
                      (fir_id, name, alias, age, gender, address,
                       district_id, occupation, prior_offences, aadhar_number, mobile_number)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    fir_id, acc["name"], acc.get("alias"), acc.get("age"),
                    acc.get("gender", "Unknown"), acc.get("address"), dist_id,
                    acc.get("occupation"), acc.get("prior_offences", 0),
                    acc.get("aadhar_number"), acc.get("mobile_number"),
                ))

        if "victims" in data:
            conn.execute("DELETE FROM victims WHERE fir_id=?", (fir_id,))
            for vic in data["victims"]:
                conn.execute("""
                    INSERT INTO victims
                      (fir_id, name, age, gender, address,
                       occupation, injury_type, mobile_number)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    fir_id, vic["name"], vic.get("age"),
                    vic.get("gender", "Unknown"), vic.get("address"),
                    vic.get("occupation"), vic.get("injury_type", "Unknown"),
                    vic.get("mobile_number"),
                ))

        conn.commit()
        run_alert_engine(conn)
        fir = fir_full(conn, fir_id)
        conn.close()
        return jsonify(fir)
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 400


@app.route("/api/firs/<int:fir_id>", methods=["DELETE"])
def delete_fir(fir_id):
    conn = get_conn()
    fir = row_to_dict(conn.execute("SELECT fir_number, status FROM firs WHERE id=?", (fir_id,)).fetchone())
    if fir:
        audit_log(conn, fir_id, "deleted", old_status=fir["status"],
                  note=f"FIR {fir['fir_number']} deleted")
        conn.commit()
    conn.execute("DELETE FROM firs WHERE id=?", (fir_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"})


# ═══════════════════════════════════════════════════════════════════════════════
#  REFERENCE DATA
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/districts", methods=["GET"])
def list_districts():
    conn = get_conn()
    rows = rows_to_list(conn.execute("SELECT * FROM districts ORDER BY name").fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/stations", methods=["GET"])
def list_stations():
    conn = get_conn()
    district = request.args.get("district")
    if district:
        rows = rows_to_list(conn.execute("""
            SELECT ps.*, d.name AS district_name
            FROM police_stations ps
            JOIN districts d ON d.id=ps.district_id
            WHERE d.name=? ORDER BY ps.name
        """, (district,)).fetchall())
    else:
        rows = rows_to_list(conn.execute("""
            SELECT ps.*, d.name AS district_name
            FROM police_stations ps
            JOIN districts d ON d.id=ps.district_id
            ORDER BY ps.name
        """).fetchall())
    conn.close()
    return jsonify(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYTICS  (feeds the Bob shell + dashboard charts)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/repeated_offenders", methods=["GET"])
def repeated_offenders():
    conn = get_conn()
    limit = int(request.args.get("limit", 20))
    rows = rows_to_list(conn.execute("""
        SELECT a.name,
               a.alias,
               COUNT(DISTINCT a.fir_id) AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type)  AS crime_types,
               GROUP_CONCAT(DISTINCT d2.name)        AS districts,
               MAX(a.prior_offences)                 AS prior_offences
        FROM   accused a
        JOIN   firs f           ON f.id = a.fir_id
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d2     ON d2.id = ps.district_id
        GROUP  BY a.name
        HAVING fir_count > 1
        ORDER  BY fir_count DESC
        LIMIT  ?
    """, (limit,)).fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/analytics/inter_district_offenders", methods=["GET"])
def inter_district_offenders():
    conn = get_conn()
    limit = int(request.args.get("limit", 20))
    rows = rows_to_list(conn.execute("""
        SELECT a.name,
               COUNT(DISTINCT d2.id)                 AS district_count,
               GROUP_CONCAT(DISTINCT d2.name)         AS districts,
               COUNT(DISTINCT a.fir_id)               AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type)    AS crime_types
        FROM   accused a
        JOIN   firs f           ON f.id = a.fir_id
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d2     ON d2.id = ps.district_id
        GROUP  BY a.name
        HAVING district_count > 1
        ORDER  BY district_count DESC, fir_count DESC
        LIMIT  ?
    """, (limit,)).fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/analytics/crime_patterns", methods=["GET"])
def crime_patterns():
    """Monthly crime counts per crime type for trend analysis."""
    conn = get_conn()
    rows = rows_to_list(conn.execute("""
        SELECT strftime('%Y-%m', date_of_fir) AS month,
               crime_type,
               COUNT(*) AS count
        FROM   firs
        GROUP  BY month, crime_type
        ORDER  BY month ASC
    """).fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/analytics/hotspots", methods=["GET"])
def crime_hotspots():
    conn = get_conn()
    rows = rows_to_list(conn.execute("""
        SELECT d.name AS district,
               ps.name AS station,
               COUNT(*) AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type) AS crime_types
        FROM   firs f
        JOIN   police_stations ps ON ps.id = f.police_station_id
        JOIN   districts d        ON d.id  = ps.district_id
        GROUP  BY d.id, ps.id
        ORDER  BY fir_count DESC
        LIMIT  20
    """).fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/analytics/modus_operandi", methods=["GET"])
def top_modus_operandi():
    conn = get_conn()
    limit = int(request.args.get("limit", 10))
    rows = rows_to_list(conn.execute("""
        SELECT modus_operandi,
               COUNT(*) AS count,
               GROUP_CONCAT(DISTINCT crime_type) AS crime_types
        FROM   firs
        WHERE  modus_operandi IS NOT NULL AND modus_operandi != ''
        GROUP  BY modus_operandi
        ORDER  BY count DESC
        LIMIT  ?
    """, (limit,)).fetchall())
    conn.close()
    return jsonify(rows)


@app.route("/api/analytics/summary", methods=["GET"])
def summary():
    conn = get_conn()
    total_firs    = conn.execute("SELECT COUNT(*) AS n FROM firs").fetchone()["n"]
    open_firs     = conn.execute("SELECT COUNT(*) AS n FROM firs WHERE status='Open'").fetchone()["n"]
    total_accused = conn.execute("SELECT COUNT(*) AS n FROM accused").fetchone()["n"]
    total_victims = conn.execute("SELECT COUNT(*) AS n FROM victims").fetchone()["n"]
    districts     = conn.execute("SELECT COUNT(*) AS n FROM districts").fetchone()["n"]
    crime_dist    = rows_to_list(conn.execute("""
        SELECT crime_type, COUNT(*) AS count FROM firs
        GROUP BY crime_type ORDER BY count DESC LIMIT 8
    """).fetchall())
    monthly       = rows_to_list(conn.execute("""
        SELECT strftime('%Y-%m', date_of_fir) AS month, COUNT(*) AS count
        FROM firs GROUP BY month ORDER BY month DESC LIMIT 12
    """).fetchall())
    conn.close()
    return jsonify({
        "total_firs":    total_firs,
        "open_firs":     open_firs,
        "total_accused": total_accused,
        "total_victims": total_victims,
        "districts":     districts,
        "crime_distribution": crime_dist,
        "monthly_trend":      monthly,
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/import/preview", methods=["POST"])
def csv_preview():
    """
    Accept a multipart file upload and return a parse preview (no DB writes).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only .csv files are supported"}), 400
    try:
        result = preview_csv(f.read())
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/import/csv", methods=["POST"])
def csv_import():
    """
    Accept a multipart file upload and import all rows into the DB.
    Query param: ?overwrite=1  to replace existing FIRs (default: skip duplicates).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only .csv files are supported"}), 400
    skip_duplicates = request.args.get("overwrite", "0") != "1"
    try:
        result = import_csv(f.read(), skip_duplicates=skip_duplicates)
        # Run alert engine after import
        conn = get_conn()
        run_alert_engine(conn)
        conn.close()
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  HEATMAP / GEO DATA
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/map/firs", methods=["GET"])
def map_firs():
    """Return all FIRs with lat/lng for the heatmap page."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT f.id, f.fir_number, f.crime_type, f.date_of_fir,
               f.modus_operandi, f.location, f.status,
               ps.name AS station_name, d.name AS district_name
        FROM   firs f
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d        ON d.id=ps.district_id
    """).fetchall()
    conn.close()

    features = []
    for r in rows:
        lat, lng = get_coords(r["district_name"], r["station_name"])
        # Small jitter so stacked pins spread out visually
        import random, hashlib
        seed = int(hashlib.md5(str(r["id"]).encode()).hexdigest()[:8], 16)
        rng  = random.Random(seed)
        lat += rng.uniform(-0.008, 0.008)
        lng += rng.uniform(-0.008, 0.008)
        features.append({
            "id":          r["id"],
            "fir_number":  r["fir_number"],
            "crime_type":  r["crime_type"],
            "date":        r["date_of_fir"],
            "district":    r["district_name"],
            "station":     r["station_name"],
            "location":    r["location"],
            "status":      r["status"],
            "modus_operandi": r["modus_operandi"],
            "lat": round(lat, 6),
            "lng": round(lng, 6),
        })
    return jsonify(features)


# ═══════════════════════════════════════════════════════════════════════════════
#  ACCUSED NETWORK GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/network", methods=["GET"])
def accused_network():
    """
    Returns top-N repeat offender nodes + their co-accused edges.
    Fixed: does not use DISTINCT inside window functions (not supported in SQLite).
    """
    from collections import defaultdict
    conn = get_conn()

    # Step 1: per-name FIR count (no window functions)
    fir_counts = {r["name"]: r["cnt"] for r in conn.execute("""
        SELECT name, COUNT(DISTINCT fir_id) AS cnt
        FROM accused GROUP BY name
    """).fetchall()}

    # Step 2: all accused rows (name + fir_id + crime_type)
    accused_rows = rows_to_list(conn.execute("""
        SELECT a.name, a.fir_id, f.crime_type
        FROM accused a JOIN firs f ON f.id=a.fir_id
    """).fetchall())
    conn.close()

    # Build fir -> [names] and name -> crimes
    fir_to_accused: dict = defaultdict(list)
    node_crimes: dict    = defaultdict(set)
    for r in accused_rows:
        fir_to_accused[r["fir_id"]].append(r["name"])
        node_crimes[r["name"]].add(r["crime_type"])

    # Build edge weights
    edge_weights: dict = defaultdict(int)
    for names in fir_to_accused.values():
        unique = list(set(names))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                key = tuple(sorted([unique[i], unique[j]]))
                edge_weights[key] += 1

    # Include repeat offenders (>=2 FIRs) + anyone directly connected to them
    repeat_names = {n for n, c in fir_counts.items() if c >= 2}
    relevant_nodes: set = set(repeat_names)
    for (a, b) in edge_weights:
        if a in repeat_names or b in repeat_names:
            relevant_nodes.add(a)
            relevant_nodes.add(b)

    # Cap at 150 nodes (largest FIR count first) to keep graph renderable
    relevant_nodes = set(sorted(relevant_nodes, key=lambda n: fir_counts.get(n, 1), reverse=True)[:150])

    nodes = [
        {
            "id":        name,
            "fir_count": fir_counts.get(name, 1),
            "crimes":    list(node_crimes.get(name, [])),
            "repeat":    fir_counts.get(name, 1) >= 3,
        }
        for name in relevant_nodes
    ]
    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_weights.items()
        if a in relevant_nodes and b in relevant_nodes
    ]
    return jsonify({"nodes": nodes, "edges": edges})


@app.route("/api/analytics/network/ego", methods=["GET"])
def accused_ego_network():
    """
    Ego-network for a single accused: returns that person + all co-accused
    who appeared in the same FIRs, plus the FIRs themselves as location nodes.
    GET /api/analytics/network/ego?name=Ravi+Kumar
    """
    from collections import defaultdict
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    conn = get_conn()

    # FIRs this accused appears in
    ego_firs = rows_to_list(conn.execute("""
        SELECT DISTINCT a.fir_id, f.fir_number, f.crime_type,
               f.date_of_fir, f.modus_operandi, f.status,
               ps.name AS station, d.name AS district
        FROM accused a
        JOIN firs f ON f.id=a.fir_id
        JOIN police_stations ps ON ps.id=f.police_station_id
        JOIN districts d ON d.id=ps.district_id
        WHERE a.name = ?
    """, (name,)).fetchall())

    if not ego_firs:
        conn.close()
        return jsonify({"error": "Accused not found"}), 404

    fir_ids = [r["fir_id"] for r in ego_firs]

    # All co-accused in those FIRs
    placeholders = ",".join("?" * len(fir_ids))
    co_accused = rows_to_list(conn.execute(f"""
        SELECT a.name, a.fir_id, f.crime_type
        FROM accused a JOIN firs f ON f.id=a.fir_id
        WHERE a.fir_id IN ({placeholders})
    """, fir_ids).fetchall())

    # Per-name total FIR count (global, not just in this ego)
    fir_counts = {r["name"]: r["cnt"] for r in conn.execute("""
        SELECT name, COUNT(DISTINCT fir_id) AS cnt FROM accused GROUP BY name
    """).fetchall()}
    conn.close()

    # Build node list
    node_crimes: dict    = defaultdict(set)
    fir_to_co: dict      = defaultdict(list)
    for r in co_accused:
        node_crimes[r["name"]].add(r["crime_type"])
        fir_to_co[r["fir_id"]].append(r["name"])

    all_names = list({r["name"] for r in co_accused})
    nodes = [
        {
            "id":        n,
            "fir_count": fir_counts.get(n, 1),
            "crimes":    list(node_crimes[n]),
            "repeat":    fir_counts.get(n, 1) >= 3,
            "ego":       n == name,
        }
        for n in all_names
    ]

    # Edges between co-accused
    edge_weights: dict = defaultdict(int)
    for names_in_fir in fir_to_co.values():
        unique = list(set(names_in_fir))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                key = tuple(sorted([unique[i], unique[j]]))
                edge_weights[key] += 1

    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_weights.items()
    ]

    # Also return the FIR list for the sidebar / location pins
    firs_with_coords = []
    for fir in ego_firs:
        lat, lng = get_coords(fir["district"], fir["station"])
        firs_with_coords.append({**fir, "lat": round(lat, 6), "lng": round(lng, 6)})

    return jsonify({
        "name":  name,
        "nodes": nodes,
        "edges": edges,
        "firs":  firs_with_coords,
    })


@app.route("/api/analytics/accused_names", methods=["GET"])
def accused_names():
    """Autocomplete list of accused names for the network search box."""
    q = request.args.get("q", "").strip()
    conn = get_conn()
    if q:
        rows = conn.execute("""
            SELECT name, COUNT(DISTINCT fir_id) AS cnt
            FROM accused WHERE name LIKE ?
            GROUP BY name ORDER BY cnt DESC LIMIT 15
        """, (f"%{q}%",)).fetchall()
    else:
        rows = conn.execute("""
            SELECT name, COUNT(DISTINCT fir_id) AS cnt
            FROM accused GROUP BY name ORDER BY cnt DESC LIMIT 20
        """).fetchall()
    conn.close()
    return jsonify([{"name": r["name"], "fir_count": r["cnt"]} for r in rows])


@app.route("/api/map/clusters", methods=["GET"])
def map_clusters():
    """
    Returns per-(district, station) FIR counts with lat/lng for heat cluster rendering.
    Each item also includes a breakdown by crime_type.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT d.name AS district, ps.name AS station,
               f.crime_type, COUNT(*) AS cnt
        FROM firs f
        JOIN police_stations ps ON ps.id=f.police_station_id
        JOIN districts d ON d.id=ps.district_id
        GROUP BY d.id, ps.id, f.crime_type
        ORDER BY cnt DESC
    """).fetchall()
    conn.close()

    import random
    from collections import defaultdict
    clusters: dict = defaultdict(lambda: {"total": 0, "crimes": {}})
    for r in rows:
        key = (r["district"], r["station"])
        clusters[key]["total"]  += r["cnt"]
        clusters[key]["crimes"][r["crime_type"]] = r["cnt"]

    result = []
    for (district, station), data in clusters.items():
        lat, lng = get_coords(district, station)
        # Extra jitter for same-centroid stations (station not in lookup)
        seed_str = f"{district}|{station}"
        import hashlib
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng  = random.Random(seed)
        lat += rng.uniform(-0.045, 0.045)
        lng += rng.uniform(-0.045, 0.045)
        # Top crime for colour
        top_crime = max(data["crimes"], key=lambda c: data["crimes"][c])
        result.append({
            "district":  district,
            "station":   station,
            "total":     data["total"],
            "crimes":    data["crimes"],
            "top_crime": top_crime,
            "lat":       round(lat, 6),
            "lng":       round(lng, 6),
        })
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  ALERTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/alerts", methods=["GET"])
def list_alerts():
    conn = get_conn()
    rows = rows_to_list(conn.execute("""
        SELECT * FROM alerts ORDER BY created_at DESC LIMIT 50
    """).fetchall())
    unread = conn.execute("SELECT COUNT(*) AS n FROM alerts WHERE is_read=0").fetchone()["n"]
    conn.close()
    return jsonify({"alerts": rows, "unread": unread})


@app.route("/api/alerts/<int:alert_id>/read", methods=["POST"])
def mark_alert_read(alert_id):
    conn = get_conn()
    conn.execute("UPDATE alerts SET is_read=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/alerts/read_all", methods=["POST"])
def mark_all_read():
    conn = get_conn()
    conn.execute("UPDATE alerts SET is_read=1")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════════
#  FULL-TEXT SEARCH  (SQLite FTS5)
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_fts(conn):
    """Create FTS5 virtual table if it doesn't exist, then sync."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS firs_fts
        USING fts5(
            fir_number, crime_type, modus_operandi, location, description,
            content='firs', content_rowid='id'
        )
    """)
    # Rebuild to sync with current firs table
    conn.execute("INSERT INTO firs_fts(firs_fts) VALUES('rebuild')")
    conn.commit()


@app.route("/api/firs/search", methods=["GET"])
def fts_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    conn = get_conn()
    try:
        _ensure_fts(conn)
        # Sanitise query for FTS5 (escape special chars)
        safe_q = re.sub(r'[^\w\s]', ' ', q) + "*"
        fts_rows = conn.execute("""
            SELECT rowid FROM firs_fts WHERE firs_fts MATCH ? LIMIT 30
        """, (safe_q,)).fetchall()
        ids = [r[0] for r in fts_rows]
        if not ids:
            conn.close()
            return jsonify([])
        placeholders = ",".join("?" * len(ids))
        rows = rows_to_list(conn.execute(f"""
            SELECT f.id, f.fir_number, f.date_of_fir, f.crime_type,
                   f.modus_operandi, f.location, f.status,
                   ps.name AS station_name, d.name AS district_name
            FROM firs f
            JOIN police_stations ps ON ps.id=f.police_station_id
            JOIN districts d ON d.id=ps.district_id
            WHERE f.id IN ({placeholders})
        """, ids).fetchall())
        conn.close()
        return jsonify(rows)
    except Exception as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/firs/suggest", methods=["GET"])
def fts_suggest():
    """Return accused name suggestions for autocomplete."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT name FROM accused
        WHERE name LIKE ? LIMIT 10
    """, (f"%{q}%",)).fetchall()
    crime_rows = conn.execute("""
        SELECT DISTINCT crime_type FROM firs
        WHERE crime_type LIKE ? LIMIT 5
    """, (f"%{q}%",)).fetchall()
    conn.close()
    results = [r[0] for r in rows] + [r[0] for r in crime_rows]
    return jsonify(list(dict.fromkeys(results))[:12])


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/firs/<int:fir_id>/pdf", methods=["GET"])
def export_fir_pdf(fir_id):
    conn = get_conn()
    fir  = fir_full(conn, fir_id)
    conn.close()
    if not fir:
        return jsonify({"error": "Not found"}), 404
    pdf_bytes = fir_report(fir)
    fname = fir["fir_number"].replace("/", "_") + ".pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.route("/api/analytics/report/pdf", methods=["GET"])
def export_analytics_pdf():
    conn = get_conn()
    summ = {
        "total_firs":    conn.execute("SELECT COUNT(*) AS n FROM firs").fetchone()["n"],
        "open_firs":     conn.execute("SELECT COUNT(*) AS n FROM firs WHERE status='Open'").fetchone()["n"],
        "total_accused": conn.execute("SELECT COUNT(*) AS n FROM accused").fetchone()["n"],
        "total_victims": conn.execute("SELECT COUNT(*) AS n FROM victims").fetchone()["n"],
        "districts":     conn.execute("SELECT COUNT(*) AS n FROM districts").fetchone()["n"],
        "crime_distribution": rows_to_list(conn.execute("""
            SELECT crime_type, COUNT(*) AS count FROM firs
            GROUP BY crime_type ORDER BY count DESC LIMIT 10
        """).fetchall()),
    }
    repeat = rows_to_list(conn.execute("""
        SELECT a.name, COUNT(DISTINCT a.fir_id) AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type) AS crime_types,
               GROUP_CONCAT(DISTINCT d.name) AS districts
        FROM accused a JOIN firs f ON f.id=a.fir_id
        JOIN police_stations ps ON ps.id=f.police_station_id
        JOIN districts d ON d.id=ps.district_id
        GROUP BY a.name HAVING fir_count > 1
        ORDER BY fir_count DESC LIMIT 15
    """).fetchall())
    hotspots = rows_to_list(conn.execute("""
        SELECT d.name AS district, ps.name AS station,
               COUNT(*) AS fir_count,
               GROUP_CONCAT(DISTINCT f.crime_type) AS crime_types
        FROM firs f JOIN police_stations ps ON ps.id=f.police_station_id
        JOIN districts d ON d.id=ps.district_id
        GROUP BY d.id, ps.id ORDER BY fir_count DESC LIMIT 15
    """).fetchall())
    mo = rows_to_list(conn.execute("""
        SELECT modus_operandi, COUNT(*) AS count,
               GROUP_CONCAT(DISTINCT crime_type) AS crime_types
        FROM firs WHERE modus_operandi IS NOT NULL AND modus_operandi != ''
        GROUP BY modus_operandi ORDER BY count DESC LIMIT 10
    """).fetchall())
    conn.close()

    pdf_bytes = analytics_report(summ, repeat, hotspots, mo)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="FIRX_Analytics_Report.pdf"'},
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  AI FIR SUMMARISER  (rule-based NLP extraction — no external API required)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/extract", methods=["POST"])
def ai_extract():
    """
    Extract FIR fields from a raw_text narrative using pattern matching.
    POST JSON: {"text": "..."}
    Returns extracted fields to pre-fill the FIR form.
    """
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    result = _extract_fields(text)
    return jsonify(result)


def _extract_fields(text: str) -> dict:
    """
    Rule-based field extractor from CCTNS-style FIR narratives.
    Works on the raw_text format generated by generate_sample_csv.py and real CCTNS exports.
    """
    t = text.lower()

    # ── Crime type ─────────────────────────────────────────────────────────────
    CRIME_PATTERNS = [
        (r"financial fraud",          "Financial Fraud"),
        (r"cybercrime\s*[-–]\s*harassment", "Cybercrime - Harassment"),
        (r"cybercrime\s*[-–]\s*fraud","Cybercrime - Fraud"),
        (r"cyber\s*crime",            "Cybercrime - Fraud"),
        (r"drug trafficking",         "Drug Trafficking"),
        (r"chain snatching",          "Chain Snatching"),
        (r"vehicle theft",            "Vehicle Theft"),
        (r"domestic violence",        "Domestic Violence"),
        (r"\bkidnap",                 "Kidnapping"),
        (r"\bextortion",              "Extortion"),
        (r"\bburglary",               "Burglary"),
        (r"\brobbery",                "Robbery"),
        (r"\bassault",                "Assault"),
        (r"\bmurder",                 "Murder"),
        (r"\bcheating",               "Cheating"),
        (r"\btheft",                  "Theft"),
        (r"\bfraud",                  "Financial Fraud"),
    ]
    crime_type = None
    for pattern, label in CRIME_PATTERNS:
        if re.search(pattern, t):
            crime_type = label
            break

    # ── Modus operandi ─────────────────────────────────────────────────────────
    mo = None
    mo_match = re.search(r"modus operandi[:\s]+([^.]+)", t)
    if mo_match:
        mo = mo_match.group(1).strip().rstrip(".")

    # ── Location ───────────────────────────────────────────────────────────────
    location = None
    loc_patterns = [
        r"incident (?:at|in|on)\s+([^.]+?)(?:\.|$)",
        r"at\s+([\w\s]+(?:shop|platform|profile|service|road|area|market|office|school|college|bank|flat|premises|residence))",
    ]
    for pat in loc_patterns:
        m = re.search(pat, t)
        if m:
            location = m.group(1).strip().rstrip(".")
            break

    # ── Accused name ───────────────────────────────────────────────────────────
    accused_name = None
    accused_desc = None
    acc_match = re.search(r"accused person was described as\s+([A-Z][a-z]+ [A-Z][a-z]+)", text, re.I)
    if acc_match:
        accused_name = acc_match.group(1).strip()
    else:
        # Try "accused: Name" or "suspect: Name"
        acc2 = re.search(r"(?:accused|suspect)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", text, re.I)
        if acc2:
            accused_name = acc2.group(1).strip()

    # ── Victim profile ─────────────────────────────────────────────────────────
    victim_profile = None
    vp_match = re.search(r"victim profile[:\s]+([^.]+)", t)
    if vp_match:
        victim_profile = vp_match.group(1).strip().rstrip(".")

    # ── Repeat offender ────────────────────────────────────────────────────────
    repeat = bool(re.search(r"previously linked|linked to fir|repeat|prior case|earlier case", t))

    # ── Description: first full sentence that sets context ────────────────────
    description = text[:400] if text else None

    return {
        "crime_type":      crime_type,
        "modus_operandi":  mo,
        "location":        location,
        "accused_name":    accused_name,
        "accused_description": accused_desc,
        "victim_profile":  victim_profile,
        "repeat_offender": repeat,
        "description":     description,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CASE TIMELINE  (audit log per FIR)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/firs/<int:fir_id>/timeline", methods=["GET"])
def fir_timeline(fir_id):
    conn = get_conn()
    rows = rows_to_list(conn.execute("""
        SELECT id, action, actor, old_status, new_status, note, created_at
        FROM   fir_audit_log
        WHERE  fir_id = ?
        ORDER  BY created_at ASC
    """, (fir_id,)).fetchall())
    conn.close()
    return jsonify(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  BULK CSV EXPORT  (honours the same filters as list_firs)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/firs/export/csv", methods=["GET"])
def export_firs_csv():
    import csv, io
    conn = get_conn()
    q = request.args
    filters, params = [], []

    if q.get("search"):
        term = f"%{q['search']}%"
        filters.append("(f.fir_number LIKE ? OR f.crime_type LIKE ? OR d.name LIKE ? OR ps.name LIKE ? OR f.modus_operandi LIKE ?)")
        params.extend([term, term, term, term, term])
    if q.get("district"):
        filters.append("d.name = ?"); params.append(q["district"])
    if q.get("crime_type"):
        filters.append("f.crime_type = ?"); params.append(q["crime_type"])
    if q.get("status"):
        filters.append("f.status = ?"); params.append(q["status"])
    if q.get("from_date"):
        filters.append("f.date_of_fir >= ?"); params.append(q["from_date"])
    if q.get("to_date"):
        filters.append("f.date_of_fir <= ?"); params.append(q["to_date"])

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    rows = conn.execute(f"""
        SELECT f.fir_number, f.date_of_fir, f.date_of_offence,
               d.name AS district, ps.name AS station,
               f.crime_type, f.modus_operandi, f.location,
               f.section_of_law, f.status, f.description,
               GROUP_CONCAT(DISTINCT a.name) AS accused_names,
               GROUP_CONCAT(DISTINCT v.name) AS victim_names
        FROM   firs f
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d        ON d.id=ps.district_id
        LEFT   JOIN accused a     ON a.fir_id=f.id
        LEFT   JOIN victims v     ON v.fir_id=f.id
        {where}
        GROUP  BY f.id
        ORDER  BY f.date_of_fir DESC
    """, params).fetchall()
    conn.close()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["FIR Number","Date of FIR","Date of Offence","District","Station",
                     "Crime Type","Modus Operandi","Location","Section of Law",
                     "Status","Description","Accused","Victims"])
    for r in rows:
        writer.writerow([r[k] or "" for k in
                         ["fir_number","date_of_fir","date_of_offence","district","station",
                          "crime_type","modus_operandi","location","section_of_law",
                          "status","description","accused_names","victim_names"]])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=firs_export.csv"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ACCUSED PROFILE  +  RISK SCORE
# ═══════════════════════════════════════════════════════════════════════════════

_CRIME_SEVERITY = {
    "Murder": 10, "Kidnapping": 9, "Robbery": 8, "Drug Trafficking": 8,
    "Extortion": 7, "Assault": 6, "Burglary": 6, "Vehicle Theft": 5,
    "Chain Snatching": 5, "Theft": 4, "Financial Fraud": 4,
    "Cybercrime - Fraud": 3, "Cybercrime - Harassment": 3,
    "Fraud": 4, "Cheating": 3, "Domestic Violence": 6,
}

def _risk_score(fir_count: int, district_count: int, crimes: list, prior: int) -> int:
    """
    Composite risk score 0–100.
      FIR volume  : up to 30 pts  (3 pts per FIR, cap 30)
      District spread: up to 20 pts (5 pts per district, cap 20)
      Crime severity : up to 30 pts (max severity crime × 3)
      Prior offences : up to 20 pts (4 pts each, cap 20)
    """
    vol   = min(fir_count * 3, 30)
    dist  = min(district_count * 5, 20)
    sev   = min(max((_CRIME_SEVERITY.get(c, 2) for c in crimes), default=0) * 3, 30)
    prior_pts = min(prior * 4, 20)
    return vol + dist + sev + prior_pts

@app.route("/api/analytics/accused/<path:name>", methods=["GET"])
def accused_profile(name):
    conn = get_conn()
    # All FIRs this accused appears in
    rows = rows_to_list(conn.execute("""
        SELECT f.id AS fir_id, f.fir_number, f.date_of_fir, f.crime_type,
               f.modus_operandi, f.location, f.status,
               ps.name AS station, d.name AS district,
               a.alias, a.age, a.gender, a.address, a.occupation,
               a.prior_offences, a.aadhar_number, a.mobile_number
        FROM   accused a
        JOIN   firs f ON f.id=a.fir_id
        JOIN   police_stations ps ON ps.id=f.police_station_id
        JOIN   districts d ON d.id=ps.district_id
        WHERE  a.name = ?
        ORDER  BY f.date_of_fir DESC
    """, (name,)).fetchall())
    conn.close()
    if not rows:
        return jsonify({"error": "Accused not found"}), 404

    crimes     = list({r["crime_type"] for r in rows})
    districts  = list({r["district"] for r in rows})
    mos        = list({r["modus_operandi"] for r in rows if r["modus_operandi"]})
    max_prior  = max((r["prior_offences"] or 0) for r in rows)
    first_r    = rows[0]

    score = _risk_score(len(rows), len(districts), crimes, max_prior)

    return jsonify({
        "name":           name,
        "alias":          first_r["alias"],
        "age":            first_r["age"],
        "gender":         first_r["gender"],
        "address":        first_r["address"],
        "occupation":     first_r["occupation"],
        "aadhar_number":  first_r["aadhar_number"],
        "mobile_number":  first_r["mobile_number"],
        "fir_count":      len(rows),
        "district_count": len(districts),
        "districts":      districts,
        "crime_types":    crimes,
        "modus_operandi": mos,
        "prior_offences": max_prior,
        "risk_score":     score,
        "risk_label":     "Critical" if score>=70 else "High" if score>=45 else "Medium" if score>=25 else "Low",
        "firs":           rows,
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  BULK STATUS UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/firs/bulk_status", methods=["POST"])
def bulk_status_update():
    data = request.json or {}
    ids  = data.get("ids", [])
    new_status = data.get("status", "")
    valid = ("Open", "Under Investigation", "Chargesheeted", "Closed")
    if not ids or new_status not in valid:
        return jsonify({"error": "Provide ids[] and a valid status"}), 400
    conn = get_conn()
    updated = 0
    for fir_id in ids:
        row = conn.execute("SELECT status FROM firs WHERE id=?", (fir_id,)).fetchone()
        if row:
            old = row["status"]
            conn.execute("UPDATE firs SET status=?, updated_at=datetime('now') WHERE id=?",
                         (new_status, fir_id))
            audit_log(conn, fir_id, "status_changed",
                      old_status=old, new_status=new_status,
                      note="bulk status update")
            updated += 1
    conn.commit()
    run_alert_engine(conn)
    conn.close()
    return jsonify({"updated": updated})


# ═══════════════════════════════════════════════════════════════════════════════
#  VICTIM DEMOGRAPHICS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/victim_demographics", methods=["GET"])
def victim_demographics():
    conn = get_conn()
    gender = rows_to_list(conn.execute("""
        SELECT gender, COUNT(*) AS count FROM victims
        GROUP BY gender ORDER BY count DESC
    """).fetchall())
    injury = rows_to_list(conn.execute("""
        SELECT injury_type, COUNT(*) AS count FROM victims
        GROUP BY injury_type ORDER BY count DESC
    """).fetchall())
    age_groups = rows_to_list(conn.execute("""
        SELECT
          CASE
            WHEN age IS NULL            THEN 'Unknown'
            WHEN age < 18               THEN 'Minor (<18)'
            WHEN age BETWEEN 18 AND 30  THEN '18–30'
            WHEN age BETWEEN 31 AND 45  THEN '31–45'
            WHEN age BETWEEN 46 AND 60  THEN '46–60'
            ELSE '>60'
          END AS age_group,
          COUNT(*) AS count
        FROM victims
        GROUP BY age_group
        ORDER BY count DESC
    """).fetchall())
    top_occupations = rows_to_list(conn.execute("""
        SELECT occupation, COUNT(*) AS count FROM victims
        WHERE occupation IS NOT NULL AND occupation != ''
        GROUP BY occupation ORDER BY count DESC LIMIT 8
    """).fetchall())
    by_crime = rows_to_list(conn.execute("""
        SELECT f.crime_type, COUNT(*) AS victim_count
        FROM victims v JOIN firs f ON f.id=v.fir_id
        GROUP BY f.crime_type ORDER BY victim_count DESC LIMIT 10
    """).fetchall())
    conn.close()
    return jsonify({
        "gender":          gender,
        "injury":          injury,
        "age_groups":      age_groups,
        "top_occupations": top_occupations,
        "by_crime":        by_crime,
    })



# ═══════════════════════════════════════════════════════════════════════════════
#  BOB LLM — AI DATABASE ANALYST
# ═══════════════════════════════════════════════════════════════════════════════

def _gather_db_context() -> dict:
    """Pull a compact statistical snapshot from the DB to inject as LLM context."""
    conn = get_conn()
    try:
        total_firs    = conn.execute("SELECT COUNT(*) FROM firs").fetchone()[0]
        open_firs     = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Open'").fetchone()[0]
        under_inv     = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Under Investigation'").fetchone()[0]
        chargesheeted = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Chargesheeted'").fetchone()[0]
        closed        = conn.execute("SELECT COUNT(*) FROM firs WHERE status='Closed'").fetchone()[0]
        total_accused = conn.execute("SELECT COUNT(*) FROM accused").fetchone()[0]
        total_victims = conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0]

        crime_dist = rows_to_list(conn.execute("""
            SELECT crime_type, COUNT(*) AS count FROM firs
            GROUP BY crime_type ORDER BY count DESC LIMIT 12
        """).fetchall())

        district_stats = rows_to_list(conn.execute("""
            SELECT d.name AS district, COUNT(*) AS fir_count
            FROM firs f
            JOIN police_stations ps ON ps.id = f.police_station_id
            JOIN districts d ON d.id = ps.district_id
            GROUP BY d.id ORDER BY fir_count DESC LIMIT 15
        """).fetchall())

        monthly_trend = rows_to_list(conn.execute("""
            SELECT strftime('%Y-%m', date_of_fir) AS month, COUNT(*) AS count
            FROM firs GROUP BY month ORDER BY month DESC LIMIT 12
        """).fetchall())

        repeat_offenders = rows_to_list(conn.execute("""
            SELECT a.name, COUNT(DISTINCT a.fir_id) AS fir_count,
                   GROUP_CONCAT(DISTINCT f.crime_type) AS crime_types,
                   GROUP_CONCAT(DISTINCT d.name) AS districts
            FROM accused a
            JOIN firs f ON f.id = a.fir_id
            JOIN police_stations ps ON ps.id = f.police_station_id
            JOIN districts d ON d.id = ps.district_id
            GROUP BY a.name HAVING fir_count > 1
            ORDER BY fir_count DESC LIMIT 10
        """).fetchall())

        hotspots = rows_to_list(conn.execute("""
            SELECT d.name AS district, ps.name AS station, COUNT(*) AS fir_count
            FROM firs f
            JOIN police_stations ps ON ps.id = f.police_station_id
            JOIN districts d ON d.id = ps.district_id
            GROUP BY d.id, ps.id ORDER BY fir_count DESC LIMIT 10
        """).fetchall())

        top_mo = rows_to_list(conn.execute("""
            SELECT modus_operandi, COUNT(*) AS count
            FROM firs WHERE modus_operandi IS NOT NULL AND modus_operandi != ''
            GROUP BY modus_operandi ORDER BY count DESC LIMIT 8
        """).fetchall())

        victim_gender = rows_to_list(conn.execute("""
            SELECT gender, COUNT(*) AS count FROM victims GROUP BY gender ORDER BY count DESC
        """).fetchall())

        inter_district = rows_to_list(conn.execute("""
            SELECT a.name, COUNT(DISTINCT d.id) AS dist_count,
                   GROUP_CONCAT(DISTINCT d.name) AS districts,
                   COUNT(DISTINCT a.fir_id) AS fir_count
            FROM accused a
            JOIN firs f ON f.id = a.fir_id
            JOIN police_stations ps ON ps.id = f.police_station_id
            JOIN districts d ON d.id = ps.district_id
            GROUP BY a.name HAVING dist_count > 1
            ORDER BY dist_count DESC LIMIT 10
        """).fetchall())

        crime_by_status = rows_to_list(conn.execute("""
            SELECT crime_type, status, COUNT(*) AS count FROM firs
            GROUP BY crime_type, status ORDER BY crime_type, count DESC
        """).fetchall())

    finally:
        conn.close()

    return {
        "overview": {
            "total_firs": total_firs, "open": open_firs,
            "under_investigation": under_inv, "chargesheeted": chargesheeted,
            "closed": closed, "total_accused": total_accused,
            "total_victims": total_victims,
        },
        "crime_distribution":   crime_dist,
        "district_stats":       district_stats,
        "monthly_trend":        monthly_trend,
        "repeat_offenders":     repeat_offenders,
        "inter_district_accused": inter_district,
        "crime_hotspots":       hotspots,
        "top_modus_operandi":   top_mo,
        "victim_gender":        victim_gender,
        "crime_by_status":      crime_by_status,
    }


def _call_bob_llm(system_prompt: str, user_message: str) -> str:
    """
    Call Bob (IBM) LLM via its OpenAI-compatible chat completions endpoint.
    Configuration via environment variables:
      BOB_API_URL   – base URL of the LiteLLM/Bob inference proxy
                      (default: http://localhost:4000)
      BOB_API_KEY   – Bearer token / API key
                      (falls back to BOBSHELL_API_KEY)
      BOB_MODEL     – model name to use (default: bob)
    """
    base_url = os.environ.get("BOB_API_URL", "http://localhost:4000").rstrip("/")
    api_key  = os.environ.get("BOB_API_KEY") or os.environ.get("BOBSHELL_API_KEY", "no-key")
    model    = os.environ.get("BOB_MODEL", "bob")

    url     = f"{base_url}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens": 1200,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """
    Body: { "question": "...", "history": [{"role":"user","content":"..."},…] }
    Returns: { "answer": "..." }
    """
    data     = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    try:
        db_ctx = _gather_db_context()
    except Exception as e:
        return jsonify({"error": f"DB context error: {e}"}), 500

    system_prompt = f"""You are FIR-X AI Analyst, an expert crime data analyst for a police intelligence dashboard.
You have access to a live FIR (First Information Report) database. Below is the current statistical snapshot of the database.
Use ONLY this data to answer questions — do not fabricate numbers or names.
Be concise, insightful, and structured. Use bullet points and bold text where helpful.
If something cannot be answered from the data, say so clearly.

=== CURRENT DATABASE SNAPSHOT ===
{json.dumps(db_ctx, indent=2)}
=== END SNAPSHOT ===

Answer the analyst's question based on this data."""

    try:
        answer = _call_bob_llm(system_prompt, question)
    except urllib.error.URLError as e:
        return jsonify({"error": f"Bob LLM unreachable: {e.reason}. Ensure the Bob inference proxy is running and BOB_API_URL is set correctly."}), 503
    except Exception as e:
        return jsonify({"error": f"LLM error: {e}"}), 500

    return jsonify({"answer": answer})



if __name__ == "__main__":
    app.run(debug=False, port=5000)

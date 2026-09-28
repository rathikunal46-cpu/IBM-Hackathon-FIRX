"""
csv_import.py  -  FIR-X CSV normaliser and importer

Exact CSV schema supported (tab-separated OR comma-separated, auto-detected):

  fir_id                    -> firs.fir_number
  station                   -> police_stations.name  (strips " PS" / " Police Station" suffix)
  district                  -> districts.name
  date                      -> firs.date_of_fir       (parses DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY ...)
  crime_type                -> firs.crime_type
  accused_name              -> accused.name           (primary; falls back to accused_description)
  accused_description       -> accused.address        (physical description / free text)
  location                  -> firs.location          (scene / place of offence)
  modus_operandi            -> firs.modus_operandi
  victim_profile            -> victims.occupation     (free-text role, e.g. "student", "business owner")
  repeat_offender_signature -> accused.prior_offences = 1 when truthy
  raw_text                  -> firs.description       (full narrative)

Additional aliases for each column are also accepted (see _ALIASES below).
Duplicate fir_id rows are skipped by default; pass skip_duplicates=False to overwrite.
"""

import csv
import io
import re
from datetime import datetime

from database import get_conn, get_or_create_station

# ── Column alias map ──────────────────────────────────────────────────────────
# Canonical key  ->  list of lowercase header spellings we accept
_ALIASES = {
    "fir_number": [
        "fir_id", "fir_number", "fir no", "firno", "case_number", "case no",
    ],
    "station": [
        "station", "police_station", "ps", "police station",
    ],
    "district": [
        "district", "dist", "district_name",
    ],
    "date": [
        "date", "date_of_fir", "fir_date", "incident_date", "date of fir",
    ],
    "crime_type": [
        "crime_type", "crime type", "offence_type", "offence type", "type_of_crime",
    ],
    "accused_name": [
        "accused_name", "accused name", "accused", "offender_name", "offender name",
    ],
    "accused_description": [
        "accused_description", "accused description", "accused_desc", "accused desc",
        "suspect_description",
    ],
    "location": [
        "location", "place", "place_of_offence", "place of offence", "scene",
        "incident_location",
    ],
    "modus_operandi": [
        "modus_operandi", "modus operandi", "mo", "method", "methodology",
    ],
    "victim_profile": [
        "victim_profile", "victim profile", "victim", "victim_description",
        "complainant_profile",
    ],
    "repeat_offender_signature": [
        "repeat_offender_signature", "repeat offender", "repeat_offender",
        "linked_fir", "linked fir", "connection",
    ],
    "raw_text": [
        "raw_text", "raw text", "description", "narrative", "details",
    ],
}

# Build reverse map: lowercase_header -> canonical key
_REVERSE: dict[str, str] = {}
for _canonical, _aliases in _ALIASES.items():
    for _alias in _aliases:
        _REVERSE[_alias.strip().lower()] = _canonical


# ── Helpers ───────────────────────────────────────────────────────────────────

def _map_header(raw_headers: list[str]) -> dict[str, int]:
    """Return {canonical_key: column_index} for every recognised header."""
    mapping: dict[str, int] = {}
    for idx, h in enumerate(raw_headers):
        canonical = _REVERSE.get(h.strip().lower())
        if canonical and canonical not in mapping:   # first match wins
            mapping[canonical] = idx
    return mapping


def _detect_dialect(text: str):
    """
    Sniff the first 4 KB to decide tab vs comma.
    Returns a dialect object or class; falls back to csv.excel (comma) on failure.
    """
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters="\t,")
    except csv.Error:
        return csv.excel          # default: comma


_DATE_FORMATS = [
    "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y",
]

def _parse_date(raw: str) -> str | None:
    """Return ISO YYYY-MM-DD or None if unparseable."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


_STATION_SUFFIX = re.compile(
    r"\s*(police\s+station|p\.s\.|ps|thana|chowki)\s*$",
    re.IGNORECASE,
)

def _clean_station(name: str) -> str:
    """Strip common station suffixes: 'Chandkheda PS' -> 'Chandkheda'."""
    return _STATION_SUFFIX.sub("", name.strip()).strip()


_POSITIVE = {"yes", "y", "true", "1", "linked", "flagged"}

def _is_repeat(value: str) -> bool:
    return value.strip().lower() in _POSITIVE


# ═══════════════════════════════════════════════════════════════════════════════
#  ROW NORMALISER  (shared by preview and import)
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_row(
    row: list[str],
    col_map: dict[str, int],
    line_num: int,
) -> tuple[dict, list[str]]:
    """
    Map one CSV row to a normalised dict.

    Returned dict keys:
      fir_number, date_of_fir, station, district, crime_type,
      modus_operandi, location, description,
      accused_name, accused_description, victim_occupation, repeat_offender
    """
    warnings: list[str] = []

    def get(key: str) -> str:
        idx = col_map.get(key)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    norm: dict = {}

    # ── Core FIR fields ───────────────────────────────────────────────────────
    norm["fir_number"] = get("fir_number")

    raw_date = get("date")
    parsed   = _parse_date(raw_date)
    if raw_date and not parsed:
        warnings.append(
            f"Row {line_num}: unrecognised date '{raw_date}' — today's date will be used"
        )
    norm["date_of_fir"] = parsed

    norm["station"]        = get("station")
    norm["district"]       = get("district")
    norm["crime_type"]     = get("crime_type")
    norm["modus_operandi"] = get("modus_operandi") or None
    norm["location"]       = get("location") or None

    # description: raw_text is the full narrative; fall back to location note
    raw_text = get("raw_text")
    norm["description"] = raw_text if raw_text else None

    # ── Accused ───────────────────────────────────────────────────────────────
    # accused_name = name (primary identity)
    # accused_description = physical description / appearance (stored in address)
    norm["accused_name"]        = get("accused_name") or None
    norm["accused_description"] = get("accused_description") or None

    # ── Victim ────────────────────────────────────────────────────────────────
    # victim_profile is the role/occupation of the victim ("student", "business owner")
    vp = get("victim_profile")
    norm["victim_occupation"] = vp.strip() if vp else None

    # ── Repeat offender flag ──────────────────────────────────────────────────
    ros = get("repeat_offender_signature")
    norm["repeat_offender"] = _is_repeat(ros) if ros else False

    return norm, warnings


# ═══════════════════════════════════════════════════════════════════════════════
#  PREVIEW  (no DB writes)
# ═══════════════════════════════════════════════════════════════════════════════

def preview_csv(file_bytes: bytes, encoding: str = "utf-8") -> dict:
    """
    Parse the CSV and return a preview dict (no DB writes):
      {
        "headers":    [...original header names...],
        "delimiter":  "tab" | "comma",
        "mapped":     {canonical_key: original_header, ...},
        "unmapped":   [...unrecognised header names...],
        "rows":       [...first 5 normalised row dicts...],
        "total_rows": N,
        "warnings":   [...parse warnings from first 5 rows...]
      }
    """
    text = file_bytes.decode(encoding, errors="replace")
    dialect = _detect_dialect(text)
    reader = csv.reader(io.StringIO(text), dialect)

    try:
        raw_headers = next(reader)
    except StopIteration:
        return {"error": "Empty CSV file"}

    col_map  = _map_header(raw_headers)
    unmapped = [h for h in raw_headers if _REVERSE.get(h.strip().lower()) is None]

    rows: list[dict]  = []
    all_warnings: list[str] = []
    count = 0

    for row in reader:
        count += 1
        if count <= 5:
            norm, warns = _normalise_row(row, col_map, count)
            rows.append(norm)
            all_warnings.extend(warns)

    # count remaining rows
    for _ in reader:
        count += 1

    delim_label = "tab" if getattr(dialect, "delimiter", ",") == "\t" else "comma"

    return {
        "headers":    raw_headers,
        "delimiter":  delim_label,
        "mapped":     {k: raw_headers[v] for k, v in col_map.items()},
        "unmapped":   unmapped,
        "rows":       rows,
        "total_rows": count,
        "warnings":   all_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  IMPORT  (write to DB)
# ═══════════════════════════════════════════════════════════════════════════════

def import_csv(
    file_bytes: bytes,
    encoding: str = "utf-8",
    skip_duplicates: bool = True,
) -> dict:
    """
    Import all rows into the database.

    Returns:
      {
        "inserted": N,
        "skipped":  N,
        "errors":   [...error strings...],
        "results":  [{row, fir_number, status, message}, ...]
      }
    """
    text    = file_bytes.decode(encoding, errors="replace")
    dialect = _detect_dialect(text)
    reader  = csv.reader(io.StringIO(text), dialect)

    try:
        raw_headers = next(reader)
    except StopIteration:
        return {"inserted": 0, "skipped": 0, "errors": ["Empty CSV file"], "results": []}

    col_map = _map_header(raw_headers)

    # Validate required columns exist
    missing = [c for c in ("fir_number", "station", "district", "date") if c not in col_map]
    if missing:
        return {
            "inserted": 0, "skipped": 0,
            "errors":   [f"Missing required columns: {', '.join(missing)}"],
            "results":  [],
        }

    conn     = get_conn()
    inserted = skipped = 0
    errors:  list[str]  = []
    results: list[dict] = []

    for line_num, row in enumerate(reader, start=2):   # line 1 = header
        norm, row_warns = _normalise_row(row, col_map, line_num)
        errors.extend(row_warns)   # warnings become soft errors in the log

        fir_number = norm.get("fir_number", "").strip()
        if not fir_number:
            results.append({
                "row": line_num, "fir_number": "—",
                "status": "error", "message": "Missing FIR number — row skipped",
            })
            continue

        # ── Duplicate guard ───────────────────────────────────────────────────
        existing = conn.execute(
            "SELECT id FROM firs WHERE fir_number=?", (fir_number,)
        ).fetchone()

        if existing:
            if skip_duplicates:
                skipped += 1
                results.append({
                    "row": line_num, "fir_number": fir_number,
                    "status": "skipped", "message": "Already exists — skipped",
                })
                continue
            else:
                # overwrite: cascade delete removes accused + victims too
                conn.execute("DELETE FROM firs WHERE fir_number=?", (fir_number,))

        # ── Insert ────────────────────────────────────────────────────────────
        try:
            station_name  = _clean_station(norm.get("station") or "Unknown")
            district_name = (norm.get("district") or "Unknown").strip() or "Unknown"
            station_id    = get_or_create_station(conn, station_name, district_name)

            cur = conn.execute(
                """
                INSERT INTO firs
                  (fir_number, date_of_fir, police_station_id,
                   crime_type, modus_operandi, location, description, status)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    fir_number,
                    norm.get("date_of_fir") or datetime.today().strftime("%Y-%m-%d"),
                    station_id,
                    norm.get("crime_type") or "Unknown",
                    norm.get("modus_operandi"),
                    norm.get("location"),          # scene / place of offence
                    norm.get("description"),       # raw_text narrative
                    "Open",
                ),
            )
            fir_id = cur.lastrowid

            # ── Accused ───────────────────────────────────────────────────────
            # accused_name  = identity (name to use)
            # accused_description = physical description stored as accused.address
            #
            # Fallback: if accused_name is blank but accused_description has text,
            # treat accused_description as the name (CCTNS sometimes puts name there)
            accused_name = (norm.get("accused_name") or "").strip()
            accused_desc = (norm.get("accused_description") or "").strip()

            if not accused_name and accused_desc:
                accused_name = accused_desc   # description value IS the name
                accused_desc = None           # nothing left for address field

            if accused_name:
                conn.execute(
                    """
                    INSERT INTO accused
                      (fir_id, name, address, prior_offences, gender)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        fir_id,
                        accused_name,
                        accused_desc,                      # physical description
                        1 if norm.get("repeat_offender") else 0,
                        "Unknown",
                    ),
                )

            # ── Victim ────────────────────────────────────────────────────────
            # victim_profile -> victims.occupation (role/profile of the complainant)
            victim_occ = norm.get("victim_occupation")
            if victim_occ:
                conn.execute(
                    """
                    INSERT INTO victims
                      (fir_id, name, occupation, gender, injury_type)
                    VALUES (?,?,?,?,?)
                    """,
                    (fir_id, "Unknown", victim_occ, "Unknown", "Unknown"),
                )

            conn.commit()
            inserted += 1
            results.append({
                "row":        line_num,
                "fir_number": fir_number,
                "status":     "inserted",
                "message":    f"Inserted — {station_name} PS, {district_name}",
            })

        except Exception as exc:
            conn.rollback()
            msg = str(exc)
            errors.append(f"Row {line_num} ({fir_number}): {msg}")
            results.append({
                "row": line_num, "fir_number": fir_number,
                "status": "error", "message": msg,
            })

    conn.close()
    return {
        "inserted": inserted,
        "skipped":  skipped,
        "errors":   errors,
        "results":  results,
    }


# ── CLI convenience ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python csv_import.py <file.csv> [--overwrite]")
        sys.exit(1)
    _path      = sys.argv[1]
    _overwrite = "--overwrite" in sys.argv
    with open(_path, "rb") as _f:
        _data = _f.read()
    _result = import_csv(_data, skip_duplicates=not _overwrite)
    print(f"Inserted : {_result['inserted']}")
    print(f"Skipped  : {_result['skipped']}")
    print(f"Errors   : {len(_result['errors'])}")
    for _e in _result["errors"]:
        print("  -", _e)

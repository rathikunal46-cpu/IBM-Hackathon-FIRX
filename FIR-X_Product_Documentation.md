# FIR-X — Crime Intelligence System
### Product Documentation & Technical Reference

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [File Structure](#3-file-structure)
4. [Database Schema](#4-database-schema)
5. [Core Features](#5-core-features)
   - 5.1 [FIR Management (CRUD)](#51-fir-management-crud)
   - 5.2 [CSV Import & Export](#52-csv-import--export)
   - 5.3 [Analytics Engine](#53-analytics-engine)
   - 5.4 [Crime Heatmap & Geo Clustering](#54-crime-heatmap--geo-clustering)
   - 5.5 [Accused Network Graph](#55-accused-network-graph)
   - 5.6 [Accused Profile & Risk Scoring](#56-accused-profile--risk-scoring)
   - 5.7 [Automated Alert Engine](#57-automated-alert-engine)
   - 5.8 [Full-Text Search & Autocomplete](#58-full-text-search--autocomplete)
   - 5.9 [AI Field Extractor](#59-ai-field-extractor)
   - 5.10 [Bob AI Analyst Chat](#510-bob-ai-analyst-chat)
   - 5.11 [PDF Export](#511-pdf-export)
   - 5.12 [Case Timeline / Audit Trail](#512-case-timeline--audit-trail)
   - 5.13 [Bulk Status Update](#513-bulk-status-update)
   - 5.14 [Victim Demographics Analytics](#514-victim-demographics-analytics)
   - 5.15 [Bob Shell CLI](#515-bob-shell-cli)
6. [REST API Reference](#6-rest-api-reference)
7. [Alert Engine Rules](#7-alert-engine-rules)
8. [Risk Scoring Model](#8-risk-scoring-model)
9. [Geocoding System](#9-geocoding-system)
10. [Running the Application](#10-running-the-application)
11. [CSV Format Specification](#11-csv-format-specification)

---

## 1. Project Overview

**FIR-X** (First Information Report – Intelligence Exchange) is a full-stack crime intelligence platform built for law enforcement analysts. It centralises CCTNS (Crime and Criminal Tracking Networks and Systems) FIR data into a single searchable, analysable, and visualisable system.

### Problem Statement
Police departments across multiple districts generate thousands of FIRs that are siloed by station and district. Cross-district repeat offenders, crime pattern spikes, and coordinated criminal activity often go undetected. FIR-X solves this by:

- Aggregating FIRs from any district or station into one database
- Automatically detecting repeat offenders, inter-district criminals, and crime spikes
- Providing real-time analytics, heatmaps, and co-accused network graphs
- Enabling AI-assisted querying of the entire crime database via the Bob LLM

### Target Users
- Police analysts and intelligence officers
- District-level supervisory officers
- Crime branch investigators

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12 · Flask · Flask-CORS |
| **Database** | SQLite 3 (FTS5 full-text search enabled) |
| **PDF Generation** | fpdf2 |
| **Frontend** | Single-page HTML/JS/CSS (`static/index.html`) |
| **AI / LLM** | IBM Bob LLM via OpenAI-compatible proxy (`/v1/chat/completions`) |
| **Geocoding** | Static coordinate lookup (no external API) |
| **CLI Shell** | Python · tabulate |

---

## 3. File Structure

```
IBM Hackathon/
│
├── app.py                          # Flask application — all REST API routes (~1,476 lines)
├── database.py                     # SQLite schema, migrations, and DB helper functions
├── csv_import.py                   # CSV normaliser, column alias resolver, and DB importer
├── alerts.py                       # Automated alert engine (4 rule types)
├── geocode.py                      # Static district/station coordinate lookup
├── pdf_export.py                   # PDF generator using fpdf2 (FIR report + analytics report)
├── bob_shell.py                    # CLI intelligence shell (Bob-powered terminal interface)
├── seed_data.py                    # Sample data seeder for development/demo
├── generate_sample_csv.py          # Generates CCTNS-format sample CSV files
├── main.py                         # Entry point alias
│
├── static/
│   └── index.html                  # Full single-page frontend application
│
├── firx.db                         # SQLite database file (auto-created on first run)
│
├── FIR-X_500_FIR_Dataset_Structured.csv   # 500-record structured sample dataset
├── sample_firs.csv                 # Small sample CSV for testing
├── sample_firs_100.csv             # 100-record sample CSV
├── Upload1.csv                     # Additional test CSV
│
└── FIR-X_Project_Documentation.docx  # Previous project documentation (Word format)
```

---

## 4. Database Schema

The SQLite database (`firx.db`) contains six tables:

### 4.1 `districts`
Stores unique district names.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT UNIQUE | e.g. "Ahmedabad", "Mumbai" |

### 4.2 `police_stations`
Each station belongs to one district.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | e.g. "Chandkheda" |
| `district_id` | INTEGER FK | → `districts.id` |

### 4.3 `firs` *(master table)*
Core FIR record.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `fir_number` | TEXT UNIQUE | e.g. "FIR/2024/AHM/001" |
| `date_of_fir` | TEXT | ISO format YYYY-MM-DD |
| `date_of_offence` | TEXT | ISO format, nullable |
| `police_station_id` | INTEGER FK | → `police_stations.id` |
| `section_of_law` | TEXT | IPC sections, nullable |
| `crime_type` | TEXT | e.g. "Vehicle Theft", "Robbery" |
| `modus_operandi` | TEXT | Method of operation, nullable |
| `location` | TEXT | Scene/place of offence |
| `description` | TEXT | Full narrative / raw_text |
| `status` | TEXT | `Open` · `Under Investigation` · `Chargesheeted` · `Closed` |
| `created_at` | TEXT | Timestamp |
| `updated_at` | TEXT | Timestamp |

### 4.4 `accused`
One row per accused person per FIR (an accused may appear in multiple FIRs).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `fir_id` | INTEGER FK | → `firs.id` CASCADE DELETE |
| `name` | TEXT | Primary identity |
| `alias` | TEXT | Known aliases |
| `age` | INTEGER | |
| `gender` | TEXT | `Male` · `Female` · `Other` · `Unknown` |
| `address` | TEXT | Address or physical description |
| `district_id` | INTEGER FK | Home district |
| `occupation` | TEXT | |
| `prior_offences` | INTEGER | Count of prior cases |
| `aadhar_number` | TEXT | |
| `mobile_number` | TEXT | |

### 4.5 `victims`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `fir_id` | INTEGER FK | → `firs.id` CASCADE DELETE |
| `name` | TEXT | |
| `age` | INTEGER | |
| `gender` | TEXT | `Male` · `Female` · `Other` · `Unknown` |
| `address` | TEXT | |
| `occupation` | TEXT | |
| `injury_type` | TEXT | `None` · `Minor` · `Grievous` · `Fatal` · `Unknown` |
| `mobile_number` | TEXT | |

### 4.6 `alerts`
Auto-generated intelligence alerts.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `type` | TEXT | `repeat_offender` · `mo_spike` · `district_spread` · `crime_spike` |
| `severity` | TEXT | `High` · `Medium` · `Low` |
| `title` | TEXT | Short alert headline |
| `detail` | TEXT | Detailed description |
| `entity_name` | TEXT | Accused name, crime type, or MO text |
| `fir_count` | INTEGER | Number of linked FIRs |
| `is_read` | INTEGER | 0 = unread, 1 = read |
| `created_at` | TEXT | Timestamp |

### 4.7 `fir_audit_log`
Immutable audit trail for every FIR change.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `fir_id` | INTEGER FK | → `firs.id` CASCADE DELETE |
| `action` | TEXT | `created` · `updated` · `status_changed` · `deleted` |
| `actor` | TEXT | Who made the change (default: "officer") |
| `old_status` | TEXT | Previous status value |
| `new_status` | TEXT | New status value |
| `note` | TEXT | Free-text note |
| `created_at` | TEXT | Timestamp |

### 4.8 Indexes
```sql
idx_firs_station   ON firs(police_station_id)
idx_firs_date      ON firs(date_of_fir)
idx_firs_crime     ON firs(crime_type)
idx_accused_name   ON accused(name)
idx_accused_fir    ON accused(fir_id)
idx_victims_fir    ON victims(fir_id)
idx_alerts_read    ON alerts(is_read)
idx_audit_fir      ON fir_audit_log(fir_id)
```

---

## 5. Core Features

### 5.1 FIR Management (CRUD)

Full create, read, update, and delete operations for FIR records via REST API.

- **Create**: `POST /api/firs` — creates the FIR record, associated accused list, victims list, auto-creates districts/stations if needed, writes audit log entry, and triggers the alert engine.
- **Read (list)**: `GET /api/firs` — paginated list with filters for search term, district, crime type, status, and date range.
- **Read (detail)**: `GET /api/firs/<id>` — full record including accused and victims.
- **Update**: `PUT /api/firs/<id>` — replaces all fields, replaces accused/victim lists if provided, logs status changes.
- **Delete**: `DELETE /api/firs/<id>` — cascades to accused and victims, writes audit log entry.

**Supported status workflow:**
```
Open → Under Investigation → Chargesheeted → Closed
```

---

### 5.2 CSV Import & Export

#### Import
The CSV importer (`csv_import.py`) supports CCTNS-format exports with intelligent column mapping.

- **Auto-detection** of tab-separated vs comma-separated files
- **Column alias resolution**: accepts 30+ alternate header spellings (e.g. `fir_id`, `case_number`, `firno` all map to `fir_number`)
- **Date normalisation**: parses `DD-MM-YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-Mon-YYYY` and more
- **Duplicate guard**: skips existing FIR numbers by default; `?overwrite=1` replaces them
- **Preview mode** (`POST /api/import/preview`): returns parsed structure, mapped columns, warnings, and first 5 rows without writing to DB
- **Import mode** (`POST /api/import/csv`): bulk insert with per-row result reporting (inserted / skipped / error)

#### Export
- **CSV export** (`GET /api/firs/export/csv`): honours all list filters (district, crime_type, status, date range, search) and exports matching FIRs with accused and victim names in one CSV file.

---

### 5.3 Analytics Engine

Seven dedicated analytics endpoints feed the dashboard charts:

| Endpoint | Description |
|---|---|
| `GET /api/analytics/summary` | KPI cards: total FIRs, open cases, accused count, victim count, districts, crime distribution, monthly trend |
| `GET /api/analytics/repeated_offenders` | Accused with 2+ FIRs, sorted by FIR count, with linked crime types and districts |
| `GET /api/analytics/inter_district_offenders` | Accused active across 2+ districts |
| `GET /api/analytics/crime_patterns` | Monthly crime counts per crime type (time-series for trend chart) |
| `GET /api/analytics/hotspots` | Top district/station pairs by FIR volume with top crime types |
| `GET /api/analytics/modus_operandi` | Top MO strings by frequency with associated crime types |
| `GET /api/analytics/victim_demographics` | Gender split, injury type, age groups, top occupations, victims by crime type |

---

### 5.4 Crime Heatmap & Geo Clustering

- `GET /api/map/firs` — returns all FIRs with `lat`/`lng` coordinates for individual pin rendering. Coordinates are derived from a static lookup (`geocode.py`) with per-station offsets and small deterministic jitter to prevent stacking.
- `GET /api/map/clusters` — returns per-(district, station) crime counts with coordinates and a per-crime-type breakdown for heat cluster rendering. Uses the station's top crime type for cluster colouring.

**Geocoding strategy**: No external API required. `geocode.py` embeds coordinates for 20 districts (10 Gujarat + 10 Maharashtra) and 50+ named police stations. Unknown stations fall back to the district centroid with coordinate jitter.

---

### 5.5 Accused Network Graph

Two graph endpoints power the co-accused relationship visualisation:

#### Global Network (`GET /api/analytics/network`)
- Builds a graph of all repeat offenders (≥2 FIRs) plus anyone who shared a FIR with them
- Nodes carry: name, FIR count, crime types, repeat offender flag
- Edges carry: co-accused weight (number of shared FIRs)
- Capped at **150 nodes** for renderable performance

#### Ego Network (`GET /api/analytics/network/ego?name=<accused>`)
- Expands a single accused's full co-accused network
- Returns all FIRs for that accused (with coordinates for a side map)
- Marks the central node with `"ego": true`
- Includes co-accused edges weighted by shared FIR count

---

### 5.6 Accused Profile & Risk Scoring

`GET /api/analytics/accused/<name>` returns a complete dossier:

- Personal details (alias, age, gender, address, occupation, Aadhar, mobile)
- Full FIR history sorted by date
- District spread, crime types, modus operandi list
- **Composite Risk Score (0–100)**:

| Component | Weight | Formula |
|---|---|---|
| FIR Volume | up to 30 pts | 3 pts × FIR count (capped 30) |
| District Spread | up to 20 pts | 5 pts × district count (capped 20) |
| Crime Severity | up to 30 pts | max crime severity × 3 (capped 30) |
| Prior Offences | up to 20 pts | 4 pts × prior count (capped 20) |

**Risk Labels:**
- `Critical` — score ≥ 70
- `High` — score ≥ 45
- `Medium` — score ≥ 25
- `Low` — score < 25

**Crime severity values** (used in score calculation):

| Crime | Severity |
|---|---|
| Murder | 10 |
| Kidnapping | 9 |
| Robbery / Drug Trafficking | 8 |
| Extortion | 7 |
| Assault / Burglary / Domestic Violence | 6 |
| Vehicle Theft / Chain Snatching | 5 |
| Theft / Financial Fraud / Fraud | 4 |
| Cybercrime / Cheating | 3 |

---

### 5.7 Automated Alert Engine

The alert engine (`alerts.py`) runs automatically after every FIR creation, update, bulk status change, and CSV import. It enforces four intelligence rules:

#### Rule 1 — Repeat Offender
Fires when an accused appears in **≥ 3 FIRs**.
- Severity: `High` if ≥ 5 FIRs, otherwise `Medium`
- Updates and un-reads existing alert if FIR count grows

#### Rule 2 — Inter-District Spread
Fires when an accused is linked to FIRs across **≥ 3 districts**.
- Severity: always `High`

#### Rule 3 — MO Spike
Fires when the same modus operandi appears in FIRs across **≥ 3 districts** within the last **60 days**.
- Severity: `High`

#### Rule 4 — Crime Spike
Fires when any crime type rises **≥ 40%** month-over-month (comparing the two most recent complete months).
- Severity: `Medium`

Alerts support mark-as-read (`POST /api/alerts/<id>/read`) and mark-all-read (`POST /api/alerts/read_all`).

---

### 5.8 Full-Text Search & Autocomplete

#### FTS5 Full-Text Search (`GET /api/firs/search?q=<query>`)
- Uses SQLite FTS5 virtual table indexing `fir_number`, `crime_type`, `modus_operandi`, `location`, and `description`
- Supports prefix matching (auto-appends `*`)
- Sanitises query to avoid FTS5 special character errors
- Returns up to 30 matching FIRs with full metadata

#### Suggest / Autocomplete (`GET /api/firs/suggest?q=<query>`)
- Returns up to 10 matching accused names + up to 5 matching crime types
- Requires minimum 2 characters
- Powers the search box autocomplete dropdown

#### Standard List Filter Search (`GET /api/firs?search=<term>`)
- LIKE-based search across FIR number, crime type, district name, station name, and modus operandi
- Combines with other filters (district, crime_type, status, date range)
- Fully paginated

---

### 5.9 AI Field Extractor

`POST /api/ai/extract` — accepts a raw CCTNS FIR narrative and extracts structured fields using rule-based NLP (no external API needed).

**Extracted fields:**
- `crime_type` — matched via 17 regex patterns covering all major crime categories
- `modus_operandi` — extracted from "Modus Operandi:" label in text
- `location` — extracted from "incident at/in/on" and location-keyword patterns
- `accused_name` — extracted from "accused person was described as" or "accused: Name" patterns
- `victim_profile` — extracted from "victim profile:" label
- `repeat_offender` — boolean flag from keywords like "previously linked", "repeat", "prior case"
- `description` — first 400 characters as case narrative

Used to pre-fill the FIR creation form from pasted narrative text.

---

### 5.10 Bob AI Analyst Chat

`POST /api/ai/chat` — conversational AI analyst powered by IBM Bob LLM.

**How it works:**
1. On each request, the system calls `_gather_db_context()` which pulls a real-time statistical snapshot from the database (total FIRs by status, crime distribution, district stats, monthly trend, repeat offenders, inter-district accused, hotspots, top MO, victim gender, crime-by-status)
2. This snapshot is injected into the Bob LLM system prompt as JSON context
3. The LLM answers the analyst's question grounded strictly in the live data

**Configuration (environment variables):**

| Variable | Default | Purpose |
|---|---|---|
| `BOB_API_URL` | `http://localhost:4000` | LiteLLM / Bob inference proxy base URL |
| `BOB_API_KEY` | — | Bearer token (falls back to `BOBSHELL_API_KEY`) |
| `BOB_MODEL` | `bob` | Model name to use |

**Supported question types** (examples):
- "Which district has the most open FIRs?"
- "Who are the top repeat offenders?"
- "What crime types spiked this month?"
- "Show me inter-district offenders with murder cases"

---

### 5.11 PDF Export

Two PDF report types generated by `pdf_export.py` using `fpdf2`:

#### Individual FIR Report (`GET /api/firs/<id>/pdf`)
- FIR number, status, all case details
- Full narrative/description block
- Accused table (name, age, gender, address, prior offences)
- Victims table (name, age, gender, occupation, injury type)
- Branded header (FIR-X | Crime Intelligence System) + page footer

#### Analytics Intelligence Report (`GET /api/analytics/report/pdf`)
- Database summary KPIs (total FIRs, open cases, accused, victims, districts)
- Crime distribution table with percentage share
- Top 15 repeat offenders
- Top 15 crime hotspots by district/station
- Top 10 modus operandi

Both PDFs are served as file downloads with descriptive filenames.

---

### 5.12 Case Timeline / Audit Trail

`GET /api/firs/<id>/timeline` — returns the full ordered audit log for a single FIR:

- Every creation, update, status change, and deletion is recorded
- Entries capture: action type, actor (officer), old status, new status, note, timestamp
- Immutable — deletion of a FIR cascades to remove its audit records (foreign key)
- The audit trail is also written on bulk status updates

---

### 5.13 Bulk Status Update

`POST /api/firs/bulk_status` — update the status of multiple FIRs in one request.

```json
{ "ids": [1, 2, 3, 45], "status": "Closed" }
```

- Validates status against the allowed enum
- Writes individual audit log entries for each FIR
- Triggers the alert engine after all updates

---

### 5.14 Victim Demographics Analytics

`GET /api/analytics/victim_demographics` returns:
- Gender distribution (Male / Female / Other / Unknown)
- Injury type breakdown (None / Minor / Grievous / Fatal / Unknown)
- Age group distribution (Minor <18, 18–30, 31–45, 46–60, >60, Unknown)
- Top 8 victim occupations / profiles
- Top 10 crime types ranked by victim count

---

### 5.15 Bob Shell CLI

`bob_shell.py` provides a terminal-based intelligence interface for use without the web UI.

**Usage:**
```bash
python bob_shell.py                     # Interactive menu
python bob_shell.py --report all        # Full intelligence report
python bob_shell.py --report repeat     # Repeat offenders only
python bob_shell.py --report interdist  # Inter-district offenders
python bob_shell.py --report hotspots   # Crime hotspots
python bob_shell.py --report mo         # Top modus operandi
python bob_shell.py --report patterns   # Rising crime patterns
python bob_shell.py --search "Ravi"     # Search accused by name
```

- Uses `tabulate` for formatted terminal tables (falls back to tab-separated if not installed)
- ANSI colour output (Windows-safe with UTF-8 stdout wrapper)
- Reads directly from the same `firx.db` database

---

## 6. REST API Reference

### FIR Endpoints

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/firs` | List FIRs (paginated, filterable) |
| `POST` | `/api/firs` | Create a new FIR |
| `GET` | `/api/firs/<id>` | Get full FIR detail |
| `PUT` | `/api/firs/<id>` | Update a FIR |
| `DELETE` | `/api/firs/<id>` | Delete a FIR |
| `GET` | `/api/firs/<id>/timeline` | Case audit timeline |
| `GET` | `/api/firs/<id>/pdf` | Download FIR as PDF |
| `GET` | `/api/firs/search` | FTS5 full-text search |
| `GET` | `/api/firs/suggest` | Autocomplete suggestions |
| `GET` | `/api/firs/export/csv` | Bulk CSV export (with filters) |
| `POST` | `/api/firs/bulk_status` | Bulk status update |

### Reference Data

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/districts` | All districts |
| `GET` | `/api/stations` | All stations (filter by `?district=`) |

### Analytics

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/analytics/summary` | Dashboard KPIs |
| `GET` | `/api/analytics/repeated_offenders` | Repeat offender list |
| `GET` | `/api/analytics/inter_district_offenders` | Inter-district accused |
| `GET` | `/api/analytics/crime_patterns` | Monthly time-series |
| `GET` | `/api/analytics/hotspots` | Station-level hotspots |
| `GET` | `/api/analytics/modus_operandi` | Top MO patterns |
| `GET` | `/api/analytics/victim_demographics` | Victim breakdown |
| `GET` | `/api/analytics/network` | Co-accused network graph |
| `GET` | `/api/analytics/network/ego` | Ego network for one accused |
| `GET` | `/api/analytics/accused_names` | Autocomplete for network search |
| `GET` | `/api/analytics/accused/<name>` | Full accused profile + risk score |
| `GET` | `/api/analytics/report/pdf` | Download analytics PDF |

### Map / Geo

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/map/firs` | All FIRs with lat/lng |
| `GET` | `/api/map/clusters` | Cluster data for heatmap |

### Alerts

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/alerts` | List alerts + unread count |
| `POST` | `/api/alerts/<id>/read` | Mark one alert read |
| `POST` | `/api/alerts/read_all` | Mark all alerts read |

### Import

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/import/preview` | CSV parse preview (no DB write) |
| `POST` | `/api/import/csv` | CSV bulk import |

### AI

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/ai/extract` | Extract fields from FIR narrative |
| `POST` | `/api/ai/chat` | Bob AI analyst chat |

---

## 7. Alert Engine Rules

```
Rule 1: Repeat Offender
  Trigger : accused.fir_count >= 3
  Severity: High (>= 5 FIRs) | Medium (3–4 FIRs)
  Action  : Insert or update alert, un-read if count grew

Rule 2: Inter-District Spread
  Trigger : accused.district_count >= 3
  Severity: High
  Action  : Insert or update alert

Rule 3: MO Spike (60-day window)
  Trigger : same modus_operandi in firs across >= 3 distinct districts
            within the past 60 days
  Severity: High
  Action  : Insert or update alert

Rule 4: Crime Spike (Month-over-Month)
  Trigger : crime_count[last_month] / crime_count[prev_month] >= 1.40
            (i.e., >= 40% increase)
  Severity: Medium
  Action  : Insert or update alert
```

---

## 8. Risk Scoring Model

```
risk_score = vol + dist + sev + prior_pts

  vol       = min(fir_count × 3,    30)   # FIR volume      → max 30 pts
  dist      = min(district_count × 5, 20)  # District spread → max 20 pts
  sev       = min(max_severity × 3,  30)   # Crime severity  → max 30 pts
  prior_pts = min(prior_offences × 4, 20)  # Prior offences  → max 20 pts

Labels:
  Critical : score >= 70
  High     : score >= 45
  Medium   : score >= 25
  Low      : score <  25
```

---

## 9. Geocoding System

Static coordinate lookup without any external API call:

- **20 districts** embedded with centroid coordinates (Gujarat + Maharashtra)
- **50+ named police stations** with per-station lat/lng offsets from district centroid
- **Fallback**: unknown stations use district centroid + deterministic hash-based jitter
- **India fallback**: `(20.5937, 78.9629)` for completely unknown districts

---

## 10. Running the Application

### Prerequisites
```bash
pip install flask flask-cors fpdf2 tabulate
```

### Start the server
```bash
python app.py
# Server runs on http://localhost:5000
```

### Seed sample data
```bash
python seed_data.py
```

### Import a CSV file via CLI
```bash
python csv_import.py FIR-X_500_FIR_Dataset_Structured.csv
python csv_import.py sample_firs_100.csv --overwrite
```

### Run the intelligence CLI shell
```bash
python bob_shell.py --report all
python bob_shell.py --search "Ravi Kumar"
```

### Configure Bob AI (optional)
```bash
set BOB_API_URL=http://localhost:4000
set BOB_API_KEY=your-api-key
set BOB_MODEL=bob
python app.py
```

---

## 11. CSV Format Specification

The CSV importer accepts both comma-separated and tab-separated files with the following columns (any of the listed aliases are accepted):

| Canonical Field | Accepted Header Names | Required |
|---|---|---|
| `fir_number` | `fir_id`, `fir_number`, `fir no`, `firno`, `case_number` | ✅ |
| `station` | `station`, `police_station`, `ps`, `police station` | ✅ |
| `district` | `district`, `dist`, `district_name` | ✅ |
| `date` | `date`, `date_of_fir`, `fir_date`, `incident_date` | ✅ |
| `crime_type` | `crime_type`, `crime type`, `offence_type`, `type_of_crime` | — |
| `accused_name` | `accused_name`, `accused name`, `accused`, `offender_name` | — |
| `accused_description` | `accused_description`, `accused desc`, `suspect_description` | — |
| `location` | `location`, `place`, `place_of_offence`, `scene`, `incident_location` | — |
| `modus_operandi` | `modus_operandi`, `modus operandi`, `mo`, `method`, `methodology` | — |
| `victim_profile` | `victim_profile`, `victim profile`, `victim`, `complainant_profile` | — |
| `repeat_offender_signature` | `repeat_offender_signature`, `repeat offender`, `linked_fir`, `connection` | — |
| `raw_text` | `raw_text`, `raw text`, `description`, `narrative`, `details` | — |

**Accepted date formats:** `DD-MM-YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `DD-Mon-YYYY`, `DD Mon YYYY`, `DD Month YYYY`

**Repeat offender truthy values:** `yes`, `y`, `true`, `1`, `linked`, `flagged`

---

*FIR-X — Crime Intelligence System | IBM Hackathon Project*

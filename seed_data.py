"""
seed_data.py  –  Populate firx.db with realistic Indian CCTNS-style sample data
Run: python seed_data.py
"""

import sqlite3, random, os
from datetime import date, timedelta
from database import init_db, get_conn, get_or_create_station

# ── Reference tables ─────────────────────────────────────────────────────────

DISTRICTS = [
    "Mumbai", "Pune", "Nagpur", "Nashik", "Aurangabad",
    "Thane", "Kolhapur", "Solapur", "Amravati", "Nanded"
]

STATIONS = {
    "Mumbai":     ["Andheri", "Bandra", "Dadar", "Kurla", "Borivali"],
    "Pune":       ["Shivajinagar", "Kothrud", "Hadapsar", "Pimpri", "Wakad"],
    "Nagpur":     ["Sitabuldi", "Sadar", "Lakadganj", "Nandanvan", "Hingna"],
    "Nashik":     ["Nashik Road", "Cidco", "Satpur", "Panchvati", "Trimbak"],
    "Aurangabad": ["Cidco", "Mukundwadi", "Kranti Chowk", "Osmanpura"],
    "Thane":      ["Thane City", "Kalyan", "Dombivali", "Ambernath", "Ulhasnagar"],
    "Kolhapur":   ["Shahupuri", "Tarabai", "Karveer", "Kagal"],
    "Solapur":    ["Solapur City", "Akkalkot", "Pandharpur", "Barshi"],
    "Amravati":   ["Amravati City", "Daryapur", "Chandur Bazar"],
    "Nanded":     ["Nanded City", "Deglur", "Kandhar"],
}

CRIME_TYPES = [
    "Theft", "Robbery", "Burglary", "Murder", "Assault",
    "Kidnapping", "Fraud", "Cybercrime", "Drug Trafficking",
    "Vehicle Theft", "Chain Snatching", "Extortion",
]

MODUS_OPERANDI = [
    "Lock-breaking at night",
    "Distraction theft in crowded areas",
    "Confidence trick / impersonation",
    "Online phishing via fake links",
    "ATM skimming",
    "Vehicle hopping",
    "Social engineering over phone",
    "Gang ambush on highway",
    "Using duplicate keys",
    "Posing as government official",
    "Armed robbery at gunpoint",
    "Drug peddling through couriers",
    "Ransomware attack",
    "Domestic violence escalation",
]

SECTIONS = [
    "IPC 302", "IPC 307", "IPC 376", "IPC 395", "IPC 420",
    "IPC 379", "IPC 380", "IPC 365", "IPC 323", "NDPS Act S.20",
    "IT Act S.66C", "IPC 392", "IPC 506", "IPC 354",
]

STATUS_CHOICES = ["Open", "Under Investigation", "Chargesheeted", "Closed"]
STATUS_WEIGHTS = [0.35, 0.30, 0.20, 0.15]

MALE_NAMES   = ["Ravi Kumar", "Suresh Patil", "Mohan Desai", "Arjun Sharma", "Deepak Yadav",
                "Rahul Mehta", "Sanjay Gupta", "Vikram Singh", "Ajay Tiwari", "Nitin Joshi",
                "Rohit Verma", "Anil Chauhan", "Manish Kale", "Santosh Thakur", "Kiran Pawar"]
FEMALE_NAMES = ["Priya Sharma", "Sunita Patil", "Rekha Devi", "Meena Kumari", "Anita Gupta",
                "Kavita Joshi", "Pooja Yadav", "Nisha Singh", "Lata Bhosale", "Sakshi More"]
ALL_NAMES    = MALE_NAMES + FEMALE_NAMES

OCCUPATIONS  = ["Labourer", "Farmer", "Student", "Shopkeeper", "Driver", "Unknown",
                "Mechanic", "Contractor", "Unemployed", "Small Business Owner"]

INJURY_TYPES = ["None", "Minor", "Grievous", "Fatal", "Unknown"]

random.seed(42)


def rand_date(start_year=2021, end_year=2024):
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))


def weighted_choice(choices, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    upto = 0
    for c, w in zip(choices, weights):
        upto += w
        if r <= upto:
            return c
    return choices[-1]


def seed(n_firs=200):
    init_db()
    conn = get_conn()

    # clear existing seed data if any
    conn.execute("DELETE FROM accused")
    conn.execute("DELETE FROM victims")
    conn.execute("DELETE FROM firs")
    conn.execute("DELETE FROM police_stations")
    conn.execute("DELETE FROM districts")
    conn.commit()

    fir_count = 0

    # A pool of ~30 accused (some will appear in multiple FIRs to simulate repeat offenders)
    accused_pool = [random.choice(MALE_NAMES + FEMALE_NAMES) for _ in range(30)]

    for i in range(1, n_firs + 1):
        district = random.choice(DISTRICTS)
        station  = random.choice(STATIONS[district])
        station_id = get_or_create_station(conn, station, district)

        fir_date    = rand_date()
        offence_date = fir_date - timedelta(days=random.randint(0, 5))
        crime       = random.choice(CRIME_TYPES)
        mo          = random.choice(MODUS_OPERANDI)
        section     = random.choice(SECTIONS)
        status      = weighted_choice(STATUS_CHOICES, STATUS_WEIGHTS)

        fir_number = f"FIR/{district[:3].upper()}/{fir_date.year}/{i:04d}"

        cur = conn.execute("""
            INSERT INTO firs
              (fir_number, date_of_fir, date_of_offence,
               police_station_id, section_of_law,
               crime_type, modus_operandi, description, status)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            fir_number, str(fir_date), str(offence_date),
            station_id, section, crime, mo,
            f"Case registered for {crime.lower()} at {station} Police Station, {district}.",
            status,
        ))
        fir_id = cur.lastrowid

        # ── Accused (1-3 per FIR; reuse pool for repeat offenders) ──────────
        n_accused = random.randint(1, 3)
        for _ in range(n_accused):
            acc_name = random.choice(accused_pool)
            gender   = "Male" if acc_name in MALE_NAMES else "Female"
            home_dist = random.choice(DISTRICTS)
            from database import get_or_create_district
            dist_id  = get_or_create_district(conn, home_dist)

            conn.execute("""
                INSERT INTO accused
                  (fir_id, name, alias, age, gender, address,
                   district_id, occupation, prior_offences, mobile_number)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                fir_id,
                acc_name,
                acc_name.split()[0] + "bhai" if random.random() < 0.3 else None,
                random.randint(18, 55),
                gender,
                f"{random.randint(1,99)}, {random.choice(['MG Road','Station Road','Market Area','Old Town'])}, {home_dist}",
                dist_id,
                random.choice(OCCUPATIONS),
                random.randint(0, 4),
                f"9{random.randint(100000000,999999999)}",
            ))

        # ── Victims (1-2 per FIR) ────────────────────────────────────────────
        n_victims = random.randint(1, 2)
        for _ in range(n_victims):
            vic_name = random.choice(ALL_NAMES)
            gender   = "Male" if vic_name in MALE_NAMES else "Female"
            conn.execute("""
                INSERT INTO victims
                  (fir_id, name, age, gender, address,
                   occupation, injury_type, mobile_number)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                fir_id,
                vic_name,
                random.randint(10, 80),
                gender,
                f"{random.randint(1,99)}, {random.choice(['Park Lane','Ring Road','Shivaji Nagar','Nehru Road'])}, {district}",
                random.choice(OCCUPATIONS),
                random.choice(INJURY_TYPES),
                f"9{random.randint(100000000,999999999)}",
            ))

        fir_count += 1

    conn.commit()
    conn.close()
    print(f"[Seed] Inserted {fir_count} FIRs into firx.db")


if __name__ == "__main__":
    seed(200)

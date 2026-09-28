"""
generate_sample_csv.py  -  Generate 100 realistic CCTNS-style FIR rows
Output: sample_firs_100.csv  (comma-separated, all 12 columns)
Run:    python generate_sample_csv.py
"""

import csv
import random
from datetime import date, timedelta

random.seed(2024)

# ── Reference data ────────────────────────────────────────────────────────────

DISTRICTS_STATIONS = {
    "Ahmedabad": [
        "Chandkheda PS", "Vastrapur PS", "Naranpura PS", "Satellite PS",
        "Maninagar PS", "Bapunagar PS", "Navrangpura PS", "Ghatlodia PS",
        "Bodakdev PS", "Nikol PS",
    ],
    "Vadodara": [
        "Karelibaug PS", "Alkapuri PS", "Fatehgunj PS", "Manjalpur PS",
        "Gotri PS", "Harni PS", "Waghodia PS",
    ],
    "Surat": [
        "Athwa PS", "Katargam PS", "Varachha PS", "Salabatpura PS",
        "Limbayat PS", "Umra PS", "Rundh PS",
    ],
    "Rajkot": [
        "Rajkot City PS", "Malviya Nagar PS", "Bhaktinagar PS",
        "Kalavad Road PS", "Aji Dam PS",
    ],
    "Gandhinagar": [
        "Gandhinagar Sector 7 PS", "Gandhinagar Sector 21 PS",
        "Mansa PS", "Kalol PS",
    ],
    "Anand": [
        "Anand City PS", "Vallabh Vidyanagar PS", "Anklav PS", "Borsad PS",
    ],
    "Mehsana": [
        "Mehsana City PS", "Visnagar PS", "Kheralu PS", "Unjha PS",
    ],
    "Bharuch": [
        "Bharuch City PS", "Ankleshwar PS", "Jambusar PS",
    ],
    "Junagadh": [
        "Junagadh City PS", "Keshod PS", "Veraval PS", "Talala PS",
    ],
    "Amreli": [
        "Amreli City PS", "Savarkundla PS", "Rajula PS",
    ],
}

CRIME_TYPES = [
    "Burglary", "Theft", "Robbery", "Extortion", "Murder",
    "Assault", "Kidnapping", "Financial Fraud", "Cybercrime - Fraud",
    "Cybercrime - Harassment", "Drug Trafficking", "Vehicle Theft",
    "Chain Snatching", "Cheating", "Domestic Violence",
]

MODUS_OPERANDI_BY_CRIME = {
    "Burglary":                ["cut a grill", "broke door lock", "entered through ventilation", "used duplicate keys", "scaled compound wall"],
    "Theft":                   ["pick-pocketing in crowd", "distraction theft at ATM", "stole from unattended vehicle", "shoplifting", "theft during travel"],
    "Robbery":                 ["armed robbery at gunpoint", "group ambush on road", "snatched bag and fled on bike", "overpowered victim at night", "robbery at knifepoint"],
    "Extortion":               ["demanded money using threats", "threatened via phone calls", "sent threatening letters", "online blackmail with personal data", "threatened business owner repeatedly"],
    "Murder":                  ["stabbed during dispute", "poisoned food", "blunt weapon assault", "hired contract killer", "strangulation during fight"],
    "Assault":                 ["physical altercation with weapon", "group assault after dispute", "attacked with iron rod", "acid attack", "hit with blunt object"],
    "Kidnapping":              ["lured victim with false job offer", "abducted minor from school vicinity", "kidnapped for ransom", "forced into vehicle", "impersonated official to abduct"],
    "Financial Fraud":         ["collected an advance and became unreachable", "forged property documents", "fake investment scheme", "chit fund fraud", "impersonated bank official"],
    "Cybercrime - Fraud":      ["created fake online shopping portal", "OTP phishing via SMS", "fake lottery call", "UPI payment fraud via QR code", "loan app fraud"],
    "Cybercrime - Harassment": ["sent threatening messages online", "created fake profile to defame", "shared morphed images on social media", "online stalking through multiple accounts", "hacked personal email to extort"],
    "Drug Trafficking":        ["transported narcotics concealed in vegetables", "used courier service for delivery", "operated through school-area peddler network", "sold near highway dhabas", "used coded messaging app"],
    "Vehicle Theft":           ["stole two-wheeler with duplicate key", "towed away car at night", "cut steering lock", "vehicle stolen from parking lot", "distracted owner and drove away"],
    "Chain Snatching":         ["snatched gold chain from woman on bike", "grabbed chain near temple area", "two-bike accomplice grab and flee", "pushed victim and snatched chain", "snatched from elderly victim at bus stop"],
    "Cheating":                ["posed as government contractor", "submitted fake academic certificates", "collected fees for non-existent services", "sold fake gold jewellery", "forged signatures on cheque"],
    "Domestic Violence":       ["repeated physical assault at home", "mental harassment over dowry", "threatened to harm children", "locked victim inside house", "assault after alcohol consumption"],
}

LOCATIONS_BY_CRIME = {
    "Burglary":                ["residential flat", "jewellery shop", "office premises", "warehouse", "school building"],
    "Theft":                   ["crowded market", "railway station", "ATM kiosk", "bus stand", "petrol pump"],
    "Robbery":                 ["isolated highway stretch", "late-night road", "bank branch", "jewellery shop", "petrol station"],
    "Extortion":               ["online messaging platform", "victim's shop", "mobile phone call", "business premises", "WhatsApp chat"],
    "Murder":                  ["open ground", "victim's residence", "agricultural field", "hotel room", "roadside"],
    "Assault":                 ["public road", "neighbour's compound", "workplace", "liquor shop vicinity", "street"],
    "Kidnapping":              ["school vicinity", "bus stop", "victim's workplace", "public road", "market area"],
    "Financial Fraud":         ["loan service", "property registration office", "online trading platform", "bank branch", "investment firm"],
    "Cybercrime - Fraud":      ["online shopping portal", "mobile banking app", "fake website", "UPI platform", "email"],
    "Cybercrime - Harassment": ["fake profile", "social media platform", "email account", "WhatsApp group", "dating app"],
    "Drug Trafficking":        ["national highway", "school vicinity", "residential colony", "railway goods yard", "nightclub"],
    "Vehicle Theft":           ["public parking lot", "residential society", "market parking", "workplace parking", "roadside"],
    "Chain Snatching":         ["temple premises", "market lane", "bus stop", "morning walk path", "residential lane"],
    "Cheating":                ["registrar office", "bank premises", "victim's residence", "online platform", "construction site"],
    "Domestic Violence":       ["victim's residence", "in-laws' home", "rented accommodation", "family home", "shared residence"],
}

VICTIM_PROFILES = {
    "Burglary":                ["family residence", "shop owner", "business owner", "tenant family", "landlord"],
    "Theft":                   ["daily commuter", "tourist", "shopkeeper", "student", "elderly person"],
    "Robbery":                 ["small trader", "bank customer", "petrol pump worker", "jeweller", "night shift worker"],
    "Extortion":               ["business owner", "property owner", "shopkeeper", "contractor", "local politician"],
    "Murder":                  ["farm labourer", "family member", "rival gang member", "property dispute party", "domestic worker"],
    "Assault":                 ["neighbour", "business rival", "family member", "road user", "daily wager"],
    "Kidnapping":              ["school student", "minor child", "young woman", "businessman", "domestic worker"],
    "Financial Fraud":         ["property owner", "retired government employee", "small investor", "NRI", "senior citizen"],
    "Cybercrime - Fraud":      ["online shopper", "bank account holder", "job seeker", "loan applicant", "housewife"],
    "Cybercrime - Harassment": ["student", "young woman", "teacher", "journalist", "social worker"],
    "Drug Trafficking":        ["school student", "youth", "daily wager", "auto driver", "unemployed youth"],
    "Vehicle Theft":           ["two-wheeler owner", "car owner", "delivery agent", "office-goer", "student"],
    "Chain Snatching":         ["elderly woman", "housewife", "temple visitor", "market shopper", "morning walker"],
    "Cheating":                ["job seeker", "farmer", "home buyer", "shopkeeper", "small business owner"],
    "Domestic Violence":       ["married woman", "daughter-in-law", "minor child", "elderly parent", "spouse"],
}

ACCUSED_FIRST = [
    "Rajan", "Suresh", "Mukesh", "Bhavesh", "Kiran", "Nilesh", "Dinesh",
    "Vijay", "Pramod", "Sanjay", "Hardik", "Jignesh", "Paresh", "Rakesh",
    "Mahesh", "Hitesh", "Prashant", "Chirag", "Devang", "Manish",
    "Priya", "Kavita", "Bhavna", "Rekha", "Sunita", "Meena", "Nisha",
    "Hetal", "Minal", "Komal", "Pooja", "Divya", "Ruchita", "Jalpa",
    "Bina", "Chandrika", "Varsha", "Rima", "Sapna", "Leela",
]

ACCUSED_LAST = [
    "Shah", "Patel", "Desai", "Mehta", "Joshi", "Rao", "Bhatt",
    "Yadav", "Chauhan", "Singh", "Thakkar", "Modi", "Pandya",
    "Parmar", "Trivedi", "Nair", "Iyer", "Sharma", "Verma", "Gupta",
    "Solanki", "Makwana", "Gohil", "Jadeja", "Vaghela", "Chavda",
    "Rabari", "Bhavsar", "Luhar", "Darji",
]

DESCRIPTIONS = [
    "tall male with beard, known to local police",
    "fair complexion, medium build, usually seen on motorcycle",
    "short stature, speaks Gujarati and Hindi",
    "has tattoo on right arm, frequent offender",
    "wears spectacles, works as auto driver",
    "woman in her 30s, used to visit victim's shop",
    "young male approximately 22 years, student of nearby college",
    "bald, heavy-built, runs small eatery near the area",
    "dark complexion, regular visitor to the neighbourhood",
    "drives a blue Activa scooter, identified by multiple witnesses",
    "has previous record of theft, known to local beat officer",
    "migrant worker, resided near the incident site for 2 months",
    "works as electrician, had access to the building",
    "regular at local paan shop, recognised by CCTV footage",
    "speaks with slight accent, claims to be from Rajasthan",
]

IPC_SECTIONS = {
    "Burglary":                "IPC 457/380",
    "Theft":                   "IPC 379",
    "Robbery":                 "IPC 392",
    "Extortion":               "IPC 384",
    "Murder":                  "IPC 302",
    "Assault":                 "IPC 323/325",
    "Kidnapping":              "IPC 363/365",
    "Financial Fraud":         "IPC 420/406",
    "Cybercrime - Fraud":      "IT Act Sec 66C/66D",
    "Cybercrime - Harassment": "IT Act Sec 67 / IPC 354D",
    "Drug Trafficking":        "NDPS Act Sec 20/21",
    "Vehicle Theft":           "IPC 379/411",
    "Chain Snatching":         "IPC 356/379",
    "Cheating":                "IPC 420/467",
    "Domestic Violence":       "DV Act / IPC 498A",
}

# A pool of ~25 names reused across FIRs to generate repeat & inter-district offenders
REPEAT_POOL = [
    "Rajan Shah", "Bhavesh Patel", "Mukesh Yadav", "Kiran Bhatt",
    "Suresh Solanki", "Jignesh Desai", "Nisha Parmar", "Vijay Gohil",
    "Priya Mehta", "Hardik Chauhan",
]


def rand_date(start=date(2022, 1, 1), end=date(2024, 12, 31)):
    return start + timedelta(days=random.randint(0, (end - start).days))


def build_raw_text(fir_id, station, district, date_str, crime, location, mo, accused, victim_profile, repeat):
    repeat_line = (
        f"This accused was previously linked to FIR in {random.choice(list(DISTRICTS_STATIONS.keys()))} district."
        if repeat else
        "No established connection to another FIR is recorded in this narrative."
    )
    return (
        f"Complainant reported a {crime.lower()} incident at {location}. "
        f"An accused person was described as {accused}. "
        f"Modus operandi: {mo}. "
        f"Victim profile: {victim_profile}. "
        f"{repeat_line}"
    )


def generate(n=100, out="sample_firs_100.csv"):
    fieldnames = [
        "fir_id", "station", "district", "date", "crime_type",
        "accused_name", "accused_description", "location",
        "modus_operandi", "victim_profile",
        "repeat_offender_signature", "raw_text",
    ]

    rows = []
    used_fir_ids = set()
    district_list = list(DISTRICTS_STATIONS.keys())

    for i in range(1, n + 1):
        district  = random.choice(district_list)
        station   = random.choice(DISTRICTS_STATIONS[district])
        crime     = random.choice(CRIME_TYPES)
        fir_date  = rand_date()
        date_str  = fir_date.strftime("%d-%m-%Y")

        # ~20% of rows use a name from the repeat-offender pool
        use_repeat_name = random.random() < 0.20
        if use_repeat_name:
            accused_name = random.choice(REPEAT_POOL)
            repeat_flag  = random.choice(["Yes", "Yes", ""])   # 66% flagged when repeat pool
        else:
            first = random.choice(ACCUSED_FIRST)
            last  = random.choice(ACCUSED_LAST)
            accused_name = f"{first} {last}"
            repeat_flag  = ""

        accused_desc  = random.choice(DESCRIPTIONS)
        location      = random.choice(LOCATIONS_BY_CRIME[crime])
        mo            = random.choice(MODUS_OPERANDI_BY_CRIME[crime])
        victim_profile= random.choice(VICTIM_PROFILES[crime])

        # Unique FIR ID
        year  = fir_date.year
        fir_id = f"FIR/{year}/{i:05d}"
        while fir_id in used_fir_ids:
            i += 1
            fir_id = f"FIR/{year}/{i:05d}"
        used_fir_ids.add(fir_id)

        raw = build_raw_text(
            fir_id, station, district, date_str,
            crime, location, mo, accused_name, victim_profile,
            bool(repeat_flag)
        )

        rows.append({
            "fir_id":                    fir_id,
            "station":                   station,
            "district":                  district,
            "date":                      date_str,
            "crime_type":                crime,
            "accused_name":              accused_name,
            "accused_description":       accused_desc,
            "location":                  location,
            "modus_operandi":            mo,
            "victim_profile":            victim_profile,
            "repeat_offender_signature": repeat_flag,
            "raw_text":                  raw,
        })

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows -> {out}")
    repeat_count = sum(1 for r in rows if r["repeat_offender_signature"])
    names_used = {}
    for r in rows:
        names_used[r["accused_name"]] = names_used.get(r["accused_name"], 0) + 1
    multi = {k: v for k, v in names_used.items() if v > 1}
    print(f"Repeat-flagged rows : {repeat_count}")
    print(f"Accused names appearing 2+ times : {len(multi)}")
    for nm, cnt in sorted(multi.items(), key=lambda x: -x[1])[:8]:
        print(f"  {nm}: {cnt} FIRs")


if __name__ == "__main__":
    generate(100)

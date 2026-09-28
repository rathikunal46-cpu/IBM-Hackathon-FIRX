"""
geocode.py  -  Static district/station coordinate lookup for FIR-X heatmap.
No external API needed — coordinates are embedded for all seeded districts.
Falls back to district centroid when station is unknown.
"""

# District centroids  {district_name: (lat, lng)}
DISTRICT_COORDS = {
    # Gujarat
    "Ahmedabad":   (23.0225, 72.5714),
    "Vadodara":    (22.3072, 73.1812),
    "Surat":       (21.1702, 72.8311),
    "Rajkot":      (22.3039, 70.8022),
    "Gandhinagar": (23.2156, 72.6369),
    "Anand":       (22.5645, 72.9289),
    "Mehsana":     (23.5880, 72.3693),
    "Bharuch":     (21.7051, 72.9959),
    "Junagadh":    (21.5222, 70.4579),
    "Amreli":      (21.6032, 71.2219),
    # Maharashtra (seed data)
    "Mumbai":      (19.0760, 72.8777),
    "Pune":        (18.5204, 73.8567),
    "Nagpur":      (21.1458, 79.0882),
    "Nashik":      (19.9975, 73.7898),
    "Aurangabad":  (19.8762, 75.3433),
    "Thane":       (19.2183, 72.9781),
    "Kolhapur":    (16.7050, 74.2433),
    "Solapur":     (17.6805, 75.9064),
    "Amravati":    (20.9374, 77.7796),
    "Nanded":      (19.1383, 77.3210),
}

# Station offsets  {station_name_lower: (delta_lat, delta_lng)}
# Small jitter so pins don't overlap on same district centroid
_STATION_OFFSETS = {
    # Ahmedabad
    "chandkheda":    (+0.12,  -0.05),
    "vastrapur":     (+0.02,  +0.08),
    "naranpura":     (+0.04,  +0.03),
    "satellite":     (-0.01,  +0.07),
    "maninagar":     (-0.08,  +0.04),
    "bapunagar":     (+0.06,  -0.02),
    "navrangpura":   (+0.01,  +0.01),
    "ghatlodia":     (+0.10,  +0.06),
    "bodakdev":      (-0.02,  +0.09),
    "nikol":         (+0.05,  +0.12),
    # Vadodara
    "karelibaug":    (+0.04,  +0.06),
    "alkapuri":      (-0.02,  -0.03),
    "fatehgunj":     (+0.06,  -0.05),
    "manjalpur":     (-0.06,  +0.04),
    "gotri":         (+0.03,  +0.08),
    "harni":         (-0.04,  +0.10),
    "waghodia":      (-0.09,  +0.05),
    # Surat
    "athwa":         (+0.03,  +0.04),
    "katargam":      (+0.07,  -0.03),
    "varachha":      (+0.05,  +0.07),
    "salabatpura":   (-0.03,  +0.02),
    "limbayat":      (-0.06,  +0.06),
    "umra":          (+0.02,  -0.05),
    "rundh":         (-0.04,  -0.04),
    # Rajkot
    "rajkot city":   (+0.01,  +0.01),
    "malviya nagar": (+0.05,  +0.04),
    "bhaktinagar":   (-0.04,  +0.03),
    "kalavad road":  (+0.03,  -0.06),
    "aji dam":       (-0.03,  -0.04),
    # Mumbai
    "andheri":       (+0.08,  +0.03),
    "bandra":        (-0.04,  +0.02),
    "dadar":         (-0.10,  -0.01),
    "kurla":         (-0.06,  +0.05),
    "borivali":      (+0.15,  -0.04),
    # Pune
    "shivajinagar":  (+0.02,  -0.02),
    "kothrud":       (-0.04,  -0.06),
    "hadapsar":      (+0.01,  +0.09),
    "pimpri":        (+0.12,  -0.05),
    "wakad":         (+0.08,  -0.09),
}

import re

def _strip_ps(name: str) -> str:
    """Remove ' PS' / ' Police Station' suffix for lookup."""
    return re.sub(r"\s*(police\s+station|p\.s\.|ps)\s*$", "", name.strip(), flags=re.I).strip().lower()


def get_coords(district: str, station: str = "") -> tuple[float, float]:
    """
    Return (lat, lng) for a district+station pair.
    Falls back to district centroid with small random-ish jitter if station unknown.
    """
    base = DISTRICT_COORDS.get(district)
    if base is None:
        # Try case-insensitive match
        lc = district.lower()
        for k, v in DISTRICT_COORDS.items():
            if k.lower() == lc:
                base = v
                break
    if base is None:
        return (20.5937, 78.9629)   # India centre fallback

    key = _strip_ps(station)
    offset = _STATION_OFFSETS.get(key, (0.0, 0.0))
    return (round(base[0] + offset[0], 6), round(base[1] + offset[1], 6))

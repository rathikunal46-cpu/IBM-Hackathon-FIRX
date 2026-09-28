"""
pdf_export.py  -  FIR-X PDF generator using fpdf2
Produces:
  - fir_report(fir_dict)   -> bytes  (single FIR detail sheet)
  - analytics_report(data) -> bytes  (summary + repeat offenders + hotspots)
"""

from fpdf import FPDF
from datetime import datetime


ACCENT = (37, 99, 235)    # blue
DARK   = (13, 17, 23)
LIGHT  = (230, 237, 243)
MUTED  = (125, 133, 144)
RED    = (218, 54, 51)
GREEN  = (35, 134, 54)
YELLOW = (210, 153, 34)


def _s(v, maxlen: int = 120) -> str:
    """Convert value to ASCII-safe string for fpdf core fonts."""
    if v is None:
        return "-"
    txt = str(v)
    # replace non-latin-1 chars
    txt = txt.encode("latin-1", errors="replace").decode("latin-1")
    return txt[:maxlen]


class _PDF(FPDF):
    def header(self):
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*LIGHT)
        self.set_xy(8, 3)
        self.cell(0, 8, "FIR-X  |  Crime Intelligence System", ln=False)
        self.set_xy(0, 3)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(200, 210, 230)
        self.cell(202, 8, datetime.now().strftime("%d %b %Y  %H:%M"), align="R")
        self.ln(16)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def section_title(self, text: str):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*LIGHT)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, f"  {text}", ln=True, fill=True)
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def kv_row(self, key: str, value: str, shade: bool = False):
        if shade:
            self.set_fill_color(240, 242, 245)
        else:
            self.set_fill_color(255, 255, 255)
        # Render key + value on same line; use fixed widths so multi_cell has room
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*MUTED)
        self.cell(52, 6, key[:28], fill=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 35, 40)
        self.cell(0, 6, _s(value), ln=True, fill=True)

    def table_header(self, cols: list[tuple[str, int]]):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*LIGHT)
        self.set_font("Helvetica", "B", 8)
        for label, w in cols:
            self.cell(w, 6, label, border=0, fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(self, values: list, cols: list[tuple[str, int]], shade: bool):
        if shade:
            self.set_fill_color(245, 247, 250)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_font("Helvetica", "", 8)
        for (_, w), val in zip(cols, values):
            self.cell(w, 5, _s(val, 40), fill=True)
        self.ln()


# ── Public API ────────────────────────────────────────────────────────────────

def fir_report(fir: dict) -> bytes:
    """Generate a single-FIR detail PDF. Returns bytes."""
    pdf = _PDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(10, 18, 10)

    # Title block
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 10, fir.get("fir_number", "FIR Report"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    status = fir.get("status", "Open")
    pdf.cell(0, 5, f"Status: {status}   |   Crime: {_s(fir.get('crime_type'))}   |   Date: {_s(fir.get('date_of_fir'))}", ln=True)
    pdf.ln(4)

    # Case details
    pdf.section_title("CASE DETAILS")
    shade = False
    for k, v in [
        ("FIR Number",      fir.get("fir_number")),
        ("Date of FIR",     fir.get("date_of_fir")),
        ("Date of Offence", fir.get("date_of_offence")),
        ("District",        fir.get("district_name")),
        ("Police Station",  fir.get("station_name")),
        ("Crime Type",      fir.get("crime_type")),
        ("Section of Law",  fir.get("section_of_law")),
        ("Location",        fir.get("location")),
        ("Modus Operandi",  fir.get("modus_operandi")),
        ("Status",          fir.get("status")),
    ]:
        pdf.kv_row(k, v, shade)
        shade = not shade
    pdf.ln(3)

    # Description
    if fir.get("description"):
        pdf.section_title("NARRATIVE / DESCRIPTION")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 35, 40)
        pdf.multi_cell(0, 5, fir["description"])
        pdf.ln(3)

    # Accused
    accused_list = fir.get("accused", [])
    pdf.section_title(f"ACCUSED  ({len(accused_list)})")
    if accused_list:
        cols = [("Name", 50), ("Age", 15), ("Gender", 20), ("Address / Description", 70), ("Prior Offences", 35)]
        pdf.table_header(cols)
        for i, a in enumerate(accused_list):
            pdf.table_row([
                a.get("name"), a.get("age"), a.get("gender"),
                a.get("address"), a.get("prior_offences", 0),
            ], cols, i % 2 == 0)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, "No accused recorded.", ln=True)
    pdf.ln(3)

    # Victims
    victims_list = fir.get("victims", [])
    pdf.section_title(f"VICTIMS  ({len(victims_list)})")
    if victims_list:
        cols = [("Name", 50), ("Age", 15), ("Gender", 20), ("Occupation / Profile", 65), ("Injury", 40)]
        pdf.table_header(cols)
        for i, v in enumerate(victims_list):
            pdf.table_row([
                v.get("name"), v.get("age"), v.get("gender"),
                v.get("occupation"), v.get("injury_type"),
            ], cols, i % 2 == 0)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, "No victim recorded.", ln=True)

    return bytes(pdf.output())


def analytics_report(summary: dict, repeat: list, hotspots: list, mo: list) -> bytes:
    """Generate an analytics summary PDF. Returns bytes."""
    pdf = _PDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(10, 18, 10)

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 10, "FIR-X Crime Intelligence Report", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}", ln=True)
    pdf.ln(4)

    # Summary stats
    pdf.section_title("DATABASE SUMMARY")
    shade = False
    for k, v in [
        ("Total FIRs",       summary.get("total_firs")),
        ("Open Cases",       summary.get("open_firs")),
        ("Total Accused",    summary.get("total_accused")),
        ("Total Victims",    summary.get("total_victims")),
        ("Districts Covered",summary.get("districts")),
    ]:
        pdf.kv_row(k, v, shade)
        shade = not shade
    pdf.ln(3)

    # Crime distribution
    if summary.get("crime_distribution"):
        pdf.section_title("CRIME DISTRIBUTION")
        cols = [("Crime Type", 110), ("FIR Count", 30), ("Share", 50)]
        pdf.table_header(cols)
        total = sum(r["count"] for r in summary["crime_distribution"]) or 1
        for i, r in enumerate(summary["crime_distribution"]):
            pct = f"{r['count']/total*100:.1f}%"
            pdf.table_row([r["crime_type"], r["count"], pct], cols, i % 2 == 0)
        pdf.ln(3)

    # Repeat offenders
    if repeat:
        pdf.section_title("TOP REPEAT OFFENDERS")
        cols = [("Name", 55), ("FIRs", 18), ("Crime Types", 70), ("Districts", 47)]
        pdf.table_header(cols)
        for i, r in enumerate(repeat[:15]):
            pdf.table_row([r["name"], r["fir_count"], r.get("crime_types",""), r.get("districts","")], cols, i % 2 == 0)
        pdf.ln(3)

    # Hotspots
    if hotspots:
        pdf.section_title("CRIME HOTSPOTS")
        cols = [("District", 45), ("Station", 55), ("FIRs", 18), ("Top Crimes", 72)]
        pdf.table_header(cols)
        for i, r in enumerate(hotspots[:15]):
            pdf.table_row([r["district"], r["station"], r["fir_count"], r.get("crime_types","")], cols, i % 2 == 0)
        pdf.ln(3)

    # Modus operandi
    if mo:
        pdf.section_title("TOP MODUS OPERANDI")
        cols = [("Modus Operandi", 120), ("Count", 20), ("Crime Types", 50)]
        pdf.table_header(cols)
        for i, r in enumerate(mo[:10]):
            pdf.table_row([r["modus_operandi"], r["count"], r.get("crime_types","")], cols, i % 2 == 0)

    return bytes(pdf.output())

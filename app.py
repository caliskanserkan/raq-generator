import streamlit as st
import datetime, io, os, json, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils import load_db, update_airport
from czib_check import check_czib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

st.set_page_config(
    page_title="Flight Briefing and Awareness Tool",
    page_icon="✈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
#MainMenu { visibility: hidden; }
input[type="text"], textarea { text-transform: uppercase !important; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="manage-app-button"] { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
.viewerBadge_container__1QSob { display: none; }
.stDeployButton { display: none !important; }
.stAppDeployButton { display: none !important; }
.info-card { background-color:#1A3A5C; padding:12px 16px; border-radius:8px; margin:8px 0; }
.info-card h3 { color:white; margin:0 0 4px 0; font-size:14px; }
.info-card p  { color:#AED6F1; margin:0; font-size:12px; }
.risk-box-high { background-color:#FADBD8; border:2px solid #C0392B; border-radius:6px; padding:8px 12px; margin:4px 0; }
.risk-box-high p { color:#C0392B; font-weight:bold; margin:0; font-size:12px; }
.risk-box-med  { background-color:#FEF9E7; border:2px solid #D4AC0D; border-radius:6px; padding:8px 12px; margin:4px 0; }
.risk-box-med  p { color:#9A7D0A; font-weight:bold; margin:0; font-size:12px; }
.risk-box-low  { background-color:#EAFAF1; border:2px solid #1E8449; border-radius:6px; padding:8px 12px; margin:4px 0; }
.risk-box-low  p { color:#1E8449; font-weight:bold; margin:0; font-size:12px; }
.airport-label { background-color:#1A3A5C; color:white; padding:6px 12px; border-radius:6px;
                 font-size:13px; font-weight:bold; margin-bottom:4px; display:inline-block; }
.ra-block { background:#F8F9FA; border-left:4px solid #1A3A5C; padding:12px 16px; border-radius:0 6px 6px 0; margin:12px 0; }
.ra-block h4 { color:#1A3A5C; margin:0 0 10px 0; font-size:14px; }
@media (max-width: 768px) {
    .stTextInput input { font-size:16px !important; }
    .stButton button { height:52px !important; font-size:15px !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Font registration ──────────────────────────────────────────────────────────
def _find_font(fname):
    for p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), fname),
              os.path.join(os.getcwd(), fname), fname]:
        if os.path.exists(p):
            return p
    return None

_reg = pdfmetrics.getRegisteredFontNames()
for _fn, _ff in [("RAQN","DejaVuSans.ttf"),("RAQB","DejaVuSans-Bold.ttf"),("RAQI","DejaVuSans-Oblique.ttf")]:
    if _fn not in _reg:
        _fp = _find_font(_ff)
        if _fp:
            pdfmetrics.registerFont(TTFont(_fn, _fp))

_dv = "RAQN" in pdfmetrics.getRegisteredFontNames()
FN = "RAQN" if _dv else "Helvetica"
FB = "RAQB" if _dv else "Helvetica-Bold"
FI = "RAQI" if _dv else "Helvetica-Oblique"


# ── Pilot Management ───────────────────────────────────────────────────────────
def load_pilots():
    try:
        data = st.secrets.get("pilots", {}).get("data", [])
        return [{"name": p["name"], "surname": p["surname"], "email": p["email"]} for p in data]
    except Exception:
        return []

def save_pilots(pilots):
    return True

def get_pilot_names(pilots):
    return [f"{p['name']} {p['surname']}" for p in pilots]

def find_pilot(pilots, full_name):
    for p in pilots:
        if f"{p['name']} {p['surname']}".upper() == full_name.upper():
            return p
    return None


# ── Email Sender ───────────────────────────────────────────────────────────────
def send_email(to_email, pilot_name, airports_list, flight_date, ac_type):
    try:
        gmail_cfg = st.secrets.get("gmail", {})
        sender    = gmail_cfg.get("sender", "")
        password  = gmail_cfg.get("password", "")
        if not sender or not password:
            return False, "Gmail secrets eksik."

        airport_lines = "\n".join([f"  • {lbl}: {icao}" for lbl, icao in airports_list])
        airport_html  = "<br>".join([f"<b>{lbl}</b>: {icao}" for lbl, icao in airports_list])

        from email.header import Header
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(f"Flight Briefing - {flight_date}", "utf-8")
        msg["From"]    = sender
        msg["To"]      = to_email

        text = f"""Sayın {pilot_name},

Adınıza aşağıdaki uçuş için Flight Briefing formu oluşturulmuştur:

Tarih    : {flight_date}
A/C Type : {ac_type}
Meydanlar:
{airport_lines}

Oluşturulma: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} UTC
Bu mail otomatik olarak gönderilmiştir.
REC HAVACILIK – Flight Briefing and Awareness Tool
"""
        html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;font-size:14px;">
<div style="background:#1A3A5C;padding:16px 24px;border-radius:8px;margin-bottom:16px">
  <h2 style="color:white;margin:0;font-size:18px">✈ REC HAVACILIK – Flight Briefing Oluşturuldu</h2>
</div>
<p>Sayın <strong>{pilot_name}</strong>,</p>
<p>Adınıza aşağıdaki uçuş için Flight Briefing formu oluşturulmuştur:</p>
<table style="border-collapse:collapse;width:100%;max-width:480px">
  <tr><td style="padding:6px 12px;background:#f4f4f4;font-weight:bold;border:1px solid #ddd">Tarih</td>
      <td style="padding:6px 12px;border:1px solid #ddd">{flight_date}</td></tr>
  <tr><td style="padding:6px 12px;background:#f4f4f4;font-weight:bold;border:1px solid #ddd">A/C Type</td>
      <td style="padding:6px 12px;border:1px solid #ddd">{ac_type}</td></tr>
  <tr><td style="padding:6px 12px;background:#f4f4f4;font-weight:bold;border:1px solid #ddd;vertical-align:top">Meydanlar</td>
      <td style="padding:6px 12px;border:1px solid #ddd">{airport_html}</td></tr>
</table>
<p style="color:#888;font-size:12px;margin-top:24px">
  Oluşturulma: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} UTC<br>
  Bu mail otomatik olarak gönderilmiştir.
</p>
</body></html>
"""
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# RISK ASSESSMENT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def calc_risk(s):
    score = 0
    override_high = False
    override_medium = False
    override_reasons = []
    drivers = []
    actions = []

    def add(pts, d=None, a=None):
        nonlocal score
        score += pts
        if d: drivers.append(d)
        if a: actions.append(a)

    # — Overrides —
    if s.get('cat') == 'C':
        override_high = True
        override_reasons.append('CAT C aerodrome (auto override)')
    if s.get('pol_risk') == 'high':
        override_high = True
        override_reasons.append('High security / political threat (auto override)')
    if not s.get('prec') and s.get('angle') == 'steep' and s.get('oei_sid'):
        override_high = True
        override_reasons.append('Combination override: no precision + steep approach + special OEI SID')
    if s.get('sp_approval'):
        override_medium = True
        override_reasons.append('Special operator approval required')
    if s.get('lvp') == 'frequent' and s.get('alt') == 'no':
        override_medium = True
        override_reasons.append('Frequent LVP conditions + no adequate alternate within range')

    # Block 1 — Classification
    if s.get('sp_desig'):    add(2, 'Special aerodrome designation applies', 'Verify operator-specific procedures for this designation')
    if s.get('sp_crew'):     add(2, 'Special crew qualification required', 'Verify crew holds required qualification and recency')
    if s.get('sp_approval'): add(2, 'Special operator approval required', 'Obtain and file approval documentation prior to flight')

    # Block 2 — Approach
    if not s.get('prec'):            add(2, 'No precision approach available', 'Confirm crew currency on non-precision approach; review technique and minima')
    if s.get('angle') == 'moderate': add(2, 'Elevated approach angle (3.9°–4.49°)')
    if s.get('angle') == 'steep':    add(3, 'Steep approach angle (≥ 4.5°)', 'Brief steep approach technique; verify aircraft certification and performance compliance')
    if s.get('high_da'):             add(1, 'Terrain-limited precision minima — DA/DH ≥ 400 ft')
    # GNSS uyarısı — yaklaşma tipiyle etkileşim
    gnss = s.get('gnss_risk', 'no')
    rwy_data_g = s.get('rwy_data', [])
    gnss_approaches = [r for r in rwy_data_g if r[1] in ('GNSS', 'RNP AR', 'RNP')]
    if gnss == 'active':
        if gnss_approaches:
            rwys = ", ".join(r[0] for r in gnss_approaches)
            add(4, f"ACTIVE GNSS JAMMING/SPOOFING — RWY {rwys} approaches may be UNRELIABLE",
                'Do NOT rely on GNSS; revert to raw data (VOR/DME/ILS)')
        else:
            add(4, 'Active GNSS jamming / spoofing reported in area',
                'Do NOT rely on GNSS; revert to conventional raw data')
    elif gnss == 'notam':
        if gnss_approaches:
            rwys = ", ".join(r[0] for r in gnss_approaches)
            add(2, f"GNSS reliability concern (NOTAM) — RWY {rwys} approach affected",
                'Cross-check raw data; GNSS degradation possible')
        else:
            add(2, 'GNSS / GPS reliability concern — NOTAM active or interference reported',
                'Cross-check raw data (VOR/DME/ILS)')

    if s.get('offset'):              add(1, 'Offset localizer / offset approach procedure in use')
    if s.get('madem'):               add(2, 'Demanding missed approach / climb gradient above standard', 'Brief missed approach in detail; review OEI missed approach procedure')
    if s.get('oei_ma_brief'):        add(2, 'Engine-out go-around requires dedicated crew briefing')

    # Block 3 — Runway
    if s.get('rwy_w') == 'narrow':   add(3, 'Narrow runway (< 30 m width)', 'Confirm crosswind and ground handling limits for narrow strip')
    elif s.get('rwy_w') == 'medium': add(1, 'Reduced runway width (30–44 m)')
    if s.get('rwy_marg'):  add(2, 'Marginal runway length for planned operation', 'Compute T/O and landing performance with actual conditions; confirm stop margins')
    if s.get('phys_comp'): add(2, 'Physical runway complexity (slope / displaced threshold / offset LOC)')

    # Block 4 — OEI
    if s.get('oei_sid'):   add(3, 'Special engine-out SID required', 'Complete OEI SID analysis; brief engine failure procedure specific to this departure')
    if s.get('oei_grad'):  add(2, 'Demanding OEI climb gradient — obstacle clearance critical', 'Review obstacle clearance margins with expected TOW and actual conditions')
    if s.get('perf_lim'):  add(1, 'Performance-limited departure likely', 'Review WAT/CLG limits; consider derate or weight restriction')

    # Block 5 — Weather
    if s.get('lvp') == 'sometimes': add(1, 'Occasional LVP / low ceiling conditions')
    if s.get('lvp') == 'frequent':  add(2, 'Frequent LVP / fog / low visibility at this aerodrome', 'Monitor aerodrome forecast closely; verify LVP procedures and published minima')
    if s.get('xw_risk'):  add(2, 'Crosswind / windshear / contamination exposure', 'Review crosswind component limits; brief windshear escape if applicable')
    # MSA terrain scoring
    msa = int(s.get('msa_ft') or 0)
    msa_sector = s.get('msa_sector', 'All sectors')
    if msa >= 12000:
        add(3, f'High terrain environment — MSA {msa:,} ft ({msa_sector})',
            'Review terrain escape options and sector MSA; enhanced GPWS/TAWS awareness required',
            'High terrain environment within TMA / route area')
    elif msa >= 8000:
        add(2, f'Elevated terrain environment — MSA {msa:,} ft ({msa_sector})',
            'Verify terrain awareness and sector MSA; confirm missed approach terrain clearance')
    elif msa >= 5000:
        add(1, f'Moderate terrain environment — MSA {msa:,} ft ({msa_sector})')
    # MSA interaction multipliers
    if msa >= 8000 and not s.get('prec'):
        add(1, 'High MSA combined with non-precision approach — increased terrain risk',
            'Increase terrain-focused briefing depth; review raw data approach technique')
    if msa >= 8000 and s.get('angle') in ('moderate', 'steep'):
        add(1, 'High MSA combined with elevated/steep approach geometry',
            'Review terrain, vertical path and go-around strategy carefully')

    if s.get('terr_hh'):  add(2, 'Significant terrain / mountain wave / hot-high environment', 'Review terrain awareness procedures; compute performance for hot/high conditions')

    # Block 6 — ATC
    if s.get('atc') == 'moderate':   add(1, 'Moderate ATC / taxi routing complexity')
    if s.get('atc') == 'significant': add(2, 'Significant ATC / slot / sequencing complexity', 'Allow extra time margins for clearances; pre-brief complex taxi routing')
    if s.get('mil_traff'): add(2, 'Military / mixed traffic or unusual ATC phraseology', 'Review local ATC procedures and non-standard phraseology before flight')

    # Block 6b — GNSS / GPS reliability
    if s.get('gnss_risk') == 'notam':
        add(2, 'GNSS / GPS reliability concern — NOTAM active or interference reported',
            'Cross-check raw data (VOR/DME/ILS); GNSS approaches require crew awareness of potential degradation')
    elif s.get('gnss_risk') == 'active':
        add(4, 'Active GNSS jamming / spoofing reported in area',
            'Do NOT rely on GNSS for navigation or approach; revert to conventional raw data; verify FMS position continuously',
            'GNSS jamming or spoofing active — RNP / GNSS approaches may be unreliable or unusable')

    # Block 7 — Security / Oversight (weighted 3–4 pts)
    if s.get('pol_risk') == 'caution':     add(3, 'Political / security caution advisories in effect', 'Obtain current security briefing; review crew emergency protocols for this region')
    if s.get('arpt_sec') == 'uncertain':   add(3, 'Airport security / handling standards uncertain', 'Coordinate with local handler for enhanced security measures')
    if s.get('arpt_sec') == 'poor':        add(4, 'Poor airport security / handling standards', 'Consult security team; consider enhanced ground security measures')
    if s.get('st_oversight') == 'partial': add(2, 'Partial state safety oversight / ICAO compliance concerns')
    if s.get('st_oversight') == 'no':      add(4, 'Inadequate or unrecognised state safety oversight', 'Verify company OM requirements; obtain all available safety bulletins')

    # Block 8 — Alternate / Operational
    if s.get('alt') == 'limited': add(2, 'Limited alternate options within fuel planning range', 'Identify extended-range alternates; plan additional contingency fuel')
    if s.get('alt') == 'no':      add(3, 'No adequate alternate within fuel planning range', 'Reassess dispatch planning; carry contingency fuel per OM; notify OCC')
    if s.get('fuel') == 'uncertain': add(1, 'Fuel / ground handling reliability uncertain', 'Confirm fuel uplift availability minimum 48 h before departure')
    if s.get('fuel') == 'poor':      add(2, 'Poor fuel or ground handling standards', 'Arrange fuel from alternative source; coordinate closely with handler')
    if not s.get('crew_rec'):        add(1, 'No recent crew experience at this aerodrome (< 12 months)', 'Brief aerodrome-specific material; consider simulator or CBT refresher')

    # Final determination
    unique_drivers = list(dict.fromkeys(filter(None, drivers)))
    unique_actions = list(dict.fromkeys(filter(None, actions)))

    if override_high:
        risk = 'HIGH'
        basis = override_reasons
    elif score >= 10:
        risk = 'HIGH'
        basis = [f'Weighted risk score: {score} (threshold ≥ 10)'] + override_reasons
    elif override_medium or score >= 5:
        risk = 'MEDIUM'
        if override_medium:
            basis = override_reasons + ([f'Score: {score}'] if score else [])
        else:
            basis = [f'Weighted risk score: {score} (threshold ≥ 5)']
    else:
        risk = 'LOW'
        basis = [f'Weighted risk score: {score} (threshold < 5)']

    return {'risk': risk, 'score': score, 'basis': basis,
            'drivers': unique_drivers, 'actions': unique_actions}


def gen_summary_items(s):
    items = []
    if s.get('cat'):              items.append(f"CAT {s['cat']} aerodrome")
    if s.get('sp_desig'):         items.append("Special aerodrome designation — operator procedures apply")
    if s.get('sp_crew'):          items.append("Special crew qualification required")
    if s.get('sp_approval'):      items.append("Special operator approval required for this destination")
    # ── Pist bazlı yaklaşma özeti ──────────────────────────────────────────
    rwy_data_g = s.get('rwy_data', [])
    best_rwy   = s.get('best_rwy')

    PRECISION    = {"CAT III", "CAT II", "ILS"}
    PERFORMANCE  = {"RNP AR", "RNP", "GNSS"}
    VISUAL       = {"Non-Precision", "Circling"}
    APPR_RANK    = {"CAT III":7,"CAT II":6,"ILS":5,"RNP AR":4,"GNSS":3,"RNP":2,"Non-Precision":1,"Circling":0,"—":0}

    if rwy_data_g:
        # En iyi yaklaşma
        if best_rwy and best_rwy[1] not in ("—",):
            items.append(f"{best_rwy[1]} available — RWY {best_rwy[0]}")

        # Diğer precision pistler (best hariç, aynı tip olanları grupla)
        from collections import defaultdict
        type_to_rwys = defaultdict(list)
        for rwy, apt in rwy_data_g:
            if not rwy or apt == "—":
                continue
            if best_rwy and rwy == best_rwy[0] and apt == best_rwy[1]:
                continue  # zaten yazdık
            type_to_rwys[apt].append(rwy)

        for apt_type in ["CAT III","CAT II","ILS"]:
            if type_to_rwys[apt_type]:
                rwys_str = ", ".join(type_to_rwys[apt_type])
                items.append(f"{apt_type} available — RWY {rwys_str}")

        # Performance-based (GNSS/RNP) — precision değil, ayrıca belirt
        for apt_type in ["RNP AR","RNP","GNSS"]:
            if type_to_rwys[apt_type]:
                rwys_str = ", ".join(type_to_rwys[apt_type])
                items.append(f"{apt_type} approach (performance-based, not precision ILS) — RWY {rwys_str}")

        # Non-Precision ve Circling — spesifik pist ile
        for apt_type in ["Non-Precision","Circling"]:
            if type_to_rwys[apt_type]:
                rwys_str = ", ".join(type_to_rwys[apt_type])
                items.append(f"⚠ {apt_type} approach only — RWY {rwys_str}")
    else:
        # Pist girilmemişse genel yaklaşma bilgisi
        if not s.get('prec'):
            items.append("No precision approach available — non-precision only")
        else:
            items.append("Precision approach available")

    if s.get('angle') == 'steep':    items.append("Steep approach required — angle ≥ 4.5°")
    elif s.get('angle') == 'moderate': items.append("Elevated approach angle — 3.9° to 4.49°")
    if s.get('high_da'):          items.append("Terrain-limited approach minima — DA/DH ≥ 400 ft")

    # GNSS güvenilirlik uyarısı
    gnss = s.get('gnss_risk', 'no')
    gnss_rwys = [r for r in rwy_data_g if r[1] in ('GNSS', 'RNP AR', 'RNP')]
    if gnss == 'active':
        if gnss_rwys:
            rstr = ", ".join(r[0] for r in gnss_rwys)
            items.append(f"⚠ ACTIVE GNSS JAMMING/SPOOFING — RWY {rstr} approaches may be UNRELIABLE — revert to raw data")
        else:
            items.append("⚠ ACTIVE GNSS JAMMING/SPOOFING reported — do NOT rely on GNSS; use raw data (VOR/DME/ILS)")
    elif gnss == 'notam':
        if gnss_rwys:
            rstr = ", ".join(r[0] for r in gnss_rwys)
            items.append(f"GNSS reliability concern (NOTAM) — RWY {rstr} — cross-check raw data; degradation possible")
        else:
            items.append("GNSS / GPS reliability concern (NOTAM) — cross-check raw data")

    if s.get('offset'):           items.append("Offset localizer / offset approach procedure in use")
    if s.get('madem'):            items.append("Demanding missed approach gradient — special briefing required")
    if s.get('oei_ma_brief'):     items.append("Engine-out go-around procedure requires dedicated pre-flight briefing")
    if s.get('rwy_w') == 'narrow':   items.append("Narrow runway — width less than 30 m")
    elif s.get('rwy_w') == 'medium': items.append("Reduced runway width — 30 to 44 m")
    if s.get('rwy_marg'):         items.append("Marginal runway length — performance check mandatory")
    if s.get('phys_comp'):        items.append("Physical runway complexity — slope / displaced threshold / offset LOC")
    if s.get('oei_sid'):          items.append("Special engine-out SID / OEI analysis required for departure")
    if s.get('oei_grad'):         items.append("Demanding OEI climb gradient — obstacle clearance critical")
    if s.get('perf_lim'):         items.append("Performance-limited departure likely")
    if s.get('lvp') == 'frequent':   items.append("Frequent LVP / fog / low visibility — monitor forecast carefully")
    elif s.get('lvp') == 'sometimes': items.append("Occasional LVP or low ceiling conditions possible")
    if s.get('xw_risk'):          items.append("Crosswind / windshear / contamination risk — monitor conditions")
    # MSA terrain briefing
    msa = int(s.get('msa_ft') or 0)
    msa_sector = s.get('msa_sector', 'All sectors')
    if msa >= 12000:
        items.append(f"High terrain — MSA {msa:,} ft ({msa_sector}): enhanced TAWS/GPWS awareness; terrain escape plan required")
    elif msa >= 8000:
        items.append(f"Elevated terrain — MSA {msa:,} ft ({msa_sector}): verify missed approach terrain clearance")
    elif msa >= 5000:
        items.append(f"Moderate terrain — MSA {msa:,} ft ({msa_sector})")

    if s.get('terr_hh'):          items.append("Significant terrain / mountain wave / hot-high environment")
    if s.get('atc') == 'significant': items.append("Significant ATC / sequencing complexity — extra time margins required")
    elif s.get('atc') == 'moderate': items.append("Moderate ATC / taxi routing complexity")
    if s.get('mil_traff'):        items.append("Military / mixed traffic or non-standard ATC phraseology in use")
    if s.get('pol_risk') == 'high':    items.append("HIGH political / security risk — enhanced crew protocols mandatory")
    elif s.get('pol_risk') == 'caution': items.append("Political / security caution advisories in effect")
    if s.get('arpt_sec') == 'poor':    items.append("Poor airport security / handling — enhanced coordination required")
    elif s.get('arpt_sec') == 'uncertain': items.append("Airport security / handling standards uncertain")
    if s.get('st_oversight') == 'no':  items.append("Inadequate state safety oversight — OM compliance check required")
    elif s.get('st_oversight') == 'partial': items.append("Partial state safety oversight — awareness required")
    if s.get('alt') == 'no':      items.append("No adequate alternate within fuel range — contingency planning required")
    elif s.get('alt') == 'limited': items.append("Limited alternate options — extended alternate identification required")
    if s.get('fuel') == 'poor':   items.append("Poor fuel / ground handling — alternative sourcing recommended")
    elif s.get('fuel') == 'uncertain': items.append("Fuel availability uncertain — confirm 48 h before departure")
    if not s.get('crew_rec'):      items.append("No recent crew experience — enhanced pre-flight briefing required")
    return items


# ── Single Page PDF Generator ──────────────────────────────────────────────────
def generate_pdf_page(cv, frm, airport, risk, fi, page_label=""):
    czib_text = fi.get("czib", "")
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    RED   = colors.HexColor("#C0392B"); DARK  = colors.HexColor("#111111")
    MID   = colors.HexColor("#1A3A5C"); STEEL = colors.HexColor("#2E5F8A")
    LIGHT = colors.white;               BORD  = colors.HexColor("#888888")
    W_    = colors.white

    # Risk colour
    ra_risk = airport.get('ra_risk_level', '')
    if ra_risk == 'HIGH' or (risk and risk.get('risk_level') == 'HIGH'):
        RISKBG = colors.HexColor("#FADBD8"); RISKBORDER = colors.HexColor("#C0392B")
    elif ra_risk == 'MEDIUM' or (risk and risk.get('risk_level') == 'MEDIUM'):
        RISKBG = colors.HexColor("#FEF9E7"); RISKBORDER = colors.HexColor("#D4AC0D")
    else:
        RISKBG = colors.HexColor("#EAFAF1"); RISKBORDER = colors.HexColor("#1E8449")

    PW, PH = A4; ML = 15 * mm; W = PW - 2 * ML
    y = PH - 12 * mm

    def bx(x, yt, w2, h, fill=LIGHT, stroke=BORD, sw=0.5):
        cv.setLineWidth(sw); cv.setFillColor(fill); cv.setStrokeColor(stroke)
        cv.rect(x, yt - h, w2, h, fill=1, stroke=1)

    def tx(text, x, yt, font=FN, size=9, color=DARK, align="left", width=0):
        cv.setFillColor(color); cv.setFont(font, size)
        if align == "center" and width: cv.drawCentredString(x + width / 2, yt, str(text))
        elif align == "right" and width: cv.drawRightString(x + width, yt, str(text))
        else: cv.drawString(x, yt, str(text))

    def wl(text, font, size, max_w):
        cv.setFont(font, size); words = text.split(); lines = []; line = ""
        for w2 in words:
            test = (line + " " + w2).strip()
            if cv.stringWidth(test, font, size) <= max_w: line = test
            else:
                if line: lines.append(line)
                line = w2
        if line: lines.append(line)
        return lines

    def shdr(yt, lbl, h=14):
        bx(ML, yt, W, h, fill=MID, stroke=MID, sw=0.8)
        tx(lbl, ML + 6, yt - h + 4, FB, 8.5, W_); return yt - h

    def sbhdr(yt, lbl, h=12):
        bx(ML, yt, W, h, fill=STEEL, stroke=STEEL, sw=0.8)
        tx(lbl, ML + 4, yt - h + 3, FB, 8, W_); return yt - h

    def tblk(yt, text, bg=LIGHT, pad=6, border_color=BORD, border_sw=0.5):
        lines = text.split("\n") if text else ["N/A"]
        lh = 11; h = max(len(lines) * lh + pad * 2, 20)
        bx(ML, yt, W, h, fill=bg, stroke=border_color, sw=border_sw)
        ty2 = yt - pad - 8
        for ln in lines:
            sub = wl(ln, FN, 8, W - pad * 2)
            for s in sub: tx(s, ML + pad, ty2, FN, 8); ty2 -= lh
        return yt - h

    def cbrow(yt, name, label, bg=LIGHT, h=16, sz=10):
        bx(ML, yt, W, h, fill=bg, stroke=BORD); cby = yt - h + (h - sz) / 2
        frm.checkbox(name=name, tooltip=label, x=ML + 6, y=cby, size=sz,
                     checked=False, buttonStyle="check", borderColor=DARK,
                     fillColor=W_, textColor=RED, forceBorder=True)
        tx(label, ML + 6 + sz + 6, yt - h / 2 - 3.5, FN, 9, DARK); return yt - h

    def chdrs(yt, cols, h=15):
        x = ML
        for lbl, w2 in cols:
            bx(x, yt, w2, h, fill=STEEL, stroke=BORD)
            tx(lbl, x, yt - h + 4, FB, 8.5, W_, "center", w2); x += w2
        return yt - h

    def cdata(yt, cols, h=21):
        x = ML
        for text, w2, font, size, color, align in cols:
            bx(x, yt, w2, h, fill=LIGHT, stroke=BORD)
            tx(text, x, yt - h + 5, font, size, color, align, w2); x += w2
        return yt - h

    # Header
    hh = 26
    rev_date = datetime.date.today().strftime("%Y-%m-%d")
    bx(ML, y, W * .72, hh, fill=MID, stroke=MID, sw=1)
    bx(ML + W * .72, y, W * .28, hh, fill=MID, stroke=MID, sw=1)
    tx("REC HAVACILIK  ✈  YOL VE MEYDAN YETERLİLİK EĞİTİM FORMU", ML + 8, y - hh + 8, FB, 9.5, W_)
    tx("FOP-FRM02", ML + W * .72 + 4, y - 7, FB, 7, W_)
    tx(f"Rev: {rev_date}", ML + W * .72 + 4, y - hh + 6, FB, 8, RED)
    y -= hh
    bx(ML, y, W, 13, fill=LIGHT, stroke=BORD)
    tx("ROUTE AND AERODROME QUALIFICATION TRAINING FORM", ML, y - 10, FI, 8, STEEL, "center", W)
    y -= 16

    y = shdr(y, "FLIGHT DETAILS")
    cw = [W * .18, W * .15, W * .335, W * .335]
    y = chdrs(y, [("Date", cw[0]), ("A/C Type", cw[1]), ("PIC", cw[2]), ("SIC", cw[3])])
    y = cdata(y, [(fi.get("date",""), cw[0], FB, 9, DARK, "center"),
                  (fi.get("ac_type","").upper(), cw[1], FB, 9, DARK, "center"),
                  (fi.get("pic","").upper(), cw[2], FB, 9, DARK, "center"),
                  (fi.get("sic","").upper(), cw[3], FB, 9, DARK, "center")]); y -= 3

    y = shdr(y, "AERODROME")
    cw2 = [W * .50, W * .25, W * .25]
    y = chdrs(y, [("Airport Name", cw2[0]), ("ICAO", cw2[1]), ("Category", cw2[2])])
    ah = 22; x = ML
    for text, w2, font, size, color in [
        (airport.get("name","").upper(), cw2[0], FB, 9, DARK),
        (airport.get("icao","").upper(), cw2[1], FB, 9, DARK),
        (airport.get("category","").upper(), cw2[2], FB, 13, RED),
    ]:
        bx(x, y, w2, ah, fill=LIGHT, stroke=BORD)
        tx(text, x, y - ah + 5, font, size, color, "center", w2); x += w2
    y -= ah + 3

    y = shdr(y, "FAMILIARIZATION CONDUCTED BY")
    hw = W / 2; y = chdrs(y, [("Self Briefing", hw), ("Local Authority", hw)])
    fh = 20; bx(ML, y, hw, fh, fill=LIGHT, stroke=BORD); bx(ML + hw, y, hw, fh, fill=LIGHT, stroke=BORD)
    csz = 12; cby = y - fh + (fh - csz) / 2
    icao_key = airport.get("icao", "X")
    frm.checkbox(name=f"fam_self_{icao_key}", tooltip="Self Briefing",
                 x=ML + hw / 2 - csz / 2, y=cby, size=csz, checked=False,
                 buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
    frm.checkbox(name=f"fam_local_{icao_key}", tooltip="Local Authority",
                 x=ML + hw + hw / 2 - csz / 2, y=cby, size=csz, checked=False,
                 buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
    y -= fh + 3

    y = shdr(y, "FOLLOWING ITEMS WERE BRIEFED AND FAMILIARIZED FOR THE ROUTE FLOWN")
    for i, (nm, lbl) in enumerate([
        (f"cb_terrain_{icao_key}",    "Terrain and Safe Altitudes"),
        (f"cb_comms_{icao_key}",      "Communication and ATC Facilities"),
        (f"cb_sar_{icao_key}",        "Search & Rescue Procedures"),
        (f"cb_layout_{icao_key}",     "Airport Layout"),
        (f"cb_approach_{icao_key}",   "Approach Aids"),
        (f"cb_instrument_{icao_key}", "Instrument Approach and Hold Procedures"),
        (f"cb_minima_{icao_key}",     "Operating Minima"),
    ]):
        y = cbrow(y, nm, lbl, bg=LIGHT if i % 2 == 0 else colors.HexColor("#FAFAFA"))
    y -= 3

    y = shdr(y, "SPECIAL ITEMS BRIEFED DUE TO AERODROME CATEGORY")
    for i, (nm, lbl) in enumerate([
        (f"sp_1_{icao_key}", "(1) Non-standard approach aids or approach patterns"),
        (f"sp_2_{icao_key}", "(2) Unusual local weather conditions"),
        (f"sp_3_{icao_key}", "(3) Unusual characteristics or performance limitations"),
        (f"sp_4_{icao_key}", "(4) Other relevant considerations: obstructions, physical layout, lighting etc."),
        (f"sp_5_{icao_key}", "(5) Category C aerodromes: additional considerations for approach/landing/take-off."),
    ]):
        y = cbrow(y, nm, lbl, bg=LIGHT if i % 2 == 0 else colors.HexColor("#FAFAFA"))
    y -= 3

    # ── SUMMARY (single merged block) ─────────────────────────────────────────
    y = shdr(y, "SPECIAL REMARKS  –  AERODROME BRIEFING  (AUTO FROM DATABASE)")

    # Collect summary content: prefer new ra_briefing_items, fallback to section1/2/3
    ra_items = airport.get('ra_briefing_items', [])
    if ra_items:
        summary_text = "\n".join(f"• {item}" for item in ra_items)
    else:
        parts = []
        for key in ['section1', 'section2', 'section3']:
            val = (airport.get(key) or '').strip()
            if val and val.upper() != 'N/A':
                parts.append(val)
        summary_text = "\n".join(parts) if parts else "N/A"

    y = tblk(y, summary_text); y -= 3

    # ── AERODROME RISK ASSESSMENT (auto) ──────────────────────────────────────
    ra_risk_lvl = airport.get('ra_risk_level', '')
    ra_score    = airport.get('ra_risk_score', '')
    ra_date     = airport.get('ra_assessment_date', '')
    ra_due      = airport.get('ra_reassessment_due', '')
    ra_by       = airport.get('ra_assessed_by', '')
    ra_drivers  = airport.get('ra_key_drivers', [])
    ra_basis    = airport.get('ra_risk_basis', [])

    if ra_risk_lvl:
        y = shdr(y, "AERODROME RISK ASSESSMENT  (AUTO – DATABASE)")
        lines = [f"RISK LEVEL: {ra_risk_lvl}   |   CAT: {airport.get('category','')}   |   Score: {ra_score}"]
        if ra_date:
            lines.append(f"Assessment: {ra_date}   |   Reassessment due: {ra_due}   |   By: {ra_by}")
        for b in ra_basis:
            lines.append(f"  {b}")

        y = tblk(y, "\n".join(lines), bg=RISKBG, border_color=RISKBORDER, border_sw=1.2, pad=8)
        y -= 3
    elif risk:
        y = shdr(y, "AERODROME RISK ASSESSMENT  (AUTO – DATABASE)")
        rt = (
            f"RISK LEVEL: {risk['risk_level']}   |   CAT: {airport.get('category','')}   |   {risk['ops_approval']}\n"
            f"MITIGATION: {risk['mitigation']}"
        )
        y = tblk(y, rt, bg=RISKBG, pad=8); y -= 3

    if czib_text:
        cz_h = 22
        bx(ML, y, W, cz_h, fill=colors.HexColor("#FADBD8"), stroke=colors.HexColor("#C0392B"), sw=1.5)
        tx(f"  ⚠  {czib_text}", ML + 6, y - cz_h + 6, FB, 9, colors.HexColor("#C0392B"))
        y -= cz_h + 3

    cert = "I hereby certify that route and aerodrome familiarization was completed for the flight in accordance with AMC1 ORO.FC.105 b(2);c and OM PART C."
    ch = 24; bx(ML, y, W, ch, fill=LIGHT, stroke=BORD)
    lns = wl(cert, FI, 8, W - 16); ty = y - 6
    for ln in lns: tx(ln, ML + 8, ty, FI, 8, STEEL); ty -= 10
    y -= ch
    today = datetime.date.today().strftime("%Y-%m-%d")
    cw3 = [W * .22, W * .55, W * .23]; x = ML
    for text, w2, font, size, color, align in [
        ("Completed by:", cw3[0], FB, 9, DARK, "center"),
        (fi.get("pic","").upper(), cw3[1], FB, 9, DARK, "center"),
        (today, cw3[2], FN, 8, STEEL, "right"),
    ]:
        bx(x, y, w2, 20, fill=LIGHT, stroke=BORD)
        tx(text, x, y - 15, font, size, color, align, w2); x += w2


# ── Booklet PDF Generator ──────────────────────────────────────────────────────
def generate_booklet_pdf(airport_list, airports_db, risks_db, fi):
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    cv = C.Canvas(buf, pagesize=A4)
    cv.setTitle(f"FBAT-BOOKLET-{fi.get('date','')}")
    frm = cv.acroForm
    for label, icao in airport_list:
        airport = airports_db[icao]; risk = risks_db.get(icao)
        try: czib_hit, czib_text = check_czib(icao)
        except Exception: czib_text = ""
        generate_pdf_page(cv, frm, airport, risk, {**fi, "czib": czib_text}, page_label=label)
        cv.showPage()
    cv.save(); buf.seek(0)
    return buf.getvalue()


# ── Load DB ────────────────────────────────────────────────────────────────────
airports, risks = load_db()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:#1A3A5C;padding:18px 24px;border-radius:8px;margin-bottom:24px">
<h1 style="color:white;margin:0;font-size:22px;letter-spacing:0.3px">✈ Flight Briefing and Awareness Tool</h1>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AIRPORT INPUTS
# ══════════════════════════════════════════════════════════════════════════════
airport_fields = [
    ("DEPT",     "Kalkış Meydanı",    "LTBA"),
    ("DEPT ALT", "Kalkış Alternatif", "LTFM"),
    ("DEST",     "Varış Meydanı",     "EHAM"),
    ("DEST ALT", "Varış Alternatif",  "EGLL"),
]

icao_inputs = {}
col_left, col_right = st.columns(2)

for i, (label, desc, placeholder) in enumerate(airport_fields):
    col = col_left if i % 2 == 0 else col_right
    with col:
        st.markdown(f'<span class="airport-label">✈ {label}</span>', unsafe_allow_html=True)
        icao_val = st.text_input(
            desc, max_chars=4, placeholder=placeholder,
            key=f"icao_{label}", label_visibility="collapsed",
        ).upper().strip()
        icao_inputs[label] = icao_val

        if icao_val:
            if icao_val in airports:
                ap = airports[icao_val]
                rk = ap.get('ra_risk_level') or (risks.get(icao_val, {}).get('risk_level') if risks.get(icao_val) else None)
                risk_html = ""
                if rk == 'HIGH':
                    risk_html = f'<div class="risk-box-high"><p>⚠ AERODROME RISK: HIGH</p></div>'
                elif rk == 'MEDIUM':
                    risk_html = f'<div class="risk-box-med"><p>⚡ AERODROME RISK: MEDIUM</p></div>'
                elif rk == 'LOW':
                    risk_html = f'<div class="risk-box-low"><p>✔ AERODROME RISK: LOW</p></div>'
                st.markdown(
                    f'<div class="info-card" style="padding:8px 14px;margin:4px 0">'
                    f'<h3 style="font-size:13px">✔ {ap["name"]}</h3>'
                    f'<p>Kategori: {ap["category"]}</p></div>'
                    f'{risk_html}',
                    unsafe_allow_html=True,
                )
            elif len(icao_val) == 4:
                st.error(f"❌ {icao_val} veritabanında bulunamadı.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# FLIGHT INFO
# ══════════════════════════════════════════════════════════════════════════════
pilots = load_pilots()
pilot_names = get_pilot_names(pilots)

col1, col2 = st.columns(2)
with col1:
    if pilot_names:
        pic_raw = st.selectbox("PIC", options=["—"] + pilot_names, key="pic_select")
        pic = "" if pic_raw == "—" else pic_raw
    else:
        st.warning("⚠ Admin panelde pilot tanımlanmamış.")
        pic = ""
    date = st.date_input("Uçuş Tarihi", value=datetime.date.today())
with col2:
    if pilot_names:
        sic_raw = st.selectbox("SIC", options=["—"] + pilot_names, key="sic_select")
        sic = "" if sic_raw == "—" else sic_raw
    else:
        sic = ""
    aircraft_list = st.secrets.get("aircraft", {}).get("list", [])
    if aircraft_list:
        ac_raw = st.selectbox("A/C Type", options=["—"] + aircraft_list, key="ac_select")
        ac = "" if ac_raw == "—" else ac_raw
    else:
        ac = st.text_input("A/C Type", value="", placeholder="TC-REC")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GENERATE
# ══════════════════════════════════════════════════════════════════════════════
valid_airports = [(lbl, icao) for lbl, icao in icao_inputs.items() if icao and icao in airports]

if valid_airports:
    st.info(f"📋 **{len(valid_airports)} meydan** için PDF oluşturulacak: " +
            " → ".join([f"**{lbl}** ({icao})" for lbl, icao in valid_airports]))
else:
    st.warning("En az bir geçerli meydan girin.")

if st.button("📄  RAQ BOOKLET PDF OLUŞTUR", use_container_width=True, type="primary"):
    if not valid_airports:
        st.error("En az bir geçerli ICAO kodu girin.")
    elif not pic:
        st.error("PIC seçiniz. Admin panelden önce pilot tanımlayın.")
    else:
        with st.spinner(f"⏳ {len(valid_airports)} sayfalık booklet oluşturuluyor..."):
            try:
                for lbl, icao_val in valid_airports:
                    czib_hit, czib_text = check_czib(icao_val)
                    if czib_hit:
                        st.warning(f"⚠ {lbl} ({icao_val}): {czib_text}")

                pdf = generate_booklet_pdf(
                    valid_airports, airports, risks,
                    {"date": date.strftime("%Y-%m-%d"), "ac_type": ac, "pic": pic, "sic": sic},
                )

                icao_str = "-".join([icao for _, icao in valid_airports])
                fname = f"FBAT_{icao_str}_{date.strftime('%Y-%m-%d')}.pdf"
                st.success(f"✔ {len(valid_airports)} sayfalık booklet hazır!")
                st.download_button(
                    f"⬇  PDF Booklet İndir ({len(valid_airports)} sayfa)",
                    pdf, fname, "application/pdf", use_container_width=True,
                )

                pilot_obj = find_pilot(pilots, pic)
                if pilot_obj:
                    ok, msg_result = send_email(pilot_obj["email"], pic, valid_airports, date.strftime("%Y-%m-%d"), ac)
                    if ok: st.success(f"📧 Mail gönderildi → {pilot_obj['email']}")
                    else:  st.warning(f"⚠ Mail gönderilemedi: {msg_result}")

                if sic:
                    sic_obj = find_pilot(pilots, sic)
                    if sic_obj:
                        ok, msg_result = send_email(sic_obj["email"], sic, valid_airports, date.strftime("%Y-%m-%d"), ac)
                        if ok: st.success(f"📧 Mail gönderildi → {sic_obj['email']}")
                        else:  st.warning(f"⚠ SIC maili gönderilemedi: {msg_result}")

            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© Flight Briefing and Awareness Tool  –  AMC1 ORO.FC.105 b(2);c")

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

with st.expander("⚙", expanded=False):
    if not st.session_state["admin_authenticated"]:
        pw = st.text_input("Şifre", type="password", key="admin_pw")
        if st.button("🔐 Giriş", use_container_width=True):
            if pw == st.secrets.get("admin", {}).get("password", "rec2024"):
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Hatalı şifre.")
    else:
        st.success("✔ Giriş başarılı")
        if st.button("🚪 Çıkış", use_container_width=True):
            st.session_state["admin_authenticated"] = False
            st.rerun()

        tab1, tab2 = st.tabs(["✈ Meydan", "👤 Pilotlar"])

        # ── DB DEBUG ─────────────────────────────────────────────────────────
        with st.expander("🔍 Veritabanı Durumu", expanded=True):
            airports_now, _ = load_db()
            if airports_now:
                st.success(f"✔ {len(airports_now)} meydan yüklendi: {', '.join(sorted(airports_now.keys()))}")
            else:
                st.error("❌ Veritabanından hiç meydan yüklenemedi. Google Sheets bağlantısı veya sekme adı (AIRPORT_DB) hatalı olabilir.")
            if st.button("🔄 Yenile", use_container_width=True):
                load_db.clear()
                st.rerun()

        # ── TAB 1: MEYDAN ──────────────────────────────────────────────────
        with tab1:
            # ── ICAO SELECTION ──
            col_icao, col_btn = st.columns([2, 1])
            with col_icao:
                icao_e = st.text_input("ICAO Kodu", max_chars=4, placeholder="LTFM", key="ei").upper().strip()
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                load_btn = st.button("📂 Yükle", use_container_width=True)

            # Kayıt başarı mesajı (rerun sonrası göster)
            if "save_ok_msg" in st.session_state:
                st.success(st.session_state.pop("save_ok_msg"))

            if load_btn and icao_e:
                ap_data = airports.get(icao_e, {})
                if ap_data.get('ra_briefing_items'):
                    loaded_summary = "\n".join(ap_data['ra_briefing_items'])
                else:
                    parts = [ap_data.get('section1',''), ap_data.get('section2',''), ap_data.get('section3','')]
                    loaded_summary = "\n".join(p for p in parts if p and p.upper() != 'N/A')
                st.session_state["edit_name"]    = ap_data.get("name", "")
                st.session_state["edit_cat"]     = ap_data.get("category", "A")
                st.session_state["edit_summary"] = loaded_summary
                # Risk form session state sıfırla — önceki girişler görünmesin
                for k in ['ra_result','ra_summary','ra_survey','ra_icao',
                          'rwy_sets','ra_cat','ra_angle','ra_prec','ra_hda',
                          'ra_off','ra_off_rwy','ra_mad','ra_oema','ra_rwyw',
                          'ra_rwym','ra_phc','ra_oisid','ra_oigrad','ra_plim',
                          'ra_lvp','ra_xw','ra_thh','ra_msa_ft','ra_msa_sector',
                          'ra_atc','ra_mil','ra_gnss','ra_pol','ra_sec',
                          'ra_usoap','ra_alt','ra_alt_lvp','ra_fuel','ra_crec',
                          'ra_spd','ra_spc','ra_spa','ra_by']:
                    if k in st.session_state:
                        del st.session_state[k]
                if ap_data: st.success(f"✔ {icao_e} yüklendi — {ap_data.get('name','')}")
                else:       st.info(f"ℹ {icao_e} yeni meydan.")

            name_e = st.text_input("Meydan Adı", key="edit_name")
            cat_e  = st.selectbox("Kategori", ["A","B","C"],
                                   index=["A","B","C"].index(st.session_state.get("edit_cat","A"))
                                   if st.session_state.get("edit_cat","A") in ["A","B","C"] else 0)

            st.divider()

            # ── MODE SELECTION ──────────────────────────────────────────────
            admin_mode = st.radio(
                "İşlem seçin:",
                ["📋  Summary Database Update", "🎯  Risk Assessment Tool"],
                horizontal=True, key="admin_mode"
            )

            # ══════════════════════════════════════════════════════════════
            # OPTION 1 — SUMMARY DATABASE UPDATE
            # ══════════════════════════════════════════════════════════════
            if "Summary" in admin_mode:
                st.markdown('<div class="ra-block"><h4>📋 Summary / Briefing Notları</h4></div>', unsafe_allow_html=True)
                summary_e = st.text_area(
                    "Özet (her satır ayrı madde olarak PDF'e işlenir)",
                    key="edit_summary", height=200,
                    placeholder="Non-precision approach only (RNAV/VOR)\nOEI SID gerekli – Departure Runway 09R\nPolitical caution advisory in effect..."
                )

                if st.button("💾 Kaydet", use_container_width=True, key="save_summary"):
                    if icao_e:
                        lines = [l.strip() for l in summary_e.split("\n") if l.strip()]
                        ok = update_airport(icao_e, {
                            "name":             name_e,
                            "category":         cat_e,
                            "section1":         summary_e,
                            "ra_briefing_items": lines,
                        })
                        if ok:
                            st.session_state["save_ok_msg"] = f"✔ {icao_e} kaydedildi!"
                            st.rerun()
                        else:
                            st.error("❌ Kayıt başarısız.")
                    else:
                        st.warning("ICAO girin.")
                # Kayıt başarı mesajını göster
                if "save_ok_msg" in st.session_state:
                    st.success(st.session_state.pop("save_ok_msg"))

            # ══════════════════════════════════════════════════════════════
            # OPTION 2 — RISK ASSESSMENT TOOL
            # ══════════════════════════════════════════════════════════════
            else:
                if not icao_e:
                    st.info("ℹ Yukarıdan ICAO kodunu girin ve Yükle'ye tıklayın.")
                else:
                    assessed_by = st.text_input("Değerlendiren (isim / callsign)", key="ra_by")

                    st.markdown("---")
                    st.markdown('<div class="ra-block"><h4>🏛 Block 1 — Aerodrome Classification</h4></div>', unsafe_allow_html=True)
                    ra_cat = st.selectbox("Aerodrome category?", ["A","B","C"], key="ra_cat",
                                          help="CAT C → otomatik HIGH override")
                    c1, c2 = st.columns(2)
                    ra_sp_desig    = c1.checkbox("Special aerodrome designation applies?", key="ra_spd")
                    ra_sp_crew     = c2.checkbox("Special crew qualification required?", key="ra_spc")
                    ra_sp_approval = st.checkbox("Special operator approval required for this destination?", key="ra_spa")

                    st.markdown('<div class="ra-block"><h4>📐 Block 2 — Runway & Approach</h4></div>', unsafe_allow_html=True)

                    # ── Pist girişi ──────────────────────────────────────
                    st.caption("Active runways and approach types / Aktif pistler ve yaklaşma tipleri")
                    APR_TYPES = ["—","CAT III","CAT II","ILS","GNSS","RNP AR","RNP","Non-Precision","Circling"]

                    if "rwy_sets" not in st.session_state:
                        st.session_state["rwy_sets"] = 1

                    rwy_data = []
                    for set_i in range(st.session_state["rwy_sets"]):
                        cols4 = st.columns(4)
                        for j in range(4):
                            slot = set_i * 4 + j
                            with cols4[j]:
                                des = st.text_input(f"RWY {slot+1}", max_chars=4,
                                                    key=f"rwy_des_{set_i}_{j}",
                                                    placeholder="09R").upper().strip()
                                apr = st.selectbox("Appr", APR_TYPES,
                                                   key=f"rwy_apr_{set_i}_{j}",
                                                   label_visibility="collapsed")
                                if des:
                                    rwy_data.append((des, apr))

                    col_add, _ = st.columns([1, 3])
                    with col_add:
                        if st.button("➕ 4 more runways", key="add_rwy_set"):
                            st.session_state["rwy_sets"] += 1
                            st.rerun()

                    # En iyi yaklaşma otomatik
                    APPR_RANK = {"CAT III":7,"CAT II":6,"ILS":5,"RNP AR":4,"GNSS":3,"RNP":2,"Non-Precision":1,"Circling":0,"—":0}
                    best_rwy = max(rwy_data, key=lambda r: APPR_RANK.get(r[1],0)) if rwy_data else None
                    ra_prec = "Yes" if best_rwy and APPR_RANK.get(best_rwy[1],0) >= 3 else "No"

                    # Offset hangi pist
                    rwy_names = [r[0] for r in rwy_data if r[0]]
                    ra_offset = st.checkbox("Offset localizer / offset approach in use?", key="ra_off")
                    ra_offset_rwy = []
                    if ra_offset and rwy_names:
                        ra_offset_rwy = st.multiselect("Offset approach — which runway(s)?", rwy_names, key="ra_off_rwy")

                    # Circling otomatik tespit
                    ra_circling = any(r[1] == "Circling" for r in rwy_data)
                    ra_circling_rwy = [r[0] for r in rwy_data if r[1] == "Circling"]

                    ra_angle = st.selectbox("Best available approach angle?",
                                            ["Normal (< 3.9°)","Elevated (3.9°–4.49°)","Steep (≥ 4.5°) — override risk"],
                                            key="ra_angle")
                    ra_high_da = st.checkbox("Precision DA/DH ≥ 400 ft due to terrain-limited minima?", key="ra_hda",
                                              disabled=(ra_prec == "No"))
                    c3, c4 = st.columns(2)
                    ra_madem  = c3.checkbox("Missed approach / climb gradient above standard?", key="ra_mad")
                    ra_oei_ma = c4.checkbox("Engine-out go-around requires dedicated crew briefing?", key="ra_oema")

                    st.markdown('<div class="ra-block"><h4>🛬 Block 3 — Runway & Physical</h4></div>', unsafe_allow_html=True)
                    ra_rwy_w = st.selectbox("Runway width?", ["≥ 45 m","30–44 m","< 30 m"], key="ra_rwyw")
                    c5, c6 = st.columns(2)
                    ra_rwy_marg  = c5.checkbox("Runway length marginal for planned operation?", key="ra_rwym")
                    ra_phys_comp = c6.checkbox("Physical complexity? (slope / displaced threshold / offset LOC)", key="ra_phc")

                    st.markdown('<div class="ra-block"><h4>⚡ Block 4 — Departure & OEI</h4></div>', unsafe_allow_html=True)
                    c7, c8, c9 = st.columns(3)
                    ra_oei_sid  = c7.checkbox("Special OEI SID required?", key="ra_oisid")
                    ra_oei_grad = c8.checkbox("OEI gradient demanding?", key="ra_oigrad")
                    ra_perf_lim = c9.checkbox("Performance-limited departure?", key="ra_plim")

                    st.markdown('<div class="ra-block"><h4>🌤 Block 5 — Weather & Environment</h4></div>', unsafe_allow_html=True)
                    ra_lvp = st.selectbox("Frequency of LVP / fog / low ceiling?",
                                          ["Rarely / not significant","Occasional","Frequent"],
                                          key="ra_lvp")
                    c10, c11 = st.columns(2)
                    ra_xw_risk = c10.checkbox("Crosswind / windshear / contamination risk significant?", key="ra_xw")
                    ra_terr_hh = c11.checkbox("Significant terrain / mountain wave / hot-high?", key="ra_thh")

                    c_msa1, c_msa2 = st.columns(2)
                    ra_msa_ft = c_msa1.number_input(
                        "Maximum Sector Altitude / MSA (ft)", min_value=0, max_value=25000,
                        value=0, step=100, key="ra_msa_ft",
                        help="Enter the highest MSA in the TMA/route area. 0 = not applicable."
                    )
                    ra_msa_sector = c_msa2.selectbox(
                        "MSA sector", ["All sectors", "Specific sector (worst case)", "Enroute MEA/MORA"],
                        key="ra_msa_sector"
                    )

                    st.markdown('<div class="ra-block"><h4>📡 Block 6 — ATC & Operational Complexity</h4></div>', unsafe_allow_html=True)
                    ra_atc = st.selectbox("ATC / slot / taxi complexity?",
                                          ["Low / normal","Moderate","Significant"], key="ra_atc")
                    ra_mil_traff = st.checkbox("Military / mixed traffic or unusual ATC phraseology?", key="ra_mil")

                    ra_gnss = st.selectbox(
                        "GNSS / GPS signal reliability?",
                        ["No known risk", "NOTAM'd / interference expected", "Active jamming / spoofing reported"],
                        key="ra_gnss",
                        help="If GNSS or RNP approach is selected and reliability is in question, a warning will be generated in the briefing summary."
                    )

                    st.markdown('<div class="ra-block"><h4>🔐 Block 7 — Security, State & Oversight</h4></div>', unsafe_allow_html=True)
                    ra_pol_risk = st.selectbox("Political / security risk?",
                                               ["No significant concern","Caution advisories in effect","High risk — AUTO OVERRIDE HIGH"],
                                               key="ra_pol")
                    ra_arpt_sec = st.selectbox("Airport security / handling standards?",
                                               ["Adequate / reliable","Uncertain / inconsistent","Poor / inadequate"],
                                               key="ra_sec")
                    ra_st_oversight = st.selectbox("State safety oversight / ICAO USOAP compliance?",
                                                    ["Acceptable (EASA or equivalent)","Partial — concerns noted","No / inadequate / unrecognised"],
                                                    key="ra_usoap")

                    st.markdown('<div class="ra-block"><h4>⛽ Block 8 — Alternate, Fuel & Crew</h4></div>', unsafe_allow_html=True)
                    ra_alt = st.selectbox("Adequate alternate within fuel planning range?",
                                          ["Yes — available and suitable","Limited options","No adequate alternate"],
                                          key="ra_alt")
                    ra_fuel = st.selectbox("Fuel quality and ground handling reliability?",
                                           ["Reliable and verified","Uncertain / variable","Poor / known concerns"],
                                           key="ra_fuel")
                    ra_crew_rec = st.radio("Crew has operated at this aerodrome within the last 12 months?",
                                           ["Yes","No"], horizontal=True, key="ra_crec")

                    st.markdown("---")

                    if st.button("🎯  Calculate Risk", use_container_width=True, type="primary", key="ra_calc"):
                        # Map UI values to engine keys
                        angle_map = {"Normal (< 3.9°)": "normal", "Elevated (3.9°–4.49°)": "moderate", "Steep (≥ 4.5°) — override risk": "steep"}
                        rwy_map   = {"≥ 45 m": "wide", "30–44 m": "medium", "< 30 m": "narrow"}
                        lvp_map   = {"Rarely / not significant": "no", "Occasional": "sometimes", "Frequent": "frequent"}
                        atc_map   = {"Low / normal": "no", "Moderate": "moderate", "Significant": "significant"}
                        pol_map   = {"No significant concern": "no", "Caution advisories in effect": "caution", "High risk — AUTO OVERRIDE HIGH": "high"}
                        sec_map   = {"Adequate / reliable": "good", "Uncertain / inconsistent": "uncertain", "Poor / inadequate": "poor"}
                        ov_map    = {"Acceptable (EASA or equivalent)": "yes", "Partial — concerns noted": "partial", "No / inadequate / unrecognised": "no"}
                        alt_map   = {"Yes — available and suitable": "yes", "Limited options": "limited", "No adequate alternate": "no"}
                        fuel_map  = {"Reliable and verified": "reliable", "Uncertain / variable": "uncertain", "Poor / known concerns": "poor"}

                        survey = {
                            'cat':         ra_cat,
                            'sp_desig':    ra_sp_desig,
                            'sp_crew':     ra_sp_crew,
                            'sp_approval': ra_sp_approval,
                            'prec':        ra_prec == "Yes",
                            'rwy_data':    rwy_data,
                            'best_rwy':    best_rwy,
                            'offset_rwys': ra_offset_rwy,
                            'circling':    ra_circling,
                            'circling_rwys': ra_circling_rwy,
                            'angle':       angle_map[ra_angle],
                            'high_da':     ra_high_da if ra_prec == "Yes" else False,
                            'offset':      ra_offset,
                            'madem':       ra_madem,
                            'oei_ma_brief':ra_oei_ma,
                            'rwy_w':       rwy_map[ra_rwy_w],
                            'rwy_marg':    ra_rwy_marg,
                            'phys_comp':   ra_phys_comp,
                            'oei_sid':     ra_oei_sid,
                            'oei_grad':    ra_oei_grad,
                            'perf_lim':    ra_perf_lim,
                            'lvp':         lvp_map[ra_lvp],
                            'xw_risk':     ra_xw_risk,
                            'terr_hh':     ra_terr_hh,
                            'msa_ft':      ra_msa_ft,
                            'msa_sector':  ra_msa_sector,
                            'atc':         atc_map[ra_atc],
                            'mil_traff':   ra_mil_traff,
                            'gnss_risk':   {"No known risk": "no", "NOTAM'd / interference expected": "notam", "Active jamming / spoofing reported": "active"}[ra_gnss],
                            'pol_risk':    pol_map[ra_pol_risk],
                            'arpt_sec':    sec_map[ra_arpt_sec],
                            'st_oversight':ov_map[ra_st_oversight],
                            'alt':         alt_map[ra_alt],
                            'fuel':        fuel_map[ra_fuel],
                            'crew_rec':    ra_crew_rec == "Yes",
                        }

                        result  = calc_risk(survey)
                        summary = gen_summary_items(survey)
                        st.session_state['ra_result']  = result
                        st.session_state['ra_summary'] = summary
                        st.session_state['ra_survey']  = survey
                        st.session_state['ra_icao']    = icao_e

                    # ── RESULT DISPLAY ──────────────────────────────────
                    if st.session_state.get('ra_result') and st.session_state.get('ra_icao') == icao_e:
                        result  = st.session_state['ra_result']
                        summary = st.session_state['ra_summary']

                        risk_colors = {'HIGH': '#FADBD8', 'MEDIUM': '#FEF9E7', 'LOW': '#EAFAF1'}
                        risk_text_c = {'HIGH': '#C0392B', 'MEDIUM': '#9A7D0A', 'LOW': '#1E8449'}
                        rl = result['risk']
                        bg = risk_colors.get(rl, '#F8F9FA')
                        tc = risk_text_c.get(rl, '#111')

                        st.markdown(f"""
<div style="background:{bg};border:2px solid {tc};border-radius:8px;padding:14px 18px;margin:12px 0">
<div style="font-size:11px;font-weight:700;color:{tc};letter-spacing:1px;margin-bottom:8px">AERODROME RISK LEVEL</div>
<div style="font-size:28px;font-weight:900;color:{tc};font-family:Arial,sans-serif;letter-spacing:2px">{rl}</div>
<div style="font-size:12px;color:{tc};margin-top:4px">Score: {result['score']}</div>
</div>""", unsafe_allow_html=True)

                        for b in result['basis']:
                            st.caption(f"• {b}")

                        if result['actions']:
                            with st.expander("✅ Recommended Actions", expanded=True):
                                for i, a in enumerate(result['actions'], 1):
                                    st.markdown(f"**{i}.** {a}")

                        if summary:
                            with st.expander("📄 Briefing Summary (PDF'e işlenecek)", expanded=True):
                                seen = set()
                                for item in summary:
                                    key = item.strip().lower()
                                    if key not in seen:
                                        seen.add(key)
                                        st.markdown(f"• {item}")

                        st.markdown("---")
                        if st.button("💾 Sonuçları Veritabanına Kaydet", use_container_width=True, type="primary", key="ra_save"):
                            today_str = datetime.date.today().strftime("%Y-%m-%d")
                            due_str   = (datetime.date.today().replace(year=datetime.date.today().year + 1)).strftime("%Y-%m-%d")
                            ok = update_airport(icao_e, {
                                "name":               name_e,
                                "category":           ra_cat,
                                "ra_risk_level":      result['risk'],
                                "ra_risk_score":      result['score'],
                                "ra_risk_basis":      result['basis'],
                                "ra_key_drivers":     result['drivers'],
                                "ra_actions":         result['actions'],
                                "ra_briefing_items":  summary,
                                "ra_assessment_date": today_str,
                                "ra_reassessment_due":due_str,
                                "ra_assessed_by":     assessed_by or "Admin",
                            })
                            if ok:
                                st.session_state["save_ok_msg"] = f"✔ {icao_e} risk değerlendirmesi kaydedildi! Yeniden değerlendirme: {due_str}"
                                for k in ['ra_result','ra_summary','ra_survey','ra_icao']:
                                    if k in st.session_state: del st.session_state[k]
                                st.rerun()
                            else:
                                st.error("Kayıt başarısız.")

            st.divider()
            if st.button("🔄 Veritabanını Yenile", use_container_width=True):
                st.rerun()

        # ── TAB 2: PILOTLAR ────────────────────────────────────────────────
        with tab2:
            st.markdown("**Kayıtlı Pilotlar**")
            pilots_list = load_pilots()
            if pilots_list:
                for p in pilots_list:
                    st.markdown(
                        f'<div class="info-card" style="padding:8px 14px;margin:4px 0">'
                        f'<h3 style="font-size:13px">👤 {p["name"]} {p["surname"]}</h3>'
                        f'<p>📧 {p["email"]}</p></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Pilot bulunamadı.")
            st.info("ℹ Pilot eklemek/silmek için Streamlit → Settings → Secrets bölümünü güncelleyin.")

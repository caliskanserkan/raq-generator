import streamlit as st
import datetime, io, os, smtplib, json, re
from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

from utils import load_db, update_airport
from czib_check import check_czib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# =============================================================================
# PAGE CONFIG / STYLE
# =============================================================================
st.set_page_config(
    page_title="Flight Briefing and Awareness Tool",
    page_icon="✈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
#MainMenu { visibility: hidden; }
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
.survey-current { background:#EAFAF1; border:1px solid #1E8449; color:#1E8449; border-radius:6px; padding:8px 12px; margin:6px 0; font-size:12px; }
.survey-due { background:#FEF9E7; border:1px solid #D4AC0D; color:#9A7D0A; border-radius:6px; padding:8px 12px; margin:6px 0; font-size:12px; }
.survey-expired { background:#FADBD8; border:1px solid #C0392B; color:#C0392B; border-radius:6px; padding:8px 12px; margin:6px 0; font-size:12px; }
.localops-box { background:#F7F9FB; border:1px solid #D6E2EE; border-radius:6px; padding:10px 12px; margin:6px 0; }
@media (max-width: 768px) {
    .stTextInput input { font-size:16px !important; }
    .stButton button { height:52px !important; font-size:15px !important; }
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# FONT REGISTRATION
# =============================================================================
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

# =============================================================================
# HELPERS
# =============================================================================
def load_pilots():
    try:
        data = st.secrets.get("pilots", {}).get("data", [])
        return [{"name": p["name"], "surname": p["surname"], "email": p["email"]} for p in data]
    except Exception:
        return []

def get_pilot_names(pilots):
    return [f"{p['name']} {p['surname']}" for p in pilots]

def find_pilot(pilots, full_name):
    for p in pilots:
        if f"{p['name']} {p['surname']}".upper() == full_name.upper():
            return p
    return None

def send_email(to_email, pilot_name, airports_list, flight_date, ac_type):
    try:
        gmail_cfg = st.secrets.get("gmail", {})
        sender    = gmail_cfg.get("sender", "")
        password  = gmail_cfg.get("password", "")
        if not sender or not password:
            return False, "Gmail secrets eksik."

        airport_lines = "\n".join([f"  • {lbl}: {icao}" for lbl, icao in airports_list])
        airport_html  = "<br>".join([f"<b>{lbl}</b>: {icao}" for lbl, icao in airports_list])

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Flight Briefing - {flight_date}"
        msg["From"]    = sender
        msg["To"]      = to_email

        text = f"""Sayın {pilot_name},

Adınıza aşağıdaki uçuş için Flight Briefing formu oluşturulmuştur:

Tarih    : {flight_date}
A/C Type : {ac_type}
Meydanlar:
{airport_lines}

Oluşturulma: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
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
  Oluşturulma: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC<br>
  Bu mail otomatik olarak gönderilmiştir.
</p>
</body></html>
"""
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)

# =============================================================================
# SURVEY AGE / AIRAC
# =============================================================================
def parse_date_safe(value):
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(str(value), fmt).date()
        except Exception:
            pass
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except Exception:
        return None

def get_survey_age_status(airport: dict):
    today = datetime.date.today()
    last = parse_date_safe(airport.get("survey_last_updated") or airport.get("ra_assessment_date"))
    if not last:
        return {
            "status": "NO SURVEY",
            "days_old": None,
            "last": None,
            "message": "No aerodrome risk survey date found in database."
        }
    days_old = (today - last).days
    if days_old >= 56:
        return {
            "status": "EXPIRED",
            "days_old": days_old,
            "last": last,
            "message": f"Aerodrome survey is {days_old} days old. Two or more AIRAC cycles may have passed. Review/update required."
        }
    if days_old >= 28:
        return {
            "status": "REVIEW DUE",
            "days_old": days_old,
            "last": last,
            "message": f"Aerodrome survey is {days_old} days old. One or more AIRAC cycles may have passed. Review recommended."
        }
    return {
        "status": "CURRENT",
        "days_old": days_old,
        "last": last,
        "message": f"Aerodrome survey is current ({days_old} days old)."
    }

# =============================================================================
# LIVE AIP / AOI LOCAL OPS CHECK
# =============================================================================
def _strip_text(html: str) -> str:
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        return re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _extract_candidate_sentences(text: str):
    text = text.replace("•", ". ").replace(";", ". ")
    chunks = re.split(r"(?<=[\.!?])\s+", text)
    keywords = [
        "curfew", "noise", "abatement", "slot", "startup", "start-up", "taxi", "hot spot", "hotspot",
        "preferential", "runway", "crossing", "initial contact", "phraseology", "contact", "clearance",
        "restriction", "restriction", "operating hour", "operation hour", "hours", "ppr", "permission",
        "coordination", "apron", "follow-me", "follow me", "pushback", "arrival", "departure", "night",
        "local procedure", "flight procedure"
    ]
    hits = []
    seen = set()
    for ch in chunks:
        c = re.sub(r"\s+", " ", ch).strip(" -\n\r\t")
        low = c.lower()
        if len(c) < 12:
            continue
        if any(k in low for k in keywords):
            c = c[:220].rstrip()
            if c not in seen:
                hits.append(c)
                seen.add(c)
        if len(hits) >= 8:
            break
    return hits


def fetch_local_ops_snapshot(airport: dict):
    """Published data only. No interpretation beyond summarizing official text snippets."""
    source_name = airport.get("aip_source_name") or airport.get("official_source_label") or "Official AIP / AOI"
    source_url = airport.get("aip_source_url") or airport.get("official_source_url")
    reference = airport.get("aip_reference") or airport.get("official_source_reference") or ""
    checked_on = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    result = {
        "source_name": source_name,
        "source_url": source_url or "",
        "reference": reference,
        "checked_on": checked_on,
        "items": [],
        "status": "NOT CONFIGURED",
        "note": "",
    }

    if not source_url:
        result["note"] = "No official AIP/AOI source URL configured in the database."
        return result
    if requests is None:
        result["status"] = "ERROR"
        result["note"] = "Python requests library is not available in this environment."
        return result

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FBAT/1.0; +official-use)",
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(source_url, timeout=20, headers=headers)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()

        raw_text = ""
        if "html" in ctype or "xml" in ctype or source_url.lower().endswith((".html", ".htm", "/")):
            raw_text = _strip_text(resp.text)
        elif "pdf" in ctype or source_url.lower().endswith(".pdf"):
            result["status"] = "SOURCE FOUND"
            result["note"] = "Official PDF source available. Direct PDF text extraction is not enabled in this app version; review source manually if needed."
            return result
        else:
            raw_text = _strip_text(resp.text)

        items = _extract_candidate_sentences(raw_text)
        result["items"] = [f"Published: {x}" for x in items[:6]]
        result["status"] = "OK"
        if not result["items"]:
            result["note"] = "No explicit local operational procedures found in the published source text."
        return result
    except Exception as e:
        result["status"] = "ERROR"
        result["note"] = f"Official source could not be read: {e}"
        return result

# =============================================================================
# RISK ENGINE
# =============================================================================
def calc_risk(s):
    score = 0
    override_high = False
    override_medium = False
    override_reasons = []
    drivers = []
    actions = []
    considerations = []

    def add(pts, d=None, a=None, c=None):
        nonlocal score
        score += pts
        if d: drivers.append(d)
        if a: actions.append(a)
        if c: considerations.append(c)

    # Hard / soft overrides
    if s.get('cat') == 'C':
        override_high = True
        override_reasons.append('CAT C aerodrome (automatic HIGH override)')
    if s.get('pol_risk') == 'high':
        override_high = True
        override_reasons.append('High political / security risk (automatic HIGH override)')
    if (not s.get('prec')) and s.get('angle') == 'steep' and s.get('oei_sid'):
        override_high = True
        override_reasons.append('No precision approach + steep approach + special OEI SID (combination override)')
    if s.get('sp_approval'):
        override_medium = True
        override_reasons.append('Special operator approval required')
    if s.get('lvp') == 'frequent' and s.get('alt') == 'no':
        override_medium = True
        override_reasons.append('Frequent LVP conditions with no adequate alternate')

    # Block 1 – classification / approval
    if s.get('sp_desig'):    add(2, 'Special aerodrome designation applies', 'Verify company procedures applicable to this designation')
    if s.get('sp_crew'):     add(2, 'Special crew qualification required', 'Verify crew qualification and recency before dispatch')
    if s.get('sp_approval'): add(2, 'Special operator approval required', 'Obtain and file approval before operation')

    # Block 2 – approach / nav
    if not s.get('prec'):
        add(2, 'No precision approach available', 'Review non-precision approach technique and minima', 'Non-precision environment – increased workload expected')
    if s.get('angle') == 'moderate':
        add(1, 'Elevated approach angle (3.9°–4.49°)', c='Elevated approach geometry published')
    if s.get('angle') == 'steep':
        add(3, 'Steep approach (≥ 4.5°)', 'Brief steep approach technique and performance implications', 'Steep approach published – enhanced stabilized approach discipline required')

    msa = s.get('msa_ft', 0) or 0
    msa_sector = s.get('msa_sector', 'All sectors')
    if msa >= 12000:
        add(3, f'High terrain environment – MSA {msa:,} ft ({msa_sector})', 'Review terrain escape options and sector minima', 'High terrain environment published within TMA')
    elif msa >= 8000:
        add(2, f'Elevated terrain environment – MSA {msa:,} ft ({msa_sector})', 'Verify terrain awareness and sector minima', 'Elevated terrain environment published within TMA')
    elif msa >= 5000:
        add(1, f'Moderate terrain environment – MSA {msa:,} ft ({msa_sector})')

    # MSA interaction logic (situational awareness multiplier)
    if msa >= 8000 and not s.get('prec'):
        add(1, 'High MSA combined with non-precision approach', 'Increase terrain-focused briefing depth')
    if msa >= 8000 and s.get('angle') in ('moderate', 'steep'):
        add(1, 'High MSA combined with elevated/steep approach geometry', 'Review terrain, vertical path and go-around strategy')
    if msa >= 8000 and s.get('alt') in ('limited', 'no'):
        add(1, 'High terrain environment with limited alternate flexibility', 'Confirm alternate strategy and fuel plan')

    if s.get('high_da'):
        add(1, 'Terrain-limited DA/DH ≥ 400 ft', c='Higher-than-normal precision minima published')
    if s.get('offset') == 'offset_non_precision':
        add(1, 'Offset non-precision approach published', 'Brief visual segment and lateral geometry carefully')
    if s.get('offset') == 'offset_precision':
        add(1, 'Offset precision approach published', 'Brief offset localizer/vertical path characteristics')
    if s.get('madem') == 'above_standard':
        add(1, 'Missed approach climb gradient above standard', 'Review missed approach procedure in detail')
    if s.get('madem') == 'special':
        add(2, 'Special missed approach procedure required', 'Conduct detailed missed approach briefing and terrain review')
    if s.get('oei_ma_brief'):
        add(2, 'Engine-out go-around requires dedicated briefing', 'Conduct dedicated OEI go-around crew briefing')

    gnss = s.get('gnss_risk', 'no')
    if gnss == 'notam':
        add(2, 'GNSS advisories / degradation risk in region', 'Cross-check navigation with conventional aids')
    elif gnss == 'active':
        add(4, 'Active GNSS jamming/spoofing risk reported', 'Treat GNSS as unreliable and prefer conventional aids where available')
    if s.get('gnss_outage'):
        add(2, 'GNSS outage / GPS NOTAM expected', 'Confirm non-GNSS backup approach options and nav cross-check strategy')

    # Block 3 – runway & ground
    if s.get('rwy_w') == 'narrow':
        add(3, 'Narrow runway (< 30 m)', 'Confirm narrow-runway limitations and crosswind exposure')
    elif s.get('rwy_w') == 'medium':
        add(1, 'Reduced runway width (30–44 m)')
    if s.get('rwy_marg') == 'marginal':
        add(2, 'Runway length margin is marginal', 'Recheck take-off/landing performance with actual conditions')
    elif s.get('rwy_marg') == 'critical':
        add(3, 'Runway length margin is critical', 'Confirm dispatch/performance acceptability before operation')
    if s.get('phys_comp') == 'slope':
        add(1, 'Runway slope characteristic present')
    elif s.get('phys_comp') == 'displaced_threshold':
        add(1, 'Displaced threshold affects runway geometry')
    elif s.get('phys_comp') == 'complex_combination':
        add(2, 'Complex physical runway characteristics', 'Review runway layout and operational implications')
    if s.get('taxi_complex'):
        add(2, 'Complex taxi routing / hot spots identified', 'Brief taxi route and hot spots prior to operation')
    if s.get('rwy_crossing') in ('arrival', 'departure'):
        add(1, 'Runway crossing required', 'Brief crossing points and clearance discipline')
    elif s.get('rwy_crossing') == 'both':
        add(2, 'Runway crossing required for both arrival and departure', 'Review all runway crossing procedures in advance')

    # Block 4 – departure & OEI
    if s.get('oei_sid'):
        add(3, 'Special OEI SID required', 'Review OEI SID and obstacle clearance margins')
    if s.get('oei_grad') == 'demanding':
        add(2, 'Demanding OEI climb gradient', 'Validate climb gradient at expected weight and conditions')
    elif s.get('oei_grad') == 'critical':
        add(3, 'Critical OEI climb gradient', 'Dispatch only after detailed OEI and weight review')
    if s.get('perf_lim'):
        add(1, 'Performance-limited departure likely', 'Review performance-limited departure implications')

    # Block 5 – weather / atc
    if s.get('lvp') == 'sometimes':
        add(1, 'Occasional LVP / low visibility exposure')
    if s.get('lvp') == 'frequent':
        add(2, 'Frequent LVP / fog / low ceiling exposure', 'Monitor forecast closely and verify minima strategy')
    if s.get('xw_risk'):
        add(2, 'Crosswind / windshear / contamination exposure', 'Review wind limitations and windshear actions')
    if s.get('terr_hh'):
        add(2, 'Mountain / terrain / hot-high environmental effects', 'Review terrain, temperature and performance impact')
    if s.get('atc') == 'moderate':
        add(1, 'Moderate ATC / sequencing / taxi complexity')
    elif s.get('atc') == 'significant':
        add(2, 'Significant ATC / slot / sequencing complexity', 'Allow extra time and brief communication workload')
    if s.get('mil_traff'):
        add(2, 'Military / mixed traffic or non-standard local phraseology', 'Review local ATC environment before operation')

    # Block 6 – security / alternate / ops resilience
    if s.get('pol_risk') == 'caution':
        add(3, 'Political / security caution advisories in effect', 'Obtain current security briefing prior to flight')
    if s.get('arpt_sec') == 'uncertain':
        add(2, 'Airport security / handling standards uncertain', 'Confirm local security arrangements with handler')
    elif s.get('arpt_sec') == 'poor':
        add(4, 'Poor airport security / handling standards', 'Consult security and operations before dispatch')
    if s.get('st_oversight') == 'partial':
        add(2, 'Partial state safety oversight concerns identified')
    elif s.get('st_oversight') == 'no':
        add(4, 'Inadequate or unrecognised state safety oversight', 'Review company requirements and safety advisories')
    if s.get('alt') == 'limited':
        add(2, 'Limited alternate options within planning range', 'Identify robust alternates and consider extra fuel')
    elif s.get('alt') == 'no':
        add(3, 'No adequate alternate within planning range', 'Reassess dispatch planning and contingency fuel policy')
    if not s.get('alt_lvp') and s.get('lvp') == 'frequent' and s.get('alt') != 'no':
        add(2, 'Destination has frequent LVP but alternate LVP capability is not confirmed', 'Consider CAT-capable alternate')
    if s.get('fuel') == 'uncertain':
        add(1, 'Fuel / ground handling reliability uncertain', 'Confirm fuel uplift arrangements in advance')
    elif s.get('fuel') == 'poor':
        add(2, 'Poor fuel / ground handling reliability', 'Coordinate alternate fueling / handling plan')
    if not s.get('crew_rec'):
        add(1, 'No recent crew experience at this aerodrome', 'Conduct enhanced aerodrome-specific briefing')

    # Runway approach-derived considerations
    rwy_approaches = s.get('rwy_approaches', {}) or {}
    if rwy_approaches:
        has_cat3 = any('Precision CAT III' in vals for vals in rwy_approaches.values())
        has_cat2 = any('Precision CAT II' in vals for vals in rwy_approaches.values())
        has_rnp_ar = any('RNP AR' in vals for vals in rwy_approaches.values())
        has_offset_prec = any('Offset Precision' in vals for vals in rwy_approaches.values())
        has_offset_npa = any('Offset Non-Precision' in vals for vals in rwy_approaches.values())
        if has_rnp_ar:
            add(1, 'RNP AR procedure published on one or more runways', 'Verify RNP AR crew/aircraft authorization if intended')
        if has_offset_prec:
            add(1, 'Offset precision approach published on one or more runways')
        if has_offset_npa:
            add(1, 'Offset non-precision approach published on one or more runways')
        if s.get('lvp') == 'frequent' and not has_cat2 and not has_cat3:
            add(2, 'Frequent LVP exposure with no CAT II/III runway capability identified', 'Confirm alternate strategy and minima planning')
        elif s.get('lvp') == 'frequent' and has_cat2 and not has_cat3:
            add(1, 'CAT II available but no CAT III capability with frequent LVP exposure')

    # Final classification
    def dedupe(items):
        out = []
        seen = set()
        for x in items:
            if x and x not in seen:
                out.append(x)
                seen.add(x)
        return out

    drivers = dedupe(drivers)[:5]
    actions = dedupe(actions)[:5]
    considerations = dedupe(considerations)[:7]

    if override_high:
        risk = 'HIGH'
        basis = override_reasons
    elif score >= 10:
        risk = 'HIGH'
        basis = [f'Weighted risk score: {score} (threshold ≥ 10)'] + override_reasons
    elif override_medium or score >= 5:
        risk = 'MEDIUM'
        basis = override_reasons + ([f'Score: {score}'] if override_medium else [f'Weighted risk score: {score} (threshold ≥ 5)'])
    else:
        risk = 'LOW'
        basis = [f'Weighted risk score: {score} (threshold < 5)']

    return {
        'risk': risk,
        'score': score,
        'basis': basis,
        'drivers': drivers,
        'actions': actions,
        'considerations': considerations,
    }


def gen_summary_items(s, result=None):
    items = []
    if s.get('cat'):
        items.append(f"CAT {s['cat']} aerodrome")
    if not s.get('prec'):
        items.append("No precision approach available")
    if s.get('angle') == 'steep':
        items.append("Steep approach published")
    elif s.get('angle') == 'moderate':
        items.append("Elevated approach angle published")
    if s.get('msa_ft', 0):
        items.append(f"Max MSA within TMA: {s['msa_ft']:,} ft ({s.get('msa_sector', 'All sectors')})")
    if s.get('offset') == 'offset_non_precision':
        items.append("Offset non-precision approach published")
    elif s.get('offset') == 'offset_precision':
        items.append("Offset precision approach published")
    if s.get('oei_sid'):
        items.append("Special OEI SID required")
    if s.get('oei_grad') in ('demanding', 'critical'):
        items.append("Demanding OEI climb gradient")
    if s.get('lvp') == 'frequent':
        items.append("Frequent LVP / fog / low visibility exposure")
    elif s.get('lvp') == 'sometimes':
        items.append("Occasional LVP / low visibility exposure")
    if s.get('xw_risk'):
        items.append("Crosswind / windshear / contamination exposure")
    if s.get('taxi_complex'):
        items.append("Complex taxi routing / hot spots identified")
    if s.get('pol_risk') == 'caution':
        items.append("Political / security caution advisories in effect")
    elif s.get('pol_risk') == 'high':
        items.append("High political / security risk")
    if s.get('alt') == 'limited':
        items.append("Limited alternate options")
    elif s.get('alt') == 'no':
        items.append("No adequate alternate within planning range")
    if not s.get('crew_rec'):
        items.append("No recent crew experience at this aerodrome")
    if result:
        items.extend(result.get('considerations', [])[:4])
    # de-dupe
    out = []
    seen = set()
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out[:10]

# =============================================================================
# PDF GENERATOR
# =============================================================================
def generate_pdf_page(cv, frm, airport, risk, fi, page_label=""):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    import datetime

    # ── COLOURS ──────────────────────────────────────────────────────────────
    DARK  = colors.HexColor("#1A3A5C")   # header bg
    MGRAY = colors.HexColor("#888888")
    LGRAY = colors.HexColor("#DDDDDD")
    BLACK = colors.HexColor("#111111")
    WHITE = colors.white
    RED   = colors.HexColor("#C0392B")
    GREEN = colors.HexColor("#1E8449")
    RISKBG_LOW  = colors.HexColor("#EAFAF1")
    RISKBG_MED  = colors.HexColor("#FEF9E7")
    RISKBG_HIGH = colors.HexColor("#FADBD8")

    PW, PH = A4
    ML = 15 * mm
    MR = 15 * mm
    W  = PW - ML - MR
    # Türkçe destekli fontlar — global FN/FB/FI (DejaVuSans) kullanılır
    _FN = FN  # global'den gelir (DejaVuSans veya Helvetica fallback)
    _FB = FB
    _FI = FI if "FI" in dir() else FN if "FI" in dir() else FN

    rev_date = datetime.date.today().strftime("%Y-%m-%d")
    y = PH - 10 * mm

    # ── helpers ──────────────────────────────────────────────────────────────
    def bx(x, yt, w2, h, fill=WHITE, stroke=MGRAY, sw=0.5):
        cv.setLineWidth(sw)
        cv.setFillColor(fill)
        cv.setStrokeColor(stroke)
        cv.rect(x, yt - h, w2, h, fill=1, stroke=1)

    def tx(text, x, yt, font=FN, size=8, color=BLACK, align="left", width=0):
        cv.setFillColor(color)
        cv.setFont(font, size)
        if align == "center" and width:
            cv.drawCentredString(x + width / 2, yt, str(text))
        elif align == "right" and width:
            cv.drawRightString(x + width, yt, str(text))
        else:
            cv.drawString(x, yt, str(text))

    def wraplines(text, font, size, max_w):
        cv.setFont(font, size)
        words = str(text).split()
        lines2 = []
        line = ""
        for wd in words:
            test = (line + " " + wd).strip()
            if cv.stringWidth(test, font, size) <= max_w:
                line = test
            else:
                if line:
                    lines2.append(line)
                line = wd
        if line:
            lines2.append(line)
        return lines2

    def section_hdr(yt, label, h=13):
        bx(ML, yt, W, h, fill=DARK, stroke=DARK, sw=0.8)
        tx(label, ML + 5, yt - h + 4, _FB, 8, WHITE)
        return yt - h

    def text_block(yt, text, bg=WHITE, pad=5, border=MGRAY, bsw=0.5, lh=10, fsize=8):
        raw_lines = (text or "N/A").split("\n")
        wrapped = []
        for ln in raw_lines:
            wrapped.extend(wraplines(ln, _FN, fsize, W - pad * 2))
        h = max(len(wrapped) * lh + pad * 2, 16)
        bx(ML, yt, W, h, fill=bg, stroke=border, sw=bsw)
        ty2 = yt - pad - (lh * 0.7)
        for s in wrapped:
            tx(s, ML + pad, ty2, _FN, fsize)
            ty2 -= lh
        return yt - h

    def checkbox_row(yt, label, h=14, checked=False):
        bx(ML, yt, W, h, fill=WHITE, stroke=LGRAY, sw=0.4)
        # draw checkbox square
        cb_size = 7
        cb_x = ML + 4
        cb_y = yt - h / 2 - cb_size / 2
        cv.setLineWidth(0.6)
        cv.setStrokeColor(MGRAY)
        cv.setFillColor(WHITE)
        cv.rect(cb_x, cb_y, cb_size, cb_size, fill=1, stroke=1)
        if checked:
            cv.setStrokeColor(BLACK)
            cv.setLineWidth(1)
            cv.line(cb_x + 1, cb_y + cb_size / 2, cb_x + cb_size / 2 - 1, cb_y + 1)
            cv.line(cb_x + cb_size / 2 - 1, cb_y + 1, cb_x + cb_size + 1, cb_y + cb_size + 2)
        tx(label, ML + 15, yt - h + 4, _FN, 8)
        return yt - h

    # ═══════════════════════════════════════════════════════════════════════
    # 1. MAIN HEADER
    # ═══════════════════════════════════════════════════════════════════════
    hh = 22
    bx(ML, y, W * 0.72, hh, fill=DARK, stroke=DARK, sw=1)
    bx(ML + W * 0.72, y, W * 0.28, hh, fill=DARK, stroke=DARK, sw=1)
    tx("REC HAVACILIK  \u2192  YOL VE MEYDAN YETERLİLİK EĞİTİM FORMU",
       ML + 6, y - hh + 7, _FB, 9, WHITE)
    tx("FOP-FRM02", ML + W * 0.72 + 4, y - 7, _FB, 7, WHITE)
    tx(f"Rev: {rev_date}", ML + W * 0.72 + 4, y - hh + 5, _FB, 8, RED)
    y -= hh

    # subtitle
    bx(ML, y, W, 12, fill=colors.HexColor("#EAF0F6"), stroke=LGRAY, sw=0.4)
    tx("ROUTE AND AERODROME QUALIFICATION TRAINING FORM",
       ML, y - 12 + 3, _FN, 7.5, DARK, align="center", width=W)
    y -= 12

    # ═══════════════════════════════════════════════════════════════════════
    # 2. FLIGHT DETAILS TABLE
    # ═══════════════════════════════════════════════════════════════════════
    y = section_hdr(y, "FLIGHT DETAILS")
    row_h = 14
    cols = [W * 0.18, W * 0.18, W * 0.32, W * 0.32]
    headers = ["Date", "A/C Type", "PIC", "SIC"]
    values  = [
        fi.get("date", ""),
        fi.get("ac_type", ""),
        fi.get("pic", "").upper(),
        fi.get("sic", "").upper(),
    ]
    cx = ML
    for i, (hd, col_w) in enumerate(zip(headers, cols)):
        bx(cx, y, col_w, row_h, fill=colors.HexColor("#D6E4F0"), stroke=LGRAY, sw=0.5)
        tx(hd, cx, y - row_h + 4, _FB, 8, DARK, align="center", width=col_w)
        cx += col_w
    y -= row_h
    cx = ML
    for i, (val, col_w) in enumerate(zip(values, cols)):
        bx(cx, y, col_w, row_h, fill=WHITE, stroke=LGRAY, sw=0.5)
        tx(val, cx, y - row_h + 4, _FB, 8.5, BLACK, align="center", width=col_w)
        cx += col_w
    y -= row_h
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 3. AERODROME TABLE
    # ═══════════════════════════════════════════════════════════════════════
    y = section_hdr(y, "AERODROME")
    cat = (airport.get("category") or "B").strip().upper()
    # header row
    col_w2 = [W * 0.50, W * 0.25, W * 0.25]
    hdrs2  = ["Airport Name", "ICAO", "Category"]
    cx = ML
    for hd, cw in zip(hdrs2, col_w2):
        bx(cx, y, cw, row_h, fill=colors.HexColor("#D6E4F0"), stroke=LGRAY, sw=0.5)
        tx(hd, cx, y - row_h + 4, _FB, 8, DARK, align="center", width=cw)
        cx += cw
    y -= row_h
    # data row
    aname = (airport.get("name") or airport.get("airport_name") or "").upper()
    icao  = (airport.get("icao") or "").upper()
    cx = ML
    vals2 = [aname, icao, cat]
    for vi, (val, cw) in enumerate(zip(vals2, col_w2)):
        bx(cx, y, cw, row_h + 2, fill=WHITE, stroke=LGRAY, sw=0.5)
        color = RED if vi == 2 else BLACK
        tx(val, cx, y - row_h + 2, _FB, 9 if vi == 2 else 8.5, color, align="center", width=cw)
        cx += cw
    y -= (row_h + 2)
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 4. FAMILIARIZATION CONDUCTED BY
    # ═══════════════════════════════════════════════════════════════════════
    y = section_hdr(y, "FAMILIARIZATION CONDUCTED BY")
    half = W / 2
    fam_h = 18
    bx(ML,        y, half, fam_h, fill=colors.HexColor("#D6E4F0"), stroke=LGRAY, sw=0.5)
    bx(ML + half, y, half, fam_h, fill=colors.HexColor("#D6E4F0"), stroke=LGRAY, sw=0.5)
    tx("Self Briefing",   ML,        y - fam_h + 6, _FB, 8, DARK, align="center", width=half)
    tx("Local Authority", ML + half, y - fam_h + 6, _FB, 8, DARK, align="center", width=half)
    y -= fam_h
    bx(ML,        y, half, fam_h, fill=WHITE, stroke=LGRAY, sw=0.5)
    bx(ML + half, y, half, fam_h, fill=WHITE, stroke=LGRAY, sw=0.5)
    # empty checkboxes
    for cx_off in [half / 2 - 5, half + half / 2 - 5]:
        cb_y = y - fam_h / 2 - 4
        cv.setLineWidth(0.7); cv.setStrokeColor(MGRAY); cv.setFillColor(WHITE)
        cv.rect(ML + cx_off, cb_y, 9, 9, fill=1, stroke=1)
    y -= fam_h
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 5. FOLLOWING ITEMS BRIEFED (empty checkboxes)
    # ═══════════════════════════════════════════════════════════════════════
    y = section_hdr(y, "FOLLOWING ITEMS WERE BRIEFED AND FAMILIARIZED FOR THE ROUTE FLOWN")
    items_briefed = [
        "Terrain and Safe Altitudes",
        "Communication and ATC Facilities",
        "Search & Rescue Procedures",
        "Airport Layout",
        "Approach Aids",
        "Instrument Approach and Hold Procedures",
        "Operating Minima",
    ]
    for item in items_briefed:
        y = checkbox_row(y, item, h=13)
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 6. SPECIAL ITEMS BY AERODROME CATEGORY (empty checkboxes)
    # ═══════════════════════════════════════════════════════════════════════
    y = section_hdr(y, "SPECIAL ITEMS BRIEFED DUE TO AERODROME CATEGORY")
    special_items = [
        "(1) Non-standard approach aids or approach patterns",
        "(2) Unusual local weather conditions",
        "(3) Unusual characteristics or performance limitations",
        "(4) Other relevant considerations: obstructions, physical layout, lighting etc.",
        "(5) Category C aerodromes: additional considerations for approach/landing/take-off.",
    ]
    for item in special_items:
        y = checkbox_row(y, item, h=13)
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 7. SPECIAL REMARKS – AUTO FROM DATABASE (Section 1+2+3)
    # ═══════════════════════════════════════════════════════════════════════
    s1 = (airport.get("section1") or "").strip()
    s2 = (airport.get("section2") or "").strip()
    s3 = (airport.get("section3") or "").strip()
    combined = "\n".join(p for p in [s1, s2, s3] if p)
    y = section_hdr(y, "SPECIAL REMARKS  –  AERODROME BRIEFING  (AUTO FROM DATABASE)")
    y = text_block(y, combined or "No briefing data available.", fsize=8)
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 8. AERODROME RISK ASSESSMENT – AUTO FROM DATABASE
    # ═══════════════════════════════════════════════════════════════════════
    risk_level = (airport.get("ra_risk_level") or "").upper()
    risk_score = airport.get("ra_risk_score", "")
    ops_appr   = airport.get("ra_ops_approval") or airport.get("ra_risk_level") or ""
    mitigation = airport.get("ra_mitigation") or ""
    if risk_level == "HIGH":
        rbg = RISKBG_HIGH
    elif risk_level == "MEDIUM":
        rbg = RISKBG_MED
    else:
        rbg = RISKBG_LOW
    y = section_hdr(y, "AERODROME RISK ASSESSMENT  (AUTO – DATABASE)")
    risk_txt = f"RISK LEVEL: {risk_level} | CAT: {cat} | {ops_appr}"
    if mitigation:
        risk_txt += f"\nMITIGATION: {mitigation}"
    y = text_block(y, risk_txt, bg=rbg, fsize=8)
    y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 9. CZIB WARNING (if any)
    # ═══════════════════════════════════════════════════════════════════════
    czib_text = fi.get("czib", "")
    if czib_text:
        y = section_hdr(y, "SECURITY / CZIB WARNING")
        y = text_block(y, czib_text, bg=RISKBG_HIGH, border=RED, bsw=1.2, fsize=8)
        y -= 2

    # ═══════════════════════════════════════════════════════════════════════
    # 10. CERTIFICATION + COMPLETED BY
    # ═══════════════════════════════════════════════════════════════════════
    cert = ("I hereby certify that route and aerodrome familiarization was completed "
            "for the flight in accordance with AMC1 ORO.FC.105 b(2);c and OM PART C.")
    cert_h = 22
    bx(ML, y, W, cert_h, fill=colors.HexColor("#F5F5F5"), stroke=LGRAY, sw=0.5)
    for wrapped_ln in wraplines(cert, _FI, 7.5, W - 10):
        tx(wrapped_ln, ML + 5, y - 6, _FI, 7.5, colors.HexColor("#555555"))
        y -= 9
    y -= (cert_h - 9 + 2)

    # completed by row
    comp_h = 16
    bx(ML,           y, W * 0.25, comp_h, fill=colors.HexColor("#D6E4F0"), stroke=LGRAY, sw=0.5)
    bx(ML + W * 0.25, y, W * 0.50, comp_h, fill=WHITE, stroke=LGRAY, sw=0.5)
    bx(ML + W * 0.75, y, W * 0.25, comp_h, fill=WHITE, stroke=LGRAY, sw=0.5)
    tx("Completed by:", ML + 4, y - comp_h + 5, _FB, 8, DARK)
    pic = fi.get("pic", "").upper()
    tx(pic, ML + W * 0.25, y - comp_h + 5, _FB, 8.5, BLACK, align="center", width=W * 0.50)
    tx(fi.get("date", ""), ML + W * 0.75, y - comp_h + 5, _FN, 8, BLACK, align="center", width=W * 0.25)
    y -= comp_h


def generate_booklet_pdf(airport_list, airports_db, fi):
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    cv = C.Canvas(buf, pagesize=A4)
    cv.setTitle(f"FBAT-BOOKLET-{fi.get('date','')}")
    frm = cv.acroForm
    for label, icao in airport_list:
        airport = airports_db[icao]
        local_ops = fetch_local_ops_snapshot(airport)
        survey_status = get_survey_age_status(airport)
        try:
            czib_hit, czib_text = check_czib(icao)
        except Exception:
            czib_text = ""
        page_fi = {**fi, "local_ops": local_ops, "survey_status": survey_status, "czib": czib_text}
        generate_pdf_page(cv, frm, airport, None, page_fi, page_label=label)
        cv.showPage()
    cv.save(); buf.seek(0)
    return buf.getvalue()

# =============================================================================
# LOAD DB
# =============================================================================
airports, risks = load_db()

# =============================================================================
# HEADER
# =============================================================================
st.markdown("""
<div style="background:#1A3A5C;padding:18px 24px;border-radius:8px;margin-bottom:24px">
<h1 style="color:white;margin:0;font-size:22px;letter-spacing:0.3px">✈ Flight Briefing and Awareness Tool</h1>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# AIRPORT INPUTS
# =============================================================================
airport_fields = [
    ("DEPT",     "Kalkış Meydanı",    "LTBA"),
    ("DEPT ALT", "Kalkış Alternatif", "LTFM"),
    ("DEST",     "Varış Meydanı",     "EHAM"),
    ("DEST ALT", "Varış Alternatif",  "EGLL"),
]

icao_inputs = {}
col_left, col_right = st.columns(2)

def survey_badge_html(status):
    if status == "CURRENT":
        return 'survey-current'
    if status == "REVIEW DUE":
        return 'survey-due'
    return 'survey-expired'

for i, (label, desc, placeholder) in enumerate(airport_fields):
    col = col_left if i % 2 == 0 else col_right
    with col:
        st.markdown(f'<span class="airport-label">✈ {label}</span>', unsafe_allow_html=True)
        icao_val = st.text_input(desc, max_chars=4, placeholder=placeholder, key=f"icao_{label}", label_visibility="collapsed").upper().strip()
        icao_inputs[label] = icao_val

        if icao_val:
            if icao_val in airports:
                ap = airports[icao_val]
                st_status = get_survey_age_status(ap)
                rk = ap.get('ra_risk_level')
                risk_html = ""
                if rk == 'HIGH':
                    risk_html = '<div class="risk-box-high"><p>⚠ AERODROME RISK: HIGH</p></div>'
                elif rk == 'MEDIUM':
                    risk_html = '<div class="risk-box-med"><p>⚡ AERODROME RISK: MEDIUM</p></div>'
                elif rk == 'LOW':
                    risk_html = '<div class="risk-box-low"><p>✔ AERODROME RISK: LOW</p></div>'
                status_cls = survey_badge_html(st_status['status'])
                age_text = f"{st_status['days_old']} days" if st_status['days_old'] is not None else "N/A"
                st.markdown(
                    f'<div class="info-card" style="padding:8px 14px;margin:4px 0">'
                    f'<h3 style="font-size:13px">✔ {ap.get("name", icao_val)}</h3>'
                    f'<p>Kategori: {ap.get("category", "N/A")}</p></div>'
                    f'{risk_html}'
                    f'<div class="{status_cls}"><b>Survey Status:</b> {st_status["status"]} &nbsp; | &nbsp; <b>Age:</b> {age_text}</div>',
                    unsafe_allow_html=True,
                )
            elif len(icao_val) == 4:
                st.error(f"❌ {icao_val} veritabanında bulunamadı.")

st.divider()

# =============================================================================
# FLIGHT INFO
# =============================================================================
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

# =============================================================================
# GENERATE
# =============================================================================
valid_airports = [(lbl, icao) for lbl, icao in icao_inputs.items() if icao and icao in airports]
if valid_airports:
    st.info(f"📋 **{len(valid_airports)} meydan** için PDF oluşturulacak: " + " → ".join([f"**{lbl}** ({icao})" for lbl, icao in valid_airports]))
else:
    st.warning("En az bir geçerli meydan girin.")

# AIRAC warnings prior to generation
if valid_airports:
    due = []
    exp = []
    for lbl, icao in valid_airports:
        ss = get_survey_age_status(airports[icao])
        if ss['status'] == 'REVIEW DUE':
            due.append((lbl, icao, ss['days_old']))
        elif ss['status'] in ('EXPIRED', 'NO SURVEY'):
            exp.append((lbl, icao, ss['days_old']))
    if due:
        st.warning("⚠ AIRAC review due: " + " | ".join([f"{lbl} {icao} ({days} days)" for lbl, icao, days in due]))
    if exp:
        parts = []
        for lbl, icao, days in exp:
            parts.append(f"{lbl} {icao} ({'no survey date' if days is None else str(days) + ' days'})")
        st.error("⛔ Survey expired / missing: " + " | ".join(parts))

if st.button("📄  RAQ BOOKLET PDF OLUŞTUR", use_container_width=True, type="primary"):
    if not valid_airports:
        st.error("En az bir geçerli ICAO kodu girin.")
    elif not pic:
        st.error("PIC seçiniz. Admin panelden önce pilot tanımlayın.")
    else:
        with st.spinner(f"⏳ {len(valid_airports)} sayfalık booklet oluşturuluyor..."):
            try:
                pdf = generate_booklet_pdf(valid_airports, airports, {"date": date.strftime("%Y-%m-%d"), "ac_type": ac, "pic": pic, "sic": sic})
                icao_str = "-".join([icao for _, icao in valid_airports])
                fname = f"FBAT_{icao_str}_{date.strftime('%Y-%m-%d')}.pdf"
                st.success(f"✔ {len(valid_airports)} sayfalık booklet hazır!")
                st.download_button(f"⬇  PDF Booklet İndir ({len(valid_airports)} sayfa)", pdf, fname, "application/pdf", use_container_width=True)

                pilot_obj = find_pilot(pilots, pic)
                if pilot_obj:
                    ok, msg_result = send_email(pilot_obj["email"], pic, valid_airports, date.strftime("%Y-%m-%d"), ac)
                    if ok:
                        st.success(f"📧 Mail gönderildi → {pilot_obj['email']}")
                    else:
                        st.warning(f"⚠ Mail gönderilemedi: {msg_result}")
                if sic:
                    sic_obj = find_pilot(pilots, sic)
                    if sic_obj:
                        ok, msg_result = send_email(sic_obj["email"], sic, valid_airports, date.strftime("%Y-%m-%d"), ac)
                        if ok:
                            st.success(f"📧 Mail gönderildi → {sic_obj['email']}")
                        else:
                            st.warning(f"⚠ SIC maili gönderilemedi: {msg_result}")
            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© Flight Briefing and Awareness Tool – AMC1 ORO.FC.105 b(2);c")

# =============================================================================
# ADMIN PANEL
# =============================================================================
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

        with tab1:
            col_icao, col_btn = st.columns([2, 1])
            with col_icao:
                icao_e = st.text_input("ICAO Kodu", max_chars=4, placeholder="LTFM", key="ei").upper().strip()
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                load_btn = st.button("📂 Yükle", use_container_width=True)

            if load_btn and icao_e:
                ap_data = airports.get(icao_e, {})
                if ap_data.get('ra_briefing_items'):
                    loaded_summary = "\n".join(ap_data['ra_briefing_items'])
                else:
                    parts = [ap_data.get('section1',''), ap_data.get('section2',''), ap_data.get('section3','')]
                    loaded_summary = "\n".join(p for p in parts if p and str(p).upper() != 'N/A')
                st.session_state["edit_name"] = ap_data.get("name", "")
                st.session_state["edit_cat"] = ap_data.get("category", "A")
                st.session_state["edit_summary"] = loaded_summary
                st.session_state["edit_aip_name"] = ap_data.get("aip_source_name", "")
                st.session_state["edit_aip_url"] = ap_data.get("aip_source_url", "")
                st.session_state["edit_aip_ref"] = ap_data.get("aip_reference", "")
                if ap_data:
                    st.success(f"✔ {icao_e} yüklendi — {ap_data.get('name','')}")
                else:
                    st.info(f"ℹ {icao_e} yeni meydan.")

            name_e = st.text_input("Meydan Adı", key="edit_name")
            cat_e  = st.selectbox("Kategori", ["A","B","C"], index=["A","B","C"].index(st.session_state.get("edit_cat","A")) if st.session_state.get("edit_cat","A") in ["A","B","C"] else 0)

            if icao_e and icao_e in airports:
                ss = get_survey_age_status(airports[icao_e])
                cls = survey_badge_html(ss['status'])
                age_text = f"{ss['days_old']} days" if ss['days_old'] is not None else "N/A"
                st.markdown(f'<div class="{cls}"><b>Survey Status:</b> {ss["status"]} &nbsp;|&nbsp; <b>Last reviewed:</b> {ss.get("last") or "N/A"} &nbsp;|&nbsp; <b>Age:</b> {age_text}</div>', unsafe_allow_html=True)

            st.divider()
            admin_mode = st.radio("İşlem seçin:", ["📋 Summary Database Update", "🎯 Risk Assessment Tool"], horizontal=True, key="admin_mode")

            if "Summary" in admin_mode:
                st.markdown('<div class="ra-block"><h4>📋 Summary / Briefing Notları</h4></div>', unsafe_allow_html=True)
                summary_e = st.text_area("Özet (her satır ayrı madde olarak PDF'e işlenir)", key="edit_summary", height=200)
                aip_name = st.text_input("Official source label", key="edit_aip_name", placeholder="Germany eAIP")
                aip_url  = st.text_input("Official source URL", key="edit_aip_url", placeholder="https://...")
                aip_ref  = st.text_input("Reference / section", key="edit_aip_ref", placeholder="AD 2.21 / AD 2.22")

                if st.button("💾 Kaydet", use_container_width=True, key="save_summary"):
                    if icao_e:
                        try:
                            lines = [l.strip() for l in summary_e.split("\n") if l.strip()]
                            # Section1 güncellenir ama section2/3 korunur
                            payload = {
                                "category": cat_e,
                                "ra_briefing_items": lines,
                            }
                            if summary_e.strip():
                                payload["section1"] = summary_e
                            if aip_name: payload["aip_source_name"] = aip_name
                            if aip_url:  payload["aip_source_url"]  = aip_url
                            if aip_ref:  payload["aip_reference"]   = aip_ref
                            ok = update_airport(icao_e, payload)
                            if ok:
                                st.success(f"✔ {icao_e} kaydedildi!")
                                st.rerun()
                            else:
                                st.error("❌ Kayıt başarısız.")
                        except Exception as _ex:
                            st.error(f"❌ Hata: {_ex}")
                    else:
                        st.warning("ICAO girin.")
            else:
                if not icao_e:
                    st.info("ℹ Yukarıdan ICAO kodunu girin ve Yükle'ye tıklayın.")
                else:
                    assessed_by = st.text_input("Değerlendiren (isim / callsign)", key="ra_by")
                    aip_name = st.text_input("Official source label", key="edit_aip_name_ra", value=airports.get(icao_e, {}).get("aip_source_name", ""))
                    aip_url = st.text_input("Official source URL", key="edit_aip_url_ra", value=airports.get(icao_e, {}).get("aip_source_url", ""))
                    aip_ref = st.text_input("Reference / section", key="edit_aip_ref_ra", value=airports.get(icao_e, {}).get("aip_reference", ""))

                    st.markdown('<div class="ra-block"><h4>🏛 Block 1 — Aerodrome Classification & Authorization</h4></div>', unsafe_allow_html=True)
                    ra_cat = st.selectbox("Aerodrome category?", ["A","B","C"], key="ra_cat")
                    c1, c2 = st.columns(2)
                    ra_sp_desig = c1.checkbox("Special aerodrome designation applies?", key="ra_spd")
                    ra_sp_crew = c2.checkbox("Special crew qualification required?", key="ra_spc")
                    ra_sp_approval = st.checkbox("Special operator approval required?", key="ra_spa")

                    st.markdown('<div class="ra-block"><h4>📐 Block 2 — Approach & Navigation Environment</h4></div>', unsafe_allow_html=True)
                    st.caption("Runway designators")
                    if 'ra_rwy_sets' not in st.session_state:
                        st.session_state['ra_rwy_sets'] = 1
                    rwy_inputs_all = []
                    for set_i in range(st.session_state['ra_rwy_sets']):
                        cols = st.columns(4)
                        for j in range(4):
                            v = cols[j].text_input(f"RWY {set_i*4+j+1}", max_chars=4, key=f"ra_rwy_{set_i}_{j}").upper().strip()
                            rwy_inputs_all.append(v)
                    if st.button("➕ Daha fazla pist ekle (4 kutu)", key="ra_add_rwy"):
                        st.session_state['ra_rwy_sets'] += 1
                        st.rerun()
                    active_runways = [r for r in rwy_inputs_all if r]
                    rwy_approaches = {}
                    if active_runways:
                        st.caption("Runway approach capability")
                        for rwy in active_runways:
                            rwy_approaches[rwy] = st.multiselect(
                                f"RWY {rwy}",
                                ["Precision CAT III", "Precision CAT II", "ILS", "GLS", "RNP AR", "RNP", "Offset Precision", "Non-Precision", "Offset Non-Precision"],
                                key=f"ra_app_{rwy}"
                            )
                    ra_prec = st.radio("Is precision approach capability available at this aerodrome?", ["Yes", "No"], horizontal=True, key="ra_prec")
                    ra_angle = st.selectbox("Approach geometry", ["Normal (< 3.9°)", "Elevated (3.9°–4.49°)", "Steep (≥ 4.5°)"], key="ra_angle")
                    c_m1, c_m2 = st.columns([1,2])
                    ra_msa_ft = c_m1.number_input("Max MSA within TMA (ft)", min_value=0, max_value=30000, step=100, value=0, key="ra_msa_ft")
                    ra_msa_sector = c_m2.selectbox("Sector", ["All Sectors","N","NE","E","SE","S","SW","W","NW"], key="ra_msa_sector")
                    ra_high_da = st.checkbox("Precision DA/DH ≥ 400 ft due to terrain?", key="ra_hda", disabled=(ra_prec == "No"))
                    ra_offset = st.selectbox("Offset approach published?", ["None", "Offset Non-Precision", "Offset Precision"], key="ra_offset")
                    ra_madem = st.selectbox("Missed approach complexity", ["Standard", "Above standard", "Special procedure required"], key="ra_madem")
                    ra_oei_ma = st.checkbox("Engine-out go-around requires dedicated briefing?", key="ra_oema")
                    ra_gnss_outage = st.checkbox("GNSS outage / GPS NOTAM expected?", key="ra_gnss_outage")

                    st.markdown('<div class="ra-block"><h4>🛬 Block 3 — Runway & Ground Environment</h4></div>', unsafe_allow_html=True)
                    ra_rwy_w = st.selectbox("Runway width", ["≥ 45 m", "30–44 m", "< 30 m"], key="ra_rwyw")
                    ra_rwy_marg = st.selectbox("Runway length margin", ["Adequate", "Marginal", "Critical"], key="ra_rwym")
                    ra_phys_comp = st.selectbox("Runway physical characteristics", ["None", "Slope", "Displaced threshold", "Complex combination"], key="ra_phc")
                    ctx1, ctx2 = st.columns(2)
                    ra_taxi_complex = ctx1.checkbox("Taxi routing / hot spots complex?", key="ra_taxi")
                    ra_rwy_crossing = ctx2.selectbox("Runway crossing required?", ["No", "Arrival", "Departure", "Both"], key="ra_rwxing")

                    st.markdown('<div class="ra-block"><h4>⚡ Block 4 — Departure & OEI Risk</h4></div>', unsafe_allow_html=True)
                    ra_oei_sid = st.checkbox("Special OEI SID required?", key="ra_oisid")
                    ra_oei_grad = st.selectbox("OEI climb gradient", ["Standard", "Demanding", "Critical"], key="ra_oigrad")
                    ra_perf_lim = st.checkbox("Performance-limited departure likely?", key="ra_plim")

                    st.markdown('<div class="ra-block"><h4>🌤 Block 5 — Weather & ATC Environment</h4></div>', unsafe_allow_html=True)
                    ra_lvp = st.selectbox("LVP / fog / low ceiling exposure", ["Rare / not significant", "Occasional", "Frequent"], key="ra_lvp")
                    cwx1, cwx2 = st.columns(2)
                    ra_xw_risk = cwx1.checkbox("Crosswind / windshear / contamination exposure significant?", key="ra_xw")
                    ra_terr_hh = cwx2.checkbox("Mountain / terrain / hot-high effects significant?", key="ra_thh")
                    ra_atc = st.selectbox("ATC / sequencing / taxi complexity", ["Normal", "Moderate", "Significant"], key="ra_atc")
                    ra_mil_traff = st.checkbox("Military / mixed traffic or non-standard phraseology?", key="ra_mil")
                    ra_gnss_risk = st.selectbox("GNSS spoofing / jamming risk", ["No known risk", "Advisories / degradation", "Active jamming / spoofing reported"], key="ra_gnss")

                    st.markdown('<div class="ra-block"><h4>🔐 Block 6 — Security, Alternate & Operational Resilience</h4></div>', unsafe_allow_html=True)
                    ra_pol_risk = st.selectbox("Political / security risk", ["No significant concern", "Caution advisories in effect", "High risk"], key="ra_pol")
                    ra_arpt_sec = st.selectbox("Airport security / handling standards", ["Adequate / reliable", "Uncertain / inconsistent", "Poor / inadequate"], key="ra_sec")
                    ra_st_oversight = st.selectbox("State safety oversight / compliance", ["Acceptable", "Partial", "Inadequate / unrecognised"], key="ra_usoap")
                    ra_alt = st.selectbox("Adequate alternate within fuel planning range", ["Yes — available and suitable", "Limited options", "No adequate alternate"], key="ra_alt")
                    ra_alt_lvp = False
                    if ra_alt != "No adequate alternate":
                        ra_alt_lvp = st.checkbox("Alternate aerodrome has LVP capability?", key="ra_alt_lvp")
                    ra_fuel = st.selectbox("Fuel / ground handling reliability", ["Reliable and verified", "Uncertain / variable", "Poor / known concerns"], key="ra_fuel")
                    ra_crew_rec = st.radio("Crew has operated here within last 12 months?", ["Yes","No"], horizontal=True, key="ra_crec")

                    if st.button("🎯 Calculate & Save Risk", use_container_width=True, type="primary", key="ra_calc"):
                        angle_map = {"Normal (< 3.9°)": "normal", "Elevated (3.9°–4.49°)": "moderate", "Steep (≥ 4.5°)": "steep"}
                        rwy_map = {"≥ 45 m": "wide", "30–44 m": "medium", "< 30 m": "narrow"}
                        lvp_map = {"Rare / not significant": "no", "Occasional": "sometimes", "Frequent": "frequent"}
                        atc_map = {"Normal": "no", "Moderate": "moderate", "Significant": "significant"}
                        pol_map = {"No significant concern": "no", "Caution advisories in effect": "caution", "High risk": "high"}
                        sec_map = {"Adequate / reliable": "good", "Uncertain / inconsistent": "uncertain", "Poor / inadequate": "poor"}
                        ov_map = {"Acceptable": "yes", "Partial": "partial", "Inadequate / unrecognised": "no"}
                        alt_map = {"Yes — available and suitable": "yes", "Limited options": "limited", "No adequate alternate": "no"}
                        fuel_map = {"Reliable and verified": "reliable", "Uncertain / variable": "uncertain", "Poor / known concerns": "poor"}
                        offset_map = {"None": "none", "Offset Non-Precision": "offset_non_precision", "Offset Precision": "offset_precision"}
                        ma_map = {"Standard": "standard", "Above standard": "above_standard", "Special procedure required": "special"}
                        crossing_map = {"No": "no", "Arrival": "arrival", "Departure": "departure", "Both": "both"}
                        grad_map = {"Standard": "standard", "Demanding": "demanding", "Critical": "critical"}
                        marg_map = {"Adequate": "adequate", "Marginal": "marginal", "Critical": "critical"}
                        phys_map = {"None": "none", "Slope": "slope", "Displaced threshold": "displaced_threshold", "Complex combination": "complex_combination"}
                        gnss_map = {"No known risk": "no", "Advisories / degradation": "notam", "Active jamming / spoofing reported": "active"}

                        survey = {
                            'cat': ra_cat,
                            'sp_desig': ra_sp_desig,
                            'sp_crew': ra_sp_crew,
                            'sp_approval': ra_sp_approval,
                            'prec': ra_prec == 'Yes',
                            'angle': angle_map[ra_angle],
                            'msa_ft': int(ra_msa_ft),
                            'msa_sector': ra_msa_sector,
                            'high_da': bool(ra_high_da) if ra_prec == 'Yes' else False,
                            'offset': offset_map[ra_offset],
                            'madem': ma_map[ra_madem],
                            'oei_ma_brief': ra_oei_ma,
                            'gnss_outage': ra_gnss_outage,
                            'rwy_approaches': rwy_approaches,
                            'rwy_w': rwy_map[ra_rwy_w],
                            'rwy_marg': marg_map[ra_rwy_marg],
                            'phys_comp': phys_map[ra_phys_comp],
                            'taxi_complex': ra_taxi_complex,
                            'rwy_crossing': crossing_map[ra_rwy_crossing],
                            'oei_sid': ra_oei_sid,
                            'oei_grad': grad_map[ra_oei_grad],
                            'perf_lim': ra_perf_lim,
                            'lvp': lvp_map[ra_lvp],
                            'xw_risk': ra_xw_risk,
                            'terr_hh': ra_terr_hh,
                            'atc': atc_map[ra_atc],
                            'mil_traff': ra_mil_traff,
                            'gnss_risk': gnss_map[ra_gnss_risk],
                            'pol_risk': pol_map[ra_pol_risk],
                            'arpt_sec': sec_map[ra_arpt_sec],
                            'st_oversight': ov_map[ra_st_oversight],
                            'alt': alt_map[ra_alt],
                            'alt_lvp': ra_alt_lvp,
                            'fuel': fuel_map[ra_fuel],
                            'crew_rec': ra_crew_rec == 'Yes',
                        }
                        try:
                            result  = calc_risk(survey)
                            summary = gen_summary_items(survey, result)
                            today_str = datetime.date.today().strftime("%Y-%m-%d")
                            due_str   = (datetime.date.today() + datetime.timedelta(days=28)).strftime("%Y-%m-%d")

                            r_level = result.get('risk', 'LOW')
                            ops_appr = {"HIGH": "DISPATCH REQUIRES APPROVAL",
                                        "MEDIUM": "DISPATCH WITH CAUTION"}.get(r_level, "DISPATCH OK")

                            update_payload = {
                                "ra_risk_level":       r_level,
                                "ra_risk_score":       result.get('score', 0),
                                "ra_risk_basis":       result.get('basis', []),
                                "ra_key_drivers":      result.get('drivers', []),
                                "ra_actions":          result.get('actions', []),
                                "ra_briefing_items":   summary,
                                "ra_assessment_date":  today_str,
                                "ra_reassessment_due": due_str,
                                "ra_assessed_by":      assessed_by or "Admin",
                                "ra_ops_approval":     ops_appr,
                                "ra_mitigation":       "; ".join(result.get('actions', [])[:3]),
                                "survey_last_updated": today_str,
                                "survey_updated_by":   assessed_by or "Admin",
                                "category":            ra_cat,
                            }
                            if aip_name: update_payload["aip_source_name"] = aip_name
                            if aip_url:  update_payload["aip_source_url"]  = aip_url
                            if aip_ref:  update_payload["aip_reference"]   = aip_ref

                            ok = update_airport(icao_e, update_payload)
                            if ok:
                                st.success(f"✔ {icao_e} kaydedildi! Risk: **{r_level}** | Score: {result.get('score',0)} | Review: {due_str}")
                                st.rerun()
                            else:
                                st.error("❌ DB kayıt başarısız.")
                        except Exception as _ex:
                            import traceback as _tb
                            st.error(f"❌ Hata: {_ex}")
                            st.code(_tb.format_exc())

            st.divider()
            if st.button("🔄 Veritabanını Yenile", use_container_width=True):
                st.rerun()

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

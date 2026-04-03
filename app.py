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

def _terrain_band(msa_ft):
    if msa_ft >= 12000:
        return 'extreme', 3
    if msa_ft >= 8000:
        return 'high', 2
    if msa_ft >= 5000:
        return 'moderate', 1
    return 'low', 0


def _dedupe_keep_order(items, limit=None):
    out = []
    seen = set()
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
        if limit and len(out) >= limit:
            break
    return out


def _get_runway_capability_summary(rwy_approaches):
    precision_types = {'Precision CAT III', 'Precision CAT II', 'ILS', 'GLS', 'RNP AR', 'RNP', 'Offset Precision'}
    gnss_dependent = {'GLS', 'RNP AR', 'RNP'}
    has_precision = any(t in precision_types for vals in rwy_approaches.values() for t in vals)
    has_cat3 = any('Precision CAT III' in vals for vals in rwy_approaches.values())
    has_cat2 = any('Precision CAT II' in vals for vals in rwy_approaches.values())
    has_offset_prec = any('Offset Precision' in vals for vals in rwy_approaches.values())
    has_offset_nonprec = any('Offset Non-Precision' in vals for vals in rwy_approaches.values())
    has_rnp_ar = any('RNP AR' in vals for vals in rwy_approaches.values())
    gnss_rwys = [rwy for rwy, vals in rwy_approaches.items() if any(t in gnss_dependent for t in vals)]
    all_non_precision = bool(rwy_approaches) and all(
        all(t in ('Non-Precision', 'Offset Non-Precision') for t in vals) if vals else True
        for vals in rwy_approaches.values()
    )
    return {
        'has_precision': has_precision,
        'has_cat2': has_cat2,
        'has_cat3': has_cat3,
        'has_offset_prec': has_offset_prec,
        'has_offset_nonprec': has_offset_nonprec,
        'has_rnp_ar': has_rnp_ar,
        'gnss_rwys': gnss_rwys,
        'all_non_precision': all_non_precision,
    }


def calc_risk(s):
    score = 0
    override_high = []
    override_medium = []
    drivers = []
    actions = []
    context_notes = []

    def add(pts, driver=None, action=None, note=None):
        nonlocal score
        score += pts
        if driver:
            drivers.append(driver)
        if action:
            actions.append(action)
        if note:
            context_notes.append(note)

    rwy_approaches = s.get('rwy_approaches', {})
    rwys = _get_runway_capability_summary(rwy_approaches)
    s['prec'] = rwys['has_precision']

    # Overrides
    if s.get('cat') == 'C':
        override_high.append('CAT C aerodrome (automatic HIGH)')
    if s.get('pol_risk') == 'high':
        override_high.append('High security / political threat (automatic HIGH)')
    if not s.get('prec') and s.get('angle') == 'steep' and s.get('oei_sid'):
        override_high.append('No precision approach + steep approach + special OEI SID')
    if s.get('sp_approval'):
        override_medium.append('Special operator approval required')
    if s.get('lvp') == 'frequent' and s.get('alt') == 'no':
        override_medium.append('Frequent LVP with no adequate alternate')

    # Block 1 — Classification & authorisation
    if s.get('sp_desig'):
        add(2, 'Special aerodrome designation applies', 'Verify operator-specific aerodrome procedures')
    if s.get('sp_crew'):
        add(2, 'Special crew qualification required', 'Confirm crew qualification and recent exposure are valid')
    if s.get('sp_approval'):
        add(2, 'Special operator approval required', 'Obtain and file operator approval before dispatch')

    # Block 2 — Approach, navigation and terrain
    if not s.get('prec'):
        add(3, 'Non-precision environment only', 'Review non-precision minima, stabilisation criteria and go-around gates')
    if s.get('angle') == 'moderate':
        add(2, 'Elevated approach angle (3.9°–4.49°)')
    if s.get('angle') == 'steep':
        add(3, 'Steep approach angle (≥ 4.5°)', 'Conduct dedicated steep-approach briefing and confirm aircraft suitability')

    msa = int(s.get('msa_ft', 0) or 0)
    msa_sector = s.get('msa_sector', 'All Sectors')
    terrain_band, terrain_pts = _terrain_band(msa)
    if terrain_pts:
        desc = {
            'moderate': f'Moderate terrain environment — MSA {msa:,} ft ({msa_sector})',
            'high': f'High terrain environment — MSA {msa:,} ft ({msa_sector})',
            'extreme': f'Extreme terrain environment — MSA {msa:,} ft ({msa_sector})',
        }[terrain_band]
        add(terrain_pts, desc, 'Verify MSA / sector altitudes and terrain escape awareness on all phases')

    # MSA interaction logic for situational awareness
    terrain_interaction_pts = 0
    if msa >= 8000 and not s.get('prec'):
        terrain_interaction_pts += 1
    if msa >= 8000 and s.get('angle') in ('moderate', 'steep'):
        terrain_interaction_pts += 1
    if msa >= 8000 and s.get('alt') in ('limited', 'no'):
        terrain_interaction_pts += 1
    if msa >= 12000 and s.get('lvp') in ('sometimes', 'frequent'):
        terrain_interaction_pts += 1
    if terrain_interaction_pts:
        add(
            terrain_interaction_pts,
            'Terrain-driven situational awareness burden increased',
            'Emphasise terrain cross-checks, escape options and vertical awareness during the briefing'
        )

    if s.get('high_da'):
        add(1, 'Terrain-limited precision minima (DA/DH ≥ 400 ft)')
    if s.get('offset_mode') == 'offset_non_precision':
        add(2, 'Offset non-precision approach in use', 'Brief visual segment and lateral guidance limitations carefully')
    elif s.get('offset_mode') == 'offset_precision':
        add(1, 'Offset precision approach in use', 'Brief offset guidance and go-around geometry')
    elif s.get('offset'):
        add(1, 'Offset approach procedure in use')

    ma_complexity = s.get('ma_complexity', 'standard')
    if ma_complexity == 'above_standard' or s.get('madem'):
        add(2, 'Missed approach gradient above standard', 'Conduct detailed missed approach review before departure')
    elif ma_complexity == 'special_required':
        add(3, 'Special missed approach procedure required', 'Review terrain and procedure notes in detail; brief trigger points for immediate go-around')
    if s.get('oei_ma_brief'):
        add(2, 'Engine-out go-around requires dedicated briefing', 'Assign PF/PM duties and verbalise OEI go-around actions')

    # Per-runway capability cross-checks
    if rwys['has_rnp_ar']:
        add(1, 'RNP AR procedure published', 'Confirm aircraft eligibility, database currency and crew authorisation before use')
    if rwys['has_offset_nonprec'] and s.get('offset_mode') == 'none':
        add(1, 'Offset non-precision capability exists on at least one runway', 'Verify selected runway / approach pair during dispatch review')
    if rwys['has_offset_prec'] and s.get('offset_mode') == 'none':
        add(1, 'Offset precision capability exists on at least one runway', 'Verify selected runway / approach geometry during briefing')
    if not rwys['has_cat2'] and not rwys['has_cat3'] and s.get('lvp') in ('sometimes', 'frequent'):
        add(2, 'No CAT II / III capability despite LVP exposure', 'Ensure alternate is suitable for low-visibility recovery')
    elif rwys['has_cat2'] and not rwys['has_cat3'] and s.get('lvp') == 'frequent':
        add(1, 'CAT II only with frequent LVP exposure', 'Verify CAT II crew / aircraft status and diversion trigger')

    gnss_risk = s.get('gnss_risk', 'no')
    if gnss_risk == 'notam':
        add(2, 'GNSS degradation advisories active in region', 'Cross-check navigation with conventional navaids and monitor NOTAM updates')
    elif gnss_risk == 'active':
        add(4, 'Active GNSS spoofing / jamming reported', 'Treat GNSS as unreliable and brief degraded-navigation procedures')

    if s.get('gnss_outage') and rwys['gnss_rwys']:
        add(
            3,
            f"GNSS outage affects RWY {', '.join(rwys['gnss_rwys'])}",
            'Prefer ILS / CAT II / CAT III where available; avoid reliance on GLS / RNP during outage'
        )

    # Block 3 — Runway & ground environment
    if s.get('rwy_w') == 'narrow':
        add(3, 'Narrow runway (< 30 m)', 'Confirm crosswind, tracking and landing technique margins for narrow runway operations')
    elif s.get('rwy_w') == 'medium':
        add(1, 'Reduced runway width (30–44 m)')

    if s.get('rwy_margin') == 'marginal' or s.get('rwy_marg'):
        add(2, 'Marginal runway length for planned operation', 'Recompute take-off / landing margins with actual conditions and expected runway state')
    elif s.get('rwy_margin') == 'critical':
        add(3, 'Critical runway length margin', 'Apply conservative performance policy and validate stop / accelerate-go margins')

    phys = s.get('runway_characteristics', 'none')
    if phys == 'slope':
        add(1, 'Runway slope relevant to performance / handling')
    elif phys == 'displaced_threshold':
        add(1, 'Displaced threshold affects usable landing distance')
    elif phys == 'complex_combination' or s.get('phys_comp'):
        add(2, 'Complex runway geometry / physical layout', 'Study charted distances, threshold displacement and visual cues before operation')

    if s.get('taxi_complex'):
        add(2, 'Complex taxi routing / hot spots identified', 'Brief hot spots, crossing plan and low-visibility taxi discipline')
    rc = s.get('rwy_crossing', 'no')
    if rc in ('after_landing', 'before_departure'):
        add(1, f"Runway crossing required ({'after landing' if rc == 'after_landing' else 'before departure'})", 'Brief runway crossing points and sterile-readback discipline')
    elif rc == 'both':
        add(2, 'Runway crossing required on both arrival and departure', 'Brief all crossing points and expected ATC flow constraints')

    # Block 4 — Departure & OEI
    if s.get('oei_sid'):
        add(3, 'Special OEI SID required', 'Complete OEI SID analysis and confirm departure runway-specific escape path')
    oei_grad = s.get('oei_gradient', 'standard')
    if oei_grad == 'demanding' or s.get('oei_grad'):
        add(2, 'Demanding OEI climb gradient', 'Review obstacle clearance margins against actual TOW and atmospheric conditions')
    elif oei_grad == 'critical':
        add(3, 'Critical OEI climb gradient', 'Reassess payload / fuel / runway choice before release')
    if s.get('perf_lim'):
        add(1, 'Performance-limited departure likely', 'Check WAT / climb-limited mass and consider weight restriction if required')
    if s.get('weight_restriction'):
        add(1, 'Weight restriction likely for safe departure', 'Coordinate payload / fuel strategy with OCC before dispatch')

    # Block 5 — Weather & ATC
    if s.get('lvp') == 'sometimes':
        add(1, 'Occasional LVP / low ceiling exposure')
    elif s.get('lvp') == 'frequent':
        add(2, 'Frequent LVP / fog / low visibility exposure', 'Monitor trend forecasts and pre-define diversion triggers')
    if s.get('xw_risk'):
        add(2, 'Crosswind / windshear / contamination exposure', 'Review crosswind policy, contamination performance and escape strategy')
    if s.get('terr_hh'):
        add(2, 'Terrain / mountain wave / hot-high operating environment', 'Validate climb performance and discuss weather-driven workload increase')
    if s.get('atc') == 'moderate':
        add(1, 'Moderate ATC / sequencing complexity')
    elif s.get('atc') == 'significant':
        add(2, 'Significant ATC / slot / sequencing complexity', 'Allow extra clearance time and pre-brief likely taxi / holding constraints')
    if s.get('mil_traff'):
        add(2, 'Military / mixed traffic or unusual ATC phraseology', 'Review local phraseology and expect non-standard traffic prioritisation')

    # Block 6 — Security, alternate and resilience
    if s.get('pol_risk') == 'caution':
        add(3, 'Political / security caution advisory in effect', 'Obtain current security briefing and local ground-security guidance')
    if s.get('arpt_sec') == 'uncertain':
        add(3, 'Airport security / handling reliability uncertain', 'Coordinate enhanced handling and crew protection measures with local provider')
    elif s.get('arpt_sec') == 'poor':
        add(4, 'Poor airport security / handling environment', 'Consult company security chain before operating and define ramp exposure limits')
    if s.get('st_oversight') == 'partial':
        add(2, 'Partial state oversight / compliance concern')
    elif s.get('st_oversight') == 'no':
        add(4, 'Inadequate or unrecognised state safety oversight', 'Verify OM limitations and review company-specific safety notices')

    if s.get('alt') == 'limited':
        add(2, 'Limited alternate options within planning range', 'Identify robust alternates and consider additional contingency fuel')
    elif s.get('alt') == 'no':
        add(3, 'No adequate alternate within planning range', 'Reassess dispatch viability and contingency fuel policy with OCC')

    if s.get('lvp') == 'frequent':
        if not s.get('alt_lvp'):
            add(2, 'Destination has frequent LVP and alternate LVP capability is not confirmed', 'Choose a CAT-capable alternate when practical')
        elif s.get('alt_cat') == 'CAT II':
            add(1, 'Alternate has CAT II only under frequent LVP exposure', 'Confirm CAT II minima and diversion strategy before release')

    if s.get('fuel') == 'uncertain':
        add(1, 'Fuel / ground handling reliability uncertain', 'Confirm uplift availability before departure day')
    elif s.get('fuel') == 'poor':
        add(2, 'Fuel / ground handling reliability poor', 'Coordinate alternative supply or protected fuel arrangement')
    if not s.get('crew_rec'):
        add(1, 'No crew recency at this aerodrome within 12 months', 'Use aerodrome-specific briefing material and allocate extra briefing time')

    # Final risk level
    if override_high:
        risk = 'HIGH'
        basis = override_high
    elif score >= 11:
        risk = 'HIGH'
        basis = [f'Weighted risk score: {score} (HIGH threshold ≥ 11)'] + override_medium
    elif override_medium or score >= 5:
        risk = 'MEDIUM'
        basis = override_medium + ([f'Weighted risk score: {score} (MEDIUM threshold ≥ 5)'] if score else [])
    else:
        risk = 'LOW'
        basis = [f'Weighted risk score: {score} (LOW threshold < 5)']

    drivers = _dedupe_keep_order(drivers, limit=5)
    actions = _dedupe_keep_order(actions, limit=5)
    context_notes = _dedupe_keep_order(context_notes, limit=4)

    return {
        'risk': risk,
        'score': score,
        'basis': basis,
        'drivers': drivers,
        'actions': actions,
        'notes': context_notes,
    }


def gen_summary_items(s):
    items = []
    rwy_approaches = s.get('rwy_approaches', {})
    rwys = _get_runway_capability_summary(rwy_approaches)
    s['prec'] = rwys['has_precision']

    if s.get('cat'):
        items.append(f"CAT {s['cat']} aerodrome")
    if s.get('sp_desig'):
        items.append('Special aerodrome designation applies — operator procedures to be followed')
    if s.get('sp_crew'):
        items.append('Special crew qualification required')
    if s.get('sp_approval'):
        items.append('Special operator approval required before dispatch')

    if not s.get('prec'):
        items.append('Non-precision environment only — review minima and stabilisation criteria')
    elif rwys['has_cat3']:
        items.append('CAT III capability available on at least one runway')
    elif rwys['has_cat2']:
        items.append('CAT II capability available on at least one runway')
    else:
        items.append('Precision capability available — confirm selected runway / approach pair')

    if s.get('angle') == 'steep':
        items.append('Steep approach geometry — dedicated approach briefing required')
    elif s.get('angle') == 'moderate':
        items.append('Elevated approach angle — monitor vertical path discipline')

    msa = int(s.get('msa_ft', 0) or 0)
    if msa > 0:
        terrain_band, _ = _terrain_band(msa)
        if terrain_band in ('high', 'extreme'):
            items.append(f"High terrain environment — MSA {msa:,} ft ({s.get('msa_sector', 'All Sectors')})")
        elif terrain_band == 'moderate':
            items.append(f"Moderate terrain environment — MSA {msa:,} ft ({s.get('msa_sector', 'All Sectors')})")
    if s.get('high_da'):
        items.append('Terrain-limited approach minima — DA/DH at or above 400 ft')

    offset_mode = s.get('offset_mode', 'none')
    if offset_mode == 'offset_non_precision':
        items.append('Offset non-precision approach published — visual segment review required')
    elif offset_mode == 'offset_precision':
        items.append('Offset precision approach published — brief guidance and go-around geometry')
    elif s.get('offset'):
        items.append('Offset approach procedure in use')

    ma_complexity = s.get('ma_complexity', 'standard')
    if ma_complexity == 'above_standard' or s.get('madem'):
        items.append('Missed approach gradient above standard — detailed missed approach review required')
    elif ma_complexity == 'special_required':
        items.append('Special missed approach procedure required')
    if s.get('oei_ma_brief'):
        items.append('Engine-out go-around requires dedicated crew briefing')

    if s.get('rwy_w') == 'narrow':
        items.append('Narrow runway — confirm directional control and crosswind margin')
    elif s.get('rwy_w') == 'medium':
        items.append('Reduced runway width — increased tracking accuracy required')

    if s.get('rwy_margin') == 'critical':
        items.append('Critical runway length margin — conservative performance review required')
    elif s.get('rwy_margin') == 'marginal' or s.get('rwy_marg'):
        items.append('Marginal runway length — performance margins must be validated')

    phys = s.get('runway_characteristics', 'none')
    if phys == 'slope':
        items.append('Runway slope affects landing / take-off performance')
    elif phys == 'displaced_threshold':
        items.append('Displaced threshold reduces usable landing distance')
    elif phys == 'complex_combination' or s.get('phys_comp'):
        items.append('Complex runway geometry — study charted distances and cues carefully')

    if s.get('taxi_complex'):
        items.append('Complex taxi routing / hot spots — chart study required before operation')
    rc = s.get('rwy_crossing', 'no')
    if rc == 'after_landing':
        items.append('Runway crossing required after landing')
    elif rc == 'before_departure':
        items.append('Runway crossing required before departure')
    elif rc == 'both':
        items.append('Runway crossing required on arrival and departure')

    if s.get('oei_sid'):
        items.append('Special OEI SID / engine-out departure review required')
    oei_grad = s.get('oei_gradient', 'standard')
    if oei_grad == 'critical':
        items.append('Critical OEI climb gradient — reassess payload / fuel before release')
    elif oei_grad == 'demanding' or s.get('oei_grad'):
        items.append('Demanding OEI climb gradient — obstacle clearance critical')
    if s.get('perf_lim'):
        items.append('Performance-limited departure likely under actual conditions')
    if s.get('weight_restriction'):
        items.append('Weight restriction may be required')

    if s.get('lvp') == 'frequent':
        items.append('Frequent LVP / fog exposure — monitor trend forecasts and diversion trigger')
    elif s.get('lvp') == 'sometimes':
        items.append('Occasional LVP / low ceiling exposure')
    if s.get('xw_risk'):
        items.append('Crosswind / windshear / contamination exposure significant')
    if s.get('terr_hh'):
        items.append('Mountain / terrain / hot-high environment increases workload')
    if s.get('atc') == 'significant':
        items.append('Significant ATC / slot / sequencing complexity expected')
    elif s.get('atc') == 'moderate':
        items.append('Moderate ATC complexity expected')
    if s.get('mil_traff'):
        items.append('Military or mixed traffic may produce non-standard ATC flow')

    if s.get('gnss_risk') == 'active':
        items.append('Active GNSS interference reported — use conventional nav cross-checks')
    elif s.get('gnss_risk') == 'notam':
        items.append('GNSS degradation advisories active in region')
    if s.get('gnss_outage') and rwys['gnss_rwys']:
        items.append(f"GNSS outage affects {', '.join(rwys['gnss_rwys'])} — prefer ILS / CAT procedures where available")

    if s.get('pol_risk') == 'high':
        items.append('High political / security risk — enhanced crew security protocols required')
    elif s.get('pol_risk') == 'caution':
        items.append('Political / security caution advisory in effect')
    if s.get('arpt_sec') == 'poor':
        items.append('Airport security / handling environment poor — enhanced coordination required')
    elif s.get('arpt_sec') == 'uncertain':
        items.append('Airport security / handling reliability uncertain')
    if s.get('st_oversight') == 'no':
        items.append('State oversight inadequate or unrecognised — OM compliance check required')
    elif s.get('st_oversight') == 'partial':
        items.append('Partial state oversight concern noted')

    if s.get('alt') == 'no':
        items.append('No adequate alternate within planning range')
    elif s.get('alt') == 'limited':
        items.append('Limited alternate options within planning range')
    if s.get('lvp') == 'frequent' and not s.get('alt_lvp') and s.get('alt') != 'no':
        items.append('Alternate low-visibility capability not confirmed despite destination LVP exposure')
    elif s.get('alt_lvp'):
        items.append(f"Alternate low-visibility capability confirmed: {s.get('alt_cat', 'confirmed')}")
    if s.get('fuel') == 'poor':
        items.append('Fuel / ground handling reliability poor — protected arrangement recommended')
    elif s.get('fuel') == 'uncertain':
        items.append('Fuel / ground handling reliability uncertain — verify before departure day')
    if not s.get('crew_rec'):
        items.append('No crew recency at this aerodrome within 12 months')

    return _dedupe_keep_order(items, limit=10)


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
        if ra_drivers:
            lines.append("Key Drivers:")
            for d in ra_drivers[:4]:
                lines.append(f"  - {d}")
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

        # ── TAB 1: MEYDAN ──────────────────────────────────────────────────
        with tab1:
            # ── ICAO SELECTION ──
            col_icao, col_btn = st.columns([2, 1])
            with col_icao:
                icao_e = st.text_input("ICAO Kodu", max_chars=4, placeholder="LTFM", key="ei").upper().strip()
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                load_btn = st.button("📂 Yükle", use_container_width=True)

            if load_btn and icao_e:
                ap_data = airports.get(icao_e, {})
                # Load summary: prefer ra_briefing_items, else merge sections
                if ap_data.get('ra_briefing_items'):
                    loaded_summary = "\n".join(ap_data['ra_briefing_items'])
                else:
                    parts = [ap_data.get('section1',''), ap_data.get('section2',''), ap_data.get('section3','')]
                    loaded_summary = "\n".join(p for p in parts if p and p.upper() != 'N/A')
                st.session_state["edit_name"]    = ap_data.get("name", "")
                st.session_state["edit_cat"]     = ap_data.get("category", "A")
                st.session_state["edit_summary"] = loaded_summary
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
                            "name": name_e,
                            "category": cat_e,
                            "section1": summary_e,
                            "section2": "",
                            "section3": "",
                            "ra_briefing_items": lines,
                        })
                        if ok:
                            st.success(f"✔ {icao_e} kaydedildi!")
                            st.cache_data.clear()
                            airports, risks = load_db()
                    else:
                        st.warning("ICAO girin.")

            # ══════════════════════════════════════════════════════════════
            # OPTION 2 — RISK ASSESSMENT TOOL
            # ══════════════════════════════════════════════════════════════
            else:
                if not icao_e:
                    st.info("ℹ Enter the ICAO code above and click Load.")
                else:
                    assessed_by = st.text_input("Assessment completed by", key="ra_by")

                    st.markdown("---")
                    st.markdown('<div class="ra-block"><h4>🏛 Block 1 — Aerodrome Classification & Authorization</h4></div>', unsafe_allow_html=True)
                    ra_cat = st.selectbox("Aerodrome category", ["A", "B", "C"], key="ra_cat",
                                          help="CAT C automatically drives HIGH risk.")
                    c1, c2 = st.columns(2)
                    ra_sp_desig = c1.checkbox("Special aerodrome designation applies", key="ra_spd")
                    ra_sp_crew = c2.checkbox("Special crew qualification required", key="ra_spc")
                    ra_sp_approval = st.checkbox("Special operator approval required", key="ra_spa")

                    st.markdown('<div class="ra-block"><h4>📐 Block 2 — Approach, Navigation & Terrain Awareness</h4></div>', unsafe_allow_html=True)
                    st.caption("Enter runway designators first; approach capability is derived from the runway selections.")
                    if 'ra_rwy_sets' not in st.session_state:
                        st.session_state['ra_rwy_sets'] = 1
                    rwy_inputs_all = []
                    for set_i in range(st.session_state['ra_rwy_sets']):
                        rc4 = st.columns(4)
                        for j in range(4):
                            v = rc4[j].text_input(
                                f"RWY {set_i * 4 + j + 1}", max_chars=4,
                                placeholder=["03L", "03R", "21L", "21R"][j] if set_i == 0 else f"RWY{set_i * 4 + j + 1}",
                                key=f"ra_rwy_{set_i}_{j}"
                            )
                            rwy_inputs_all.append(v.upper().strip())
                    if st.button("➕ Add four more runway fields", key="ra_add_rwy"):
                        st.session_state['ra_rwy_sets'] += 1
                        st.rerun()
                    active_runways = [r for r in rwy_inputs_all if r]

                    rwy_approaches = {}
                    if active_runways:
                        st.caption("Runway approach capability")
                        for rwy in active_runways:
                            types = st.multiselect(
                                f"RWY {rwy} — published approach types",
                                ["Precision CAT III", "Precision CAT II", "ILS", "GLS", "RNP AR", "RNP", "Offset Precision", "Non-Precision", "Offset Non-Precision"],
                                key=f"ra_app_{rwy}"
                            )
                            rwy_approaches[rwy] = types

                    precision_types = {"Precision CAT III", "Precision CAT II", "ILS", "GLS", "RNP AR", "RNP", "Offset Precision"}
                    derived_prec = any(t in precision_types for vals in rwy_approaches.values() for t in vals)
                    if active_runways:
                        st.info(f"Derived precision capability: {'YES' if derived_prec else 'NO'}")

                    ra_angle = st.selectbox(
                        "Approach geometry",
                        ["Normal (< 3.9°)", "Elevated (3.9°–4.49°)", "Steep (≥ 4.5°)"],
                        key="ra_angle"
                    )

                    st.caption("Minimum Safe Altitude (MSA) / terrain awareness")
                    msa_col1, msa_col2 = st.columns([1, 2])
                    ra_msa_ft = msa_col1.number_input("Highest MSA within TMA (ft)", min_value=0, max_value=30000,
                                                      step=100, value=0, key="ra_msa_ft")
                    ra_msa_sector = msa_col2.selectbox("MSA sector", ["All Sectors", "N", "NE", "E", "SE", "S", "SW", "W", "NW"], key="ra_msa_sector")
                    ra_high_da = st.checkbox("Terrain-limited minima (DA/DH ≥ 400 ft)", key="ra_hda", disabled=(not derived_prec))
                    if ra_high_da and active_runways:
                        st.multiselect("↳ Affected runway(s)", active_runways, key="ra_hda_rwys")

                    c3, c4 = st.columns(2)
                    ra_offset_mode = c3.selectbox(
                        "Offset approach type",
                        ["None", "Offset non-precision", "Offset precision"],
                        key="ra_offset_mode"
                    )
                    ra_ma_complexity = c4.selectbox(
                        "Missed approach complexity",
                        ["Standard", "Above standard", "Special procedure required"],
                        key="ra_ma_complexity"
                    )
                    ra_oei_ma = st.checkbox("Engine-out go-around requires dedicated briefing", key="ra_oema")
                    ra_gnss_outage = st.checkbox(
                        "GNSS outage / GPS NOTAM active or expected",
                        key="ra_gnss_outage",
                        help="Use this when an outage is expected to affect GLS / RNP availability."
                    )

                    if ra_gnss_outage and active_runways:
                        gnss_dep = {"GLS", "RNP AR", "RNP"}
                        gnss_affected = [rwy for rwy, types in rwy_approaches.items() if any(t in gnss_dep for t in types)]
                        st.warning(
                            f"GNSS outage selected — affected runways: {', '.join(gnss_affected)}"
                            if gnss_affected else
                            "GNSS outage selected, but no GNSS-dependent approach has been chosen in the runway list."
                        )

                    st.markdown('<div class="ra-block"><h4>🛬 Block 3 — Runway & Ground Environment</h4></div>', unsafe_allow_html=True)
                    ra_rwy_w = st.selectbox("Runway width", ["≥ 45 m", "30–44 m", "< 30 m"], key="ra_rwyw")
                    c5, c6 = st.columns(2)
                    ra_rwy_margin = c5.selectbox("Runway length margin", ["Adequate", "Marginal", "Critical"], key="ra_rwy_margin")
                    ra_runway_characteristics = c6.selectbox(
                        "Runway characteristics",
                        ["None", "Slope", "Displaced threshold", "Complex combination"],
                        key="ra_runway_char"
                    )
                    c7, c8 = st.columns(2)
                    ra_taxi_complex = c7.checkbox("Taxi routing complex / hot spots present", key="ra_taxi")
                    ra_rwy_crossing = c8.selectbox("Runway crossing requirement", ["No", "After landing", "Before departure", "Both"], key="ra_rwxing")

                    st.markdown('<div class="ra-block"><h4>⚡ Block 4 — Departure & OEI Risk</h4></div>', unsafe_allow_html=True)
                    c9, c10 = st.columns(2)
                    ra_oei_sid = c9.checkbox("Special OEI SID required", key="ra_oisid")
                    ra_perf_lim = c10.checkbox("Performance-limited departure likely", key="ra_plim")
                    c11, c12 = st.columns(2)
                    ra_oei_gradient = c11.selectbox("OEI climb gradient", ["Standard", "Demanding", "Critical"], key="ra_oei_gradient")
                    ra_weight_restriction = c12.checkbox("Weight restriction likely", key="ra_weight_restriction")

                    st.markdown('<div class="ra-block"><h4>🌤 Block 5 — Weather & ATC Environment</h4></div>', unsafe_allow_html=True)
                    ra_lvp = st.selectbox("LVP / fog / low ceiling exposure", ["Rare / not significant", "Occasional", "Frequent"], key="ra_lvp")
                    c13, c14 = st.columns(2)
                    ra_xw_risk = c13.checkbox("Crosswind / windshear / contamination exposure significant", key="ra_xw")
                    ra_terr_hh = c14.checkbox("Mountain / terrain / hot-high environment significant", key="ra_thh")
                    c15, c16 = st.columns(2)
                    ra_atc = c15.selectbox("ATC / slot / sequencing complexity", ["Low / normal", "Moderate", "Significant"], key="ra_atc")
                    ra_mil_traff = c16.checkbox("Military / mixed traffic or non-standard phraseology", key="ra_mil")
                    ra_gnss_risk = st.selectbox(
                        "Regional GNSS resilience",
                        ["No known risk", "NOTAMs / advisories active", "Active spoofing / jamming reported"],
                        key="ra_gnss"
                    )

                    st.markdown('<div class="ra-block"><h4>🔐 Block 6 — Security, Alternate & Operational Resilience</h4></div>', unsafe_allow_html=True)
                    ra_pol_risk = st.selectbox("Political / security risk", ["No significant concern", "Caution advisory in effect", "High risk"], key="ra_pol")
                    c17, c18 = st.columns(2)
                    ra_arpt_sec = c17.selectbox("Airport security / handling reliability", ["Adequate / reliable", "Uncertain / inconsistent", "Poor / inadequate"], key="ra_sec")
                    ra_st_oversight = c18.selectbox("State oversight / compliance confidence", ["Acceptable (EASA or equivalent)", "Partial — concerns noted", "No / inadequate / unrecognised"], key="ra_usoap")
                    ra_alt = st.selectbox("Adequate alternate within planning range", ["Yes — available and suitable", "Limited options", "No adequate alternate"], key="ra_alt")
                    ra_alt_lvp = False
                    ra_alt_cat = None
                    if ra_alt != "No adequate alternate":
                        ra_alt_lvp = st.checkbox("Alternate has confirmed low-visibility capability", key="ra_alt_lvp")
                        if ra_alt_lvp:
                            ra_alt_cat = st.radio("Alternate LVP category", ["CAT II", "CAT III"], horizontal=True, key="ra_alt_cat")
                    ra_fuel = st.selectbox("Fuel / ground handling reliability", ["Reliable and verified", "Uncertain / variable", "Poor / known concerns"], key="ra_fuel")
                    ra_crew_rec = st.radio("Crew operated at this aerodrome within the last 12 months", ["Yes", "No"], horizontal=True, key="ra_crec")

                    st.markdown("---")

                    if st.button("🎯 Calculate Risk", use_container_width=True, type="primary", key="ra_calc"):
                        angle_map = {
                            "Normal (< 3.9°)": "normal",
                            "Elevated (3.9°–4.49°)": "moderate",
                            "Steep (≥ 4.5°)": "steep",
                        }
                        lvp_map = {"Rare / not significant": "no", "Occasional": "sometimes", "Frequent": "frequent"}
                        atc_map = {"Low / normal": "no", "Moderate": "moderate", "Significant": "significant"}
                        pol_map = {"No significant concern": "no", "Caution advisory in effect": "caution", "High risk": "high"}
                        sec_map = {"Adequate / reliable": "good", "Uncertain / inconsistent": "uncertain", "Poor / inadequate": "poor"}
                        ov_map = {"Acceptable (EASA or equivalent)": "yes", "Partial — concerns noted": "partial", "No / inadequate / unrecognised": "no"}
                        alt_map = {"Yes — available and suitable": "yes", "Limited options": "limited", "No adequate alternate": "no"}
                        fuel_map = {"Reliable and verified": "reliable", "Uncertain / variable": "uncertain", "Poor / known concerns": "poor"}
                        rwy_map = {"≥ 45 m": "wide", "30–44 m": "medium", "< 30 m": "narrow"}
                        crossing_map = {"No": "no", "After landing": "after_landing", "Before departure": "before_departure", "Both": "both"}
                        offset_map = {"None": "none", "Offset non-precision": "offset_non_precision", "Offset precision": "offset_precision"}
                        ma_map = {"Standard": "standard", "Above standard": "above_standard", "Special procedure required": "special_required"}
                        oei_grad_map = {"Standard": "standard", "Demanding": "demanding", "Critical": "critical"}
                        rwy_margin_map = {"Adequate": "adequate", "Marginal": "marginal", "Critical": "critical"}
                        runway_char_map = {"None": "none", "Slope": "slope", "Displaced threshold": "displaced_threshold", "Complex combination": "complex_combination"}

                        survey = {
                            'cat': ra_cat,
                            'sp_desig': ra_sp_desig,
                            'sp_crew': ra_sp_crew,
                            'sp_approval': ra_sp_approval,
                            'rwy_approaches': rwy_approaches,
                            'active_runways': active_runways,
                            'prec': derived_prec,
                            'angle': angle_map[ra_angle],
                            'msa_ft': ra_msa_ft,
                            'msa_sector': ra_msa_sector,
                            'high_da': ra_high_da if derived_prec else False,
                            'offset_mode': offset_map[ra_offset_mode],
                            'offset': offset_map[ra_offset_mode] != 'none',
                            'ma_complexity': ma_map[ra_ma_complexity],
                            'madem': ma_map[ra_ma_complexity] in ('above_standard', 'special_required'),
                            'oei_ma_brief': ra_oei_ma,
                            'gnss_outage': ra_gnss_outage,
                            'rwy_w': rwy_map[ra_rwy_w],
                            'rwy_margin': rwy_margin_map[ra_rwy_margin],
                            'rwy_marg': rwy_margin_map[ra_rwy_margin] in ('marginal', 'critical'),
                            'runway_characteristics': runway_char_map[ra_runway_characteristics],
                            'phys_comp': runway_char_map[ra_runway_characteristics] == 'complex_combination',
                            'taxi_complex': ra_taxi_complex,
                            'rwy_crossing': crossing_map[ra_rwy_crossing],
                            'oei_sid': ra_oei_sid,
                            'oei_gradient': oei_grad_map[ra_oei_gradient],
                            'oei_grad': oei_grad_map[ra_oei_gradient] in ('demanding', 'critical'),
                            'perf_lim': ra_perf_lim,
                            'weight_restriction': ra_weight_restriction,
                            'lvp': lvp_map[ra_lvp],
                            'xw_risk': ra_xw_risk,
                            'terr_hh': ra_terr_hh,
                            'atc': atc_map[ra_atc],
                            'mil_traff': ra_mil_traff,
                            'gnss_risk': {"No known risk": "no", "NOTAMs / advisories active": "notam", "Active spoofing / jamming reported": "active"}[ra_gnss_risk],
                            'pol_risk': pol_map[ra_pol_risk],
                            'arpt_sec': sec_map[ra_arpt_sec],
                            'st_oversight': ov_map[ra_st_oversight],
                            'alt': alt_map[ra_alt],
                            'alt_lvp': ra_alt_lvp,
                            'alt_cat': ra_alt_cat,
                            'fuel': fuel_map[ra_fuel],
                            'crew_rec': ra_crew_rec == "Yes",
                        }

                        result = calc_risk(survey)
                        summary = gen_summary_items(survey)
                        st.session_state['ra_result'] = result
                        st.session_state['ra_summary'] = summary
                        st.session_state['ra_survey'] = survey
                        st.session_state['ra_icao'] = icao_e

                    if st.session_state.get('ra_result') and st.session_state.get('ra_icao') == icao_e:
                        result = st.session_state['ra_result']
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

                        if result['drivers']:
                            with st.expander("🔍 Key Risk Drivers", expanded=True):
                                for d in result['drivers']:
                                    st.markdown(f"**▶** {d}")

                        if summary:
                            with st.expander("📄 Operational Considerations (PDF output)", expanded=True):
                                for item in summary:
                                    st.markdown(f"• {item}")

                        if result['actions']:
                            with st.expander("✅ Required Actions", expanded=True):
                                for i, a in enumerate(result['actions'], 1):
                                    st.markdown(f"**{i}.** {a}")

                        st.markdown("---")
                        if st.button("💾 Save Risk Assessment to Database", use_container_width=True, type="primary", key="ra_save"):
                            today_str = datetime.date.today().strftime("%Y-%m-%d")
                            due_str = (datetime.date.today().replace(year=datetime.date.today().year + 1)).strftime("%Y-%m-%d")
                            ok = update_airport(icao_e, {
                                "name": name_e or airports.get(icao_e, {}).get("name", icao_e),
                                "category": ra_cat,
                                "section1": "\n".join(summary),
                                "section2": "",
                                "section3": "",
                                "ra_risk_level": result['risk'],
                                "ra_risk_score": result['score'],
                                "ra_risk_basis": result['basis'],
                                "ra_key_drivers": result['drivers'],
                                "ra_actions": result['actions'],
                                "ra_briefing_items": summary,
                                "ra_assessment_date": today_str,
                                "ra_reassessment_due": due_str,
                                "ra_assessed_by": assessed_by or "Admin",
                            })
                            if ok:
                                st.success(f"✔ {icao_e} risk assessment saved. Reassessment due: {due_str}")
                                st.cache_data.clear()
                                airports, risks = load_db()
                                keys_to_clear = [k for k in st.session_state if k.startswith('ra_') or k in ('edit_name', 'edit_cat', 'edit_summary', 'ei')]
                                for k in keys_to_clear:
                                    del st.session_state[k]
                                st.session_state['ra_rwy_sets'] = 1
                                st.rerun()
                            else:
                                st.error("Save failed.")
            st.divider()
            if st.button("🔄 Veritabanını Yenile", use_container_width=True):
                st.cache_data.clear(); st.rerun()

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

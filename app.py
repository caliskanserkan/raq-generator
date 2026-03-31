import streamlit as st
import datetime, io, os
from utils import load_db, update_airport
from czib_check import check_czib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

st.set_page_config(
    page_title="RAQ Form Generator - REC Havacilik",
    page_icon="✈",
    layout="centered",
    initial_sidebar_state="expanded",
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
.info-card { background-color:#2C3E50; padding:14px 20px; border-radius:8px; margin:10px 0; }
.info-card h3 { color:white; margin:0 0 4px 0; font-size:15px; }
.info-card p  { color:#AEB6BF; margin:0; font-size:12px; }
.risk-box { background-color:#FADBD8; border:2px solid #C0392B; border-radius:6px; padding:10px 14px; margin:6px 0; }
.risk-box p { color:#C0392B; font-weight:bold; margin:0; font-size:12px; }
.airport-label { background-color:#1A252F; color:white; padding:6px 12px; border-radius:6px;
                 font-size:13px; font-weight:bold; margin-bottom:4px; display:inline-block; }
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
for _fn, _ff in [("RAQN", "DejaVuSans.ttf"), ("RAQB", "DejaVuSans-Bold.ttf"), ("RAQI", "DejaVuSans-Oblique.ttf")]:
    if _fn not in _reg:
        _fp = _find_font(_ff)
        if _fp:
            pdfmetrics.registerFont(TTFont(_fn, _fp))

_dv = "RAQN" in pdfmetrics.getRegisteredFontNames()
FN = "RAQN" if _dv else "Helvetica"
FB = "RAQB" if _dv else "Helvetica-Bold"
FI = "RAQI" if _dv else "Helvetica-Oblique"


# ── Single Page PDF Generator ──────────────────────────────────────────────────
def generate_pdf_page(cv, frm, airport, risk, fi, page_label=""):
    """Draws one RAQ form page onto the given canvas (cv). Does NOT save."""
    czib_text = fi.get("czib", "")
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    RED   = colors.HexColor("#C0392B"); DARK  = colors.HexColor("#111111")
    MID   = colors.HexColor("#1A3A5C"); STEEL = colors.HexColor("#2E5F8A")
    LIGHT = colors.white;               ALT   = colors.white
    INPB  = colors.white;               RISKB = colors.white
    BORD  = colors.HexColor("#888888"); W_    = colors.white

    PW, PH = A4; ML = 15 * mm; W = PW - 2 * ML
    y = PH - 12 * mm

    def bx(x, yt, w2, h, fill=LIGHT, stroke=BORD, sw=0.5):
        cv.setLineWidth(sw); cv.setFillColor(fill); cv.setStrokeColor(stroke)
        cv.rect(x, yt - h, w2, h, fill=1, stroke=1)

    def tx(text, x, yt, font=FN, size=9, color=DARK, align="left", width=0):
        cv.setFillColor(color); cv.setFont(font, size)
        if align == "center" and width:
            cv.drawCentredString(x + width / 2, yt, str(text))
        elif align == "right" and width:
            cv.drawRightString(x + width, yt, str(text))
        else:
            cv.drawString(x, yt, str(text))

    def wl(text, font, size, max_w):
        cv.setFont(font, size); words = text.split(); lines = []; line = ""
        for w2 in words:
            test = (line + " " + w2).strip()
            if cv.stringWidth(test, font, size) <= max_w:
                line = test
            else:
                if line: lines.append(line)
                line = w2
        if line: lines.append(line)
        return lines

    def shdr(yt, lbl, h=14):
        bx(ML, yt, W, h, fill=MID, stroke=MID, sw=0.8); tx(lbl, ML + 6, yt - h + 4, FB, 8.5, W_); return yt - h

    def sbhdr(yt, lbl, h=12):
        bx(ML, yt, W, h, fill=STEEL, stroke=STEEL, sw=0.8); tx(lbl, ML + 4, yt - h + 3, FB, 8, W_); return yt - h

    def tblk(yt, text, bg=LIGHT, pad=6):
        lines = text.split("\n") if text else ["N/A"]
        lh = 11; h = max(len(lines) * lh + pad * 2, 20)
        bx(ML, yt, W, h, fill=bg, stroke=BORD)
        ty2 = yt - pad - 8
        for ln in lines:
            sub = wl(ln, FN, 8, W - pad * 2)
            for s in sub: tx(s, ML + pad, ty2, FN, 8); ty2 -= lh
        return yt - h

    def cbrow(yt, name, label, bg=LIGHT, h=16, sz=10):
        bx(ML, yt, W, h, fill=bg, stroke=BORD); cby = yt - h + (h - sz) / 2
        frm.checkbox(name=name, tooltip=label, x=ML + 6, y=cby, size=sz,
                     checked=False, buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
        tx(label, ML + 6 + sz + 6, yt - h / 2 - 3.5, FN, 9, DARK); return yt - h

    def chdrs(yt, cols, h=15):
        x = ML
        for lbl, w2 in cols: bx(x, yt, w2, h, fill=STEEL, stroke=BORD); tx(lbl, x, yt - h + 4, FB, 8.5, W_, "center", w2); x += w2
        return yt - h

    def cdata(yt, cols, h=21):
        x = ML
        for text, w2, font, size, color, align in cols: bx(x, yt, w2, h, fill=INPB, stroke=BORD); tx(text, x, yt - h + 5, font, size, color, align, w2); x += w2
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
    tx("ROUTE AND AERODROME QUALIFICATION TRAINING FORM", ML, y - 10, FI, 8, STEEL, "center", W); y -= 16

    y = shdr(y, "FLIGHT DETAILS")
    cw = [W * .18, W * .15, W * .335, W * .335]
    y = chdrs(y, [("Date", cw[0]), ("A/C Type", cw[1]), ("PIC", cw[2]), ("SIC", cw[3])])
    y = cdata(y, [(fi.get("date", ""), cw[0], FB, 9, DARK, "center"),
                  (fi.get("ac_type", "").upper(), cw[1], FB, 9, DARK, "center"),
                  (fi.get("pic", "").upper(), cw[2], FB, 9, DARK, "center"),
                  (fi.get("sic", "").upper(), cw[3], FB, 9, DARK, "center")]); y -= 3

    y = shdr(y, "AERODROME")
    cw2 = [W * .50, W * .25, W * .25]
    y = chdrs(y, [("Airport Name", cw2[0]), ("ICAO", cw2[1]), ("Category", cw2[2])])
    ah = 22; x = ML
    for text, w2, font, size, color in [(airport.get("name", "").upper(), cw2[0], FB, 9, DARK),
                                         (airport.get("icao", "").upper(), cw2[1], FB, 9, DARK),
                                         (airport.get("category", "").upper(), cw2[2], FB, 13, RED)]:
        bx(x, y, w2, ah, fill=LIGHT, stroke=BORD); tx(text, x, y - ah + 5, font, size, color, "center", w2); x += w2
    y -= ah + 3

    y = shdr(y, "FAMILIARIZATION CONDUCTED BY")
    hw = W / 2; y = chdrs(y, [("Self Briefing", hw), ("Local Authority", hw)])
    fh = 20; bx(ML, y, hw, fh, fill=LIGHT, stroke=BORD); bx(ML + hw, y, hw, fh, fill=LIGHT, stroke=BORD)
    csz = 12; cby = y - fh + (fh - csz) / 2
    icao_key = airport.get("icao", "X")
    frm.checkbox(name=f"fam_self_{icao_key}",  tooltip="Self Briefing",    x=ML + hw / 2 - csz / 2,      y=cby, size=csz, checked=False, buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
    frm.checkbox(name=f"fam_local_{icao_key}", tooltip="Local Authority", x=ML + hw + hw / 2 - csz / 2, y=cby, size=csz, checked=False, buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
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
        y = cbrow(y, nm, lbl, bg=LIGHT if i % 2 == 0 else ALT)
    y -= 3

    y = shdr(y, "SPECIAL ITEMS BRIEFED DUE TO AERODROME CATEGORY")
    for i, (nm, lbl) in enumerate([
        (f"sp_1_{icao_key}", "(1) Non-standard approach aids or approach patterns"),
        (f"sp_2_{icao_key}", "(2) Unusual local weather conditions"),
        (f"sp_3_{icao_key}", "(3) Unusual characteristics or performance limitations"),
        (f"sp_4_{icao_key}", "(4) Other relevant considerations: obstructions, physical layout, lighting etc."),
        (f"sp_5_{icao_key}", "(5) Category C aerodromes: additional considerations for approach/landing/take-off."),
    ]):
        y = cbrow(y, nm, lbl, bg=LIGHT if i % 2 == 0 else ALT)
    y -= 3

    y = shdr(y, "SPECIAL REMARKS  -  PPS BRIEFING  (AUTO FROM DATABASE)")
    for lbl, key in [
        ("SECTION 1  -  Traffic / ATC / Taxi / Runway Ops", "section1"),
        ("SECTION 2  -  Meteorology / Wind",                "section2"),
        ("SECTION 3  -  Security / Handling / Navigation",  "section3"),
    ]:
        y = sbhdr(y, lbl); y = tblk(y, airport.get(key, "N/A")); y -= 2
    y -= 3

    y = shdr(y, "AERODROME RISK SUMMARY  (AUTO - DATABASE)")
    rt = (
        f"RISK LEVEL: {risk['risk_level']}   |   CAT: {airport.get('category', '')}   |   {risk['ops_approval']}\n"
        f"MITIGATION: {risk['mitigation']}"
        if risk else "Risk verisi bulunamadi."
    )
    y = tblk(y, rt, bg=RISKB, pad=8); y -= 3

    if czib_text:
        from reportlab.lib import colors as cl
        cz_h = 22
        bx(ML, y, W, cz_h, fill=cl.HexColor("#FADBD8"), stroke=cl.HexColor("#C0392B"), sw=1.5)
        tx(f"  ⚠  {czib_text}", ML + 6, y - cz_h + 6, FB, 9, cl.HexColor("#C0392B"))
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
        (fi.get("pic", "").upper(), cw3[1], FB, 9, DARK, "center"),
        (today, cw3[2], FN, 8, STEEL, "right"),
    ]:
        bx(x, y, w2, 20, fill=LIGHT, stroke=BORD); tx(text, x, y - 15, font, size, color, align, w2); x += w2


# ── Booklet PDF Generator ──────────────────────────────────────────────────────
def generate_booklet_pdf(airport_list, airports_db, risks_db, fi):
    """Generates a multi-page booklet PDF for all provided airports."""
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    cv = C.Canvas(buf, pagesize=A4)
    cv.setTitle(f"RAQ-BOOKLET-{fi.get('date', '')}")
    frm = cv.acroForm

    for idx, (label, icao) in enumerate(airport_list):
        airport = airports_db[icao]
        risk = risks_db.get(icao)

        # Get CZIB for this airport
        try:
            czib_hit, czib_text = check_czib(icao)
        except Exception:
            czib_text = ""

        fi_page = {**fi, "czib": czib_text}
        generate_pdf_page(cv, frm, airport, risk, fi_page, page_label=label)

        # Add page (showPage) after each airport except the logic handles it
        cv.showPage()

    cv.save()
    buf.seek(0)
    return buf.getvalue()


# ── UI ─────────────────────────────────────────────────────────────────────────
airports, risks = load_db()

with st.sidebar:
    st.markdown("### ⚙ Admin Panel")
    pw = st.text_input("Şifre", type="password", key="admin_pw")
    admin_ok = pw == st.secrets.get("admin", {}).get("password", "rec2024")

    if admin_ok and pw:
        st.success("✔ Giris basarili")
        st.divider()
        st.markdown("**Meydan Düzenle / Ekle**")
        icao_e = st.text_input("ICAO", max_chars=4, key="ei").upper().strip()
        ap_e   = airports.get(icao_e, {})
        if icao_e and ap_e:
            st.caption(f"Mevcut: {ap_e['name']}")
        name_e = st.text_input("Meydan Adı",  value=ap_e.get("name", ""),     key="en")
        cat_e  = st.selectbox("Kategori", ["A", "B", "C"],
                               index=["A", "B", "C"].index(ap_e.get("category", "A"))
                               if ap_e.get("category", "A") in ["A", "B", "C"] else 0)
        s1_e   = st.text_area("Section 1",    value=ap_e.get("section1", ""), height=100, key="e1")
        s2_e   = st.text_area("Section 2",    value=ap_e.get("section2", ""), height=80,  key="e2")
        s3_e   = st.text_area("Section 3",    value=ap_e.get("section3", ""), height=80,  key="e3")

        if st.button("💾 Kaydet", use_container_width=True):
            if icao_e:
                ok = update_airport(icao_e, {"name": name_e, "category": cat_e,
                                             "section1": s1_e, "section2": s2_e, "section3": s3_e})
                if ok:
                    st.success(f"✔ {icao_e} kaydedildi!")
                    st.cache_data.clear()
            else:
                st.warning("ICAO girin.")

        st.divider()
        if st.button("🔄 Veritabanını Yenile", use_container_width=True):
            st.cache_data.clear(); st.rerun()

# ── Main Header ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:#1A3A5C;padding:18px 24px;border-radius:8px;margin-bottom:20px">
<h1 style="color:white;margin:0;font-size:22px">✈ REC HAVACILIK – RAQ Form Generator</h1>
<p style="color:#AED6F1;margin:4px 0 0 0;font-size:12px">Route and Aerodrome Qualification Training Form</p>
</div>
""", unsafe_allow_html=True)

# ── Airport Inputs ─────────────────────────────────────────────────────────────
st.subheader("🛫 Meydan Bilgileri")
st.caption("En az 1, en fazla 4 meydan girebilirsiniz. Boş bırakılan meydanlar PDF'e dahil edilmez.")

airport_fields = [
    ("DEPT",     "Kalkış Meydanı",          "LTBA"),
    ("DEPT ALT", "Kalkış Alternatif",        "LTFM"),
    ("DEST",     "Varış Meydanı",            "EHAM"),
    ("DEST ALT", "Varış Alternatif",         "EGLL"),
]

icao_inputs = {}
col_left, col_right = st.columns(2)

for i, (label, desc, placeholder) in enumerate(airport_fields):
    col = col_left if i % 2 == 0 else col_right
    with col:
        st.markdown(f'<span class="airport-label">✈ {label}</span>', unsafe_allow_html=True)
        icao_val = st.text_input(
            desc,
            max_chars=4,
            placeholder=placeholder,
            key=f"icao_{label}",
            label_visibility="collapsed",
        ).upper().strip()
        icao_inputs[label] = icao_val

        if icao_val:
            if icao_val in airports:
                ap = airports[icao_val]
                rk = risks.get(icao_val)
                st.markdown(
                    f'<div class="info-card" style="padding:8px 14px;margin:4px 0">'
                    f'<h3 style="font-size:13px">✔ {ap["name"]}</h3>'
                    f'<p>Kategori: {ap["category"]}</p></div>',
                    unsafe_allow_html=True,
                )
                if rk:
                    st.markdown(
                        f'<div class="risk-box"><p>RISK: {rk["risk_level"]}  |  {rk["ops_approval"]}</p></div>',
                        unsafe_allow_html=True,
                    )
            elif len(icao_val) == 4:
                st.error(f"❌ {icao_val} veritabanında bulunamadı.")

st.divider()

# ── Flight Info ────────────────────────────────────────────────────────────────
st.subheader("✈ Uçuş Bilgileri")
col1, col2 = st.columns(2)
with col1:
    pic  = st.text_input("PIC (Ad Soyad / Kod)")
    date = st.date_input("Uçuş Tarihi", value=datetime.date.today())
with col2:
    sic  = st.text_input("SIC (Ad Soyad / Kod)")
    ac   = st.text_input("A/C Type", value="TC-REC")

st.divider()

# ── Generate Button ────────────────────────────────────────────────────────────
# Collect valid airports
valid_airports = []
for label, icao_val in icao_inputs.items():
    if icao_val and icao_val in airports:
        valid_airports.append((label, icao_val))

if valid_airports:
    st.info(f"📋 **{len(valid_airports)} meydan** için PDF oluşturulacak: " +
            " → ".join([f"**{lbl}** ({icao})" for lbl, icao in valid_airports]))
else:
    st.warning("En az bir geçerli meydan girin.")

if st.button("📄  RAQ BOOKLET PDF OLUŞTUR", use_container_width=True, type="primary"):
    if not valid_airports:
        st.error("En az bir geçerli ICAO kodu girin.")
    elif not pic:
        st.error("PIC bilgisini girin.")
    else:
        with st.spinner(f"⏳ {len(valid_airports)} sayfalık booklet oluşturuluyor..."):
            try:
                # Warn for any CZIB hits
                for lbl, icao_val in valid_airports:
                    czib_hit, czib_text = check_czib(icao_val)
                    if czib_hit:
                        st.warning(f"⚠ {lbl} ({icao_val}): {czib_text}")

                pdf = generate_booklet_pdf(
                    valid_airports,
                    airports,
                    risks,
                    {
                        "date":    date.strftime("%Y-%m-%d"),
                        "ac_type": ac,
                        "pic":     pic,
                        "sic":     sic,
                    },
                )

                icao_str = "-".join([icao for _, icao in valid_airports])
                fname = f"RAQ_BOOKLET_{icao_str}_{date.strftime('%Y-%m-%d')}.pdf"
                st.success(f"✔ {len(valid_airports)} sayfalık booklet hazır!")
                st.download_button(
                    f"⬇  PDF Booklet İndir ({len(valid_airports)} sayfa)",
                    pdf, fname, "application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© REC HAVACILIK  -  AMC1 ORO.FC.105 b(2);c")

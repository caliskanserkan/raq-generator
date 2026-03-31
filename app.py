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

# ── PDF Generator ──────────────────────────────────────────────────────────────
def generate_pdf(airport, risk, fi):
    czib_text = fi.get("czib", "")
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    RED   = colors.HexColor("#C0392B"); DARK  = colors.HexColor("#1A252F")
    MID   = colors.HexColor("#2C3E50"); STEEL = colors.HexColor("#4A6274")
    LIGHT = colors.HexColor("#FDFEFE"); ALT   = colors.HexColor("#F2F3F4")
    INPB  = colors.HexColor("#EBF5FB"); RISKB = colors.HexColor("#FADBD8")
    BORD  = colors.HexColor("#AEB6BF"); W_    = colors.white

    PW, PH = A4; ML = 15 * mm; W = PW - 2 * ML
    buf = io.BytesIO(); cv = C.Canvas(buf, pagesize=A4)
    cv.setTitle(f"RAQ-{airport.get('icao','')}-{fi.get('date','')}"); frm = cv.acroForm; y = PH - 12 * mm

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
        bx(ML, yt, W, h, fill=MID, stroke=MID); tx(lbl, ML + 6, yt - h + 4, FB, 8.5, W_); return yt - h

    def sbhdr(yt, lbl, h=12):
        bx(ML, yt, W, h, fill=STEEL, stroke=STEEL); tx(lbl, ML + 4, yt - h + 3, FB, 8, W_); return yt - h

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

    hh = 26
    bx(ML, y, W * .72, hh, fill=RED, stroke=DARK, sw=1); bx(ML + W * .72, y, W * .28, hh, fill=MID, stroke=DARK, sw=1)
    tx("REC HAVACILIK  ✈  YOL VE MEYDAN YETERLİLİK EĞİTİM FORMU", ML + 8, y - hh + 8, FB, 10, W_)
    tx("FOP-FRM02 | Rev 0 | 2023-10-31", ML + W * .72 + 4, y - hh + 8, FB, 7, W_); y -= hh
    bx(ML, y, W, 13, fill=LIGHT, stroke=BORD)
    tx("ROUTE AND AERODROME QUALIFICATION TRAINING FORM", ML, y - 10, FI, 8, STEEL, "center", W); y -= 16

    y = shdr(y, "FLIGHT DETAILS")
    cw = [W * .18, W * .15, W * .335, W * .335]
    y = chdrs(y, [("Date", cw[0]), ("A/C Type", cw[1]), ("PIC", cw[2]), ("SIC", cw[3])])
    y = cdata(y, [(fi.get("date", ""), cw[0], FB, 9, DARK, "center"),
                  (fi.get("ac_type", ""), cw[1], FB, 9, DARK, "center"),
                  (fi.get("pic", ""), cw[2], FB, 9, DARK, "center"),
                  (fi.get("sic", ""), cw[3], FB, 9, DARK, "center")]); y -= 3

    y = shdr(y, "AERODROME")
    cw2 = [W * .50, W * .25, W * .25]
    y = chdrs(y, [("Airport Name", cw2[0]), ("ICAO", cw2[1]), ("Category", cw2[2])])
    ah = 22; x = ML
    for text, w2, font, size, color in [(airport.get("name", ""), cw2[0], FB, 9, DARK),
                                         (airport.get("icao", ""), cw2[1], FB, 9, DARK),
                                         (airport.get("category", ""), cw2[2], FB, 13, RED)]:
        bx(x, y, w2, ah, fill=LIGHT, stroke=BORD); tx(text, x, y - ah + 5, font, size, color, "center", w2); x += w2
    y -= ah + 3

    y = shdr(y, "FAMILIARIZATION CONDUCTED BY")
    hw = W / 2; y = chdrs(y, [("Self Briefing", hw), ("Local Authority", hw)])
    fh = 20; bx(ML, y, hw, fh, fill=LIGHT, stroke=BORD); bx(ML + hw, y, hw, fh, fill=LIGHT, stroke=BORD)
    csz = 12; cby = y - fh + (fh - csz) / 2
    frm.checkbox(name="fam_self",  tooltip="Self Briefing",    x=ML + hw / 2 - csz / 2,      y=cby, size=csz, checked=False, buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
    frm.checkbox(name="fam_local", tooltip="Local Authority", x=ML + hw + hw / 2 - csz / 2, y=cby, size=csz, checked=False, buttonStyle="check", borderColor=DARK, fillColor=W_, textColor=RED, forceBorder=True)
    y -= fh + 3

    y = shdr(y, "FOLLOWING ITEMS WERE BRIEFED AND FAMILIARIZED FOR THE ROUTE FLOWN")
    for i, (nm, lbl) in enumerate([
        ("cb_terrain",    "Terrain and Safe Altitudes"),
        ("cb_comms",      "Communication and ATC Facilities"),
        ("cb_sar",        "Search & Rescue Procedures"),
        ("cb_layout",     "Airport Layout"),
        ("cb_approach",   "Approach Aids"),
        ("cb_instrument", "Instrument Approach and Hold Procedures"),
        ("cb_minima",     "Operating Minima"),
    ]):
        y = cbrow(y, nm, lbl, bg=LIGHT if i % 2 == 0 else ALT)
    y -= 3

    y = shdr(y, "SPECIAL ITEMS BRIEFED DUE TO AERODROME CATEGORY")
    for i, (nm, lbl) in enumerate([
        ("sp_1", "(1) Non-standard approach aids or approach patterns"),
        ("sp_2", "(2) Unusual local weather conditions"),
        ("sp_3", "(3) Unusual characteristics or performance limitations"),
        ("sp_4", "(4) Other relevant considerations: obstructions, physical layout, lighting etc."),
        ("sp_5", "(5) Category C aerodromes: additional considerations for approach/landing/take-off."),
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
        (fi.get("pic", ""), cw3[1], FB, 9, DARK, "center"),
        (today, cw3[2], FN, 8, STEEL, "right"),
    ]:
        bx(x, y, w2, 20, fill=LIGHT, stroke=BORD); tx(text, x, y - 15, font, size, color, align, w2); x += w2

    cv.save(); buf.seek(0); return buf.getvalue()


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

st.markdown("""
<div style="background:#C0392B;padding:18px 24px;border-radius:8px;margin-bottom:20px">
<h1 style="color:white;margin:0;font-size:22px">✈ REC HAVACILIK – RAQ Form Generator</h1>
<p style="color:#FADBD8;margin:4px 0 0 0;font-size:12px">Route and Aerodrome Qualification Training Form</p>
</div>
""", unsafe_allow_html=True)

icao = st.text_input("ICAO Kodu", max_chars=4, placeholder="EHAM").upper().strip()

if icao:
    if icao in airports:
        ap = airports[icao]; rk = risks.get(icao)
        st.markdown(
            f'<div class="info-card"><h3>✔ {ap["name"]}</h3>'
            f'<p>ICAO: {ap["icao"]}   |   Kategori: {ap["category"]}   |   Guncelleme: {ap["updated"]}</p></div>',
            unsafe_allow_html=True,
        )
        if rk:
            st.markdown(
                f'<div class="risk-box"><p>RISK: {rk["risk_level"]}  |  {rk["ops_approval"]}</p></div>',
                unsafe_allow_html=True,
            )
    elif len(icao) == 4:
        st.error("Meydan veritabaninda bulunamadi.")

st.divider()
st.subheader("Ucus Bilgileri")
col1, col2 = st.columns(2)
with col1: pic  = st.text_input("PIC (Ad Soyad / Kod)"); date = st.date_input("Ucus Tarihi", value=datetime.date.today())
with col2: sic  = st.text_input("SIC (Ad Soyad / Kod)"); ac   = st.text_input("A/C Type", value="TC-REC")
st.divider()

if st.button("📄  RAQ FORM PDF OLUSTUR", use_container_width=True, type="primary"):
    if not icao or icao not in airports:
        st.error("Gecerli ICAO girin.")
    elif not pic:
        st.error("PIC bilgisini girin.")
    else:
        with st.spinner("PDF olusturuluyor..."):
            try:
                czib_hit, czib_text = check_czib(icao)
                if czib_hit:
                    st.warning(f"⚠ {czib_text}")
                pdf = generate_pdf(
                    airports[icao], risks.get(icao),
                    {"date": date.strftime("%Y-%m-%d"), "ac_type": ac,
                     "pic": pic, "sic": sic, "czib": czib_text},
                )
                fname = f"RAQ_{icao}_{date.strftime('%Y-%m-%d')}.pdf"
                st.success("✔ PDF hazir!")
                st.download_button("⬇  PDF Indir", pdf, fname, "application/pdf", use_container_width=True)
            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© REC HAVACILIK  -  AMC1 ORO.FC.105 b(2);c")

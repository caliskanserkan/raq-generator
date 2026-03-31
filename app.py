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
for _fn, _ff in [("RAQN", "DejaVuSans.ttf"),
                 ("RAQB", "DejaVuSans-Bold.ttf"),
                 ("RAQI", "DejaVuSans-Oblique.ttf")]:
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
    # Burada senin uzun RAQ form çizim mantığın vardı
    # Kutular, başlıklar, checkbox’lar, risk summary vs.
    # (Sen bana ilk gönderdiğinde bu fonksiyonun tamamı vardı)
    pass

# ── UI ─────────────────────────────────────────────────────────────────────────
airports, risks = load_db()

with st.sidebar:
    st.markdown("### ⚙ Admin Panel")
    pw = st.text_input("Şifre", type="password", key="admin_pw")
    admin_ok = pw == st.secrets.get("admin", {}).get("password", "rec2024")
    # ... Admin panel kodları ...

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
st.subheader("Ucus Bilgileri

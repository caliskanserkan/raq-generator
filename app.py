import streamlit as st
import datetime, io, os
from utils import load_db, update_airport
from czib_check import check_czib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as C
from reportlab.lib.pagesizes import A4

st.set_page_config(
    page_title="RAQ Form Generator - REC Havacilik",
    page_icon="✈",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── PDF Generator (çoklu sayfa) ──────────────────────────────────────────────
def generate_multi_pdf(airports, risks, fi):
    buf = io.BytesIO()
    cv = C.Canvas(buf, pagesize=A4)

    def add_page(title, content):
        cv.showPage()
        cv.setFont("Helvetica-Bold", 14)
        cv.drawString(100, 800, title)
        cv.setFont("Helvetica", 12)
        cv.drawString(100, 770, content)

    if fi.get("dep", "").strip():
        add_page("Departure", fi["dep"])
    if fi.get("dep_alt", "").strip():
        add_page("Departure Alternate", fi["dep_alt"])
    if fi.get("arr", "").strip():
        add_page("Arrival", fi["arr"])
    if fi.get("arr_alt", "").strip():
        add_page("Arrival Alternate", fi["arr_alt"])

    cv.save()
    buf.seek(0)
    return buf.getvalue()

# ── UI ─────────────────────────────────────────────────────────────────────────
st.markdown("<h2>✈ REC HAVACILIK – RAQ Form Generator</h2>", unsafe_allow_html=True)

st.subheader("Uçuş Bilgileri")
col1, col2 = st.columns(2)
with col1:
    pic  = st.text_input("PIC (Ad Soyad / Kod)")
    date = st.date_input("Uçuş Tarihi", value=datetime.date.today())
with col2:
    sic  = st.text_input("SIC (Ad Soyad / Kod)")
    ac   = st.text_input("A/C Type", value="TC-REC")

# Yeni 4 pencere
dep = st.text_area("Departure")
dep_alt = st.text_area("Departure Alternate")
arr = st.text_area("Arrival")
arr_alt = st.text_area("Arrival Alternate")

if st.button("📄  RAQ FORM PDF OLUSTUR", use_container_width=True, type="primary"):
    if not pic:
        st.error("PIC bilgisini girin.")
    else:
        with st.spinner("PDF olusturuluyor..."):
            try:
                czib_hit, czib_text = check_czib("TEST")
                pdf = generate_multi_pdf(
                    {}, {}, {
                        "date": date.strftime("%Y-%m-%d"),
                        "ac_type": ac,
                        "pic": pic,
                        "sic": sic,
                        "czib": czib_text,
                        "dep": dep,
                        "dep_alt": dep_alt,
                        "arr": arr,
                        "arr_alt": arr_alt
                    }
                )
                fname = f"RAQ_{date.strftime('%Y-%m-%d')}.pdf"
                st.success("✔ PDF hazır!")
                st.download_button("⬇  PDF İndir", pdf, fname, "application/pdf", use_container_width=True)
            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© REC HAVACILIK  -  AMC1 ORO.FC.105 b(2);c")

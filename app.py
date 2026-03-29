import streamlit as st
import datetime, io, os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

st.set_page_config(
    page_title="RAQ Form Generator - REC Havacilik",
    page_icon="✈",
    layout="centered"
)

st.markdown("""
<style>
.info-card { background-color:#2C3E50; padding:14px 20px; border-radius:8px; margin:10px 0; }
.info-card h3 { color:white; margin:0 0 4px 0; font-size:15px; }
.info-card p  { color:#AEB6BF; margin:0; font-size:12px; }
.risk-box { background-color:#FADBD8; border:2px solid #C0392B; border-radius:6px; padding:10px 14px; margin:6px 0; }
.risk-box p { color:#C0392B; font-weight:bold; margin:0; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ── Register fonts once ───────────────────────────────────────────────────────
# Find font directory — works both locally and on Streamlit Cloud
def _find_font(fname):
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), fname),
        os.path.join(os.getcwd(), fname),
        fname,
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

_registered = pdfmetrics.getRegisteredFontNames()
for _fn, _ff in [("RAQN","DejaVuSans.ttf"),("RAQB","DejaVuSans-Bold.ttf"),("RAQI","DejaVuSans-Oblique.ttf")]:
    if _fn not in _registered:
        _fp = _find_font(_ff)
        if _fp:
            pdfmetrics.registerFont(TTFont(_fn, _fp))

_use_dv = "RAQN" in pdfmetrics.getRegisteredFontNames()
FN = "RAQN" if _use_dv else "Helvetica"
FB = "RAQB" if _use_dv else "Helvetica-Bold"
FI = "RAQI" if _use_dv else "Helvetica-Oblique"

# ── Database ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_db():
    try:
        import openpyxl
        wb = openpyxl.load_workbook(
            next((p for p in [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.xlsx"),
            os.path.join(os.getcwd(), "database.xlsx"),
            "database.xlsx"] if os.path.exists(p)), "database.xlsx"), data_only=True)
        airports = {}
        for row in wb['AIRPORT_DB'].iter_rows(min_row=2, values_only=True):
            if row[0]:
                airports[str(row[0]).upper()] = {
                    "icao":     str(row[0]),
                    "name":     str(row[1]) if row[1] else str(row[0]),
                    "section1": str(row[2]) if row[2] else "",
                    "section2": str(row[3]) if row[3] else "",
                    "section3": str(row[4]) if row[4] else "",
                    "updated":  str(row[6])[:10] if row[6] else "",
                    "category": str(row[8]) if row[8] else "A",
                }
        risks = {}
        for row in wb['MATRIX_STORE'].iter_rows(min_row=2, values_only=True):
            if row[0]:
                s = [v for v in row[1:11]  if isinstance(v, (int, float))]
                l = [v for v in row[11:21] if isinstance(v, (int, float))]
                cat = str(row[27]) if row[27] else "A"
                mit = str(row[24]) if row[24] else ""
                if s and l:
                    sc = round(sum(sorted(s,reverse=True)[:3])/3 +
                               sum(sorted(l,reverse=True)[:3])/3 - 1)
                    if cat == "C": sc += 1
                    if sc <= 6:    rl,ops = "LOW","DISPATCH OK"
                    elif sc <= 9:  rl,ops = "MEDIUM","DISPATCH OK"
                    elif sc <= 12:
                        rl  = "HIGH"
                        ops = "OPS MANAGER APPROVAL REQUIRED" if cat=="C" else "CAPTAIN REVIEW / DISPATCH COORDINATION"
                    else:          rl,ops = "EXTREME","OPS MANAGER APPROVAL REQUIRED"
                else:
                    rl,ops = "N/A","N/A"
                risks[str(row[0]).upper()] = {
                    "risk_level":rl, "ops_approval":ops, "mitigation":mit}
        return airports, risks
    except Exception as e:
        st.error(f"DB Hatasi: {e}")
        return {}, {}

# ── PDF ───────────────────────────────────────────────────────────────────────
def generate_pdf(airport, risk, fi):
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    RED   = colors.HexColor("#C0392B")
    DARK  = colors.HexColor("#1A252F")
    MID   = colors.HexColor("#2C3E50")
    STEEL = colors.HexColor("#4A6274")
    LIGHT = colors.HexColor("#FDFEFE")
    ALT   = colors.HexColor("#F2F3F4")
    INPB  = colors.HexColor("#EBF5FB")
    RISKB = colors.HexColor("#FADBD8")
    BORD  = colors.HexColor("#AEB6BF")
    W_    = colors.white

    PW,PH = A4
    ML = 15*mm
    W  = PW - 2*ML

    buf = io.BytesIO()
    cv  = C.Canvas(buf, pagesize=A4)
    cv.setTitle(f"RAQ-{airport.get('icao','')}-{fi.get('date','')}")
    frm = cv.acroForm
    y   = PH - 12*mm

    def bx(x,yt,w,h,fill=None,stroke=BORD,sw=0.5):
        cv.saveState()
        cv.setLineWidth(sw); cv.setStrokeColor(stroke)
        if fill: cv.setFillColor(fill); cv.rect(x,yt-h,w,h,fill=1,stroke=1)
        else: cv.rect(x,yt-h,w,h,fill=0,stroke=1)
        cv.restoreState()

    def tx(text,x,yb,font=FN,size=9,color=DARK,align='left',mw=None):
        cv.saveState(); cv.setFont(font,size); cv.setFillColor(color)
        if align=='center' and mw: x=x+(mw-cv.stringWidth(text,font,size))/2
        elif align=='right' and mw: x=x+mw-cv.stringWidth(text,font,size)
        cv.drawString(x,yb,text); cv.restoreState()

    def wl(text,font,size,mw):
        import re
        words=re.split(r'(\s+)',text.replace('\n',' '))
        lines,line=[],""
        for w2 in words:
            t=line+w2
            if cv.stringWidth(t,font,size)<=mw: line=t
            else:
                if line.strip(): lines.append(line.strip())
                line=w2.lstrip()
        if line.strip(): lines.append(line.strip())
        return lines or [text]

    def shdr(yt,text,h=17):
        bx(ML,yt,W,h,fill=MID,stroke=DARK,sw=1)
        tx(f"  {text}",ML+4,yt-h+5,FB,9,W_); return yt-h

    def sbhdr(yt,text,h=13):
        bx(ML,yt,W,h,fill=STEEL,stroke=STEEL)
        tx(f"  {text}",ML+6,yt-h+3,FB,8,W_); return yt-h

    def tblk(yt,text,bg=INPB,pad=8):
        clean=text.replace('\\n','\n')
        parts=[p.strip() for p in clean.split('•') if p.strip()]
        lns=[]
        if parts:
            for p in parts: lns.extend(wl(f"• {p}",FN,8.5,W-pad*2-4))
        else: lns=wl(clean,FN,8.5,W-pad*2-4)
        h=len(lns)*11+pad*2
        bx(ML,yt,W,h,fill=bg,stroke=BORD)
        ty=yt-pad-8
        for ln in lns: tx(ln,ML+pad+2,ty,FN,8.5,DARK); ty-=11
        return yt-h

    def cbrow(yt,name,label,bg=LIGHT,h=18,sz=10):
        bx(ML,yt,W,h,fill=bg,stroke=BORD)
        cby=yt-h+(h-sz)/2
        frm.checkbox(name=name,tooltip=label,x=ML+6,y=cby,size=sz,
            checked=False,buttonStyle='check',borderColor=DARK,
            fillColor=W_,textColor=RED,forceBorder=True)
        tx(label,ML+6+sz+6,yt-h/2-3.5,FN,9,DARK); return yt-h

    def chdrs(yt,cols,h=15):
        x=ML
        for lbl,w2 in cols:
            bx(x,yt,w2,h,fill=STEEL,stroke=BORD)
            tx(lbl,x,yt-h+4,FB,8.5,W_,'center',w2); x+=w2
        return yt-h

    def cdata(yt,cols,h=21):
        x=ML
        for text,w2,font,size,color,align in cols:
            bx(x,yt,w2,h,fill=INPB,stroke=BORD)
            tx(text,x,yt-h+5,font,size,color,align,w2); x+=w2
        return yt-h

    # Header
    hh=26
    bx(ML,y,W*.72,hh,fill=RED,stroke=DARK,sw=1)
    bx(ML+W*.72,y,W*.28,hh,fill=MID,stroke=DARK,sw=1)
    tx("REC HAVACILIK  ✈  YOL VE MEYDAN YETERLİLİK EĞİTİM FORMU",ML+8,y-hh+8,FB,10,W_)
    tx("FOP-FRM02 | Rev 0 | 2023-10-31",ML+W*.72+4,y-hh+8,FB,7,W_)
    y-=hh
    bx(ML,y,W,13,fill=LIGHT,stroke=BORD)
    tx("ROUTE AND AERODROME QUALIFICATION TRAINING FORM",ML,y-10,FI,8,STEEL,'center',W)
    y-=13+3

    # Flight Details
    y=shdr(y,"FLIGHT DETAILS")
    cw=[W*.18,W*.15,W*.335,W*.335]
    y=chdrs(y,[("Date",cw[0]),("A/C Type",cw[1]),("PIC",cw[2]),("SIC",cw[3])])
    y=cdata(y,[(fi.get("date",""),cw[0],FB,9,DARK,'center'),
               (fi.get("ac_type",""),cw[1],FB,9,DARK,'center'),
               (fi.get("pic",""),cw[2],FB,9,DARK,'center'),
               (fi.get("sic",""),cw[3],FB,9,DARK,'center')]); y-=3

    # Aerodrome
    y=shdr(y,"AERODROME")
    cw2=[W*.50,W*.25,W*.25]
    y=chdrs(y,[("Airport Name",cw2[0]),("ICAO",cw2[1]),("Category",cw2[2])])
    ah=22; x=ML
    for text,w2,font,size,color in [
        (airport.get("name",""),cw2[0],FB,9,DARK),
        (airport.get("icao",""),cw2[1],FB,9,DARK),
        (airport.get("category",""),cw2[2],FB,13,RED)]:
        bx(x,y,w2,ah,fill=LIGHT,stroke=BORD)
        tx(text,x,y-ah+5,font,size,color,'center',w2); x+=w2
    y-=ah+3

    # Familiarization
    y=shdr(y,"FAMILIARIZATION CONDUCTED BY")
    hw=W/2
    y=chdrs(y,[("Self Briefing",hw),("Local Authority",hw)])
    fh=20
    bx(ML,y,hw,fh,fill=LIGHT,stroke=BORD)
    bx(ML+hw,y,hw,fh,fill=LIGHT,stroke=BORD)
    csz=12; cby=y-fh+(fh-csz)/2
    frm.checkbox(name='fam_self',tooltip='Self Briefing',x=ML+hw/2-csz/2,y=cby,size=csz,
        checked=False,buttonStyle='check',borderColor=DARK,fillColor=W_,textColor=RED,forceBorder=True)
    frm.checkbox(name='fam_local',tooltip='Local Authority',x=ML+hw+hw/2-csz/2,y=cby,size=csz,
        checked=False,buttonStyle='check',borderColor=DARK,fillColor=W_,textColor=RED,forceBorder=True)
    y-=fh+3

    # Briefing Items
    y=shdr(y,"FOLLOWING ITEMS WERE BRIEFED AND FAMILIARIZED FOR THE ROUTE FLOWN")
    for i,(nm,lbl) in enumerate([
        ("cb_terrain","Terrain and Safe Altitudes"),
        ("cb_comms","Communication and ATC Facilities"),
        ("cb_sar","Search & Rescue Procedures"),
        ("cb_layout","Airport Layout"),
        ("cb_approach","Approach Aids"),
        ("cb_instrument","Instrument Approach and Hold Procedures"),
        ("cb_minima","Operating Minima")]):
        y=cbrow(y,nm,lbl,bg=LIGHT if i%2==0 else ALT)
    y-=3

    # Special Items
    y=shdr(y,"SPECIAL ITEMS BRIEFED DUE TO AERODROME CATEGORY")
    for i,(nm,lbl) in enumerate([
        ("sp_1","(1) Non-standard approach aids or approach patterns"),
        ("sp_2","(2) Unusual local weather conditions"),
        ("sp_3","(3) Unusual characteristics or performance limitations"),
        ("sp_4","(4) Other relevant considerations: obstructions, physical layout, lighting etc."),
        ("sp_5","(5) Category C aerodromes: additional considerations for approach/landing/take-off.")]):
        y=cbrow(y,nm,lbl,bg=LIGHT if i%2==0 else ALT)
    y-=3

    # PPS Sections
    y=shdr(y,"SPECIAL REMARKS  -  PPS BRIEFING  (AUTO FROM DATABASE)")
    for lbl,key in [
        ("SECTION 1  -  Traffic / ATC / Taxi / Runway Ops","section1"),
        ("SECTION 2  -  Meteorology / Wind","section2"),
        ("SECTION 3  -  Security / Handling / Navigation","section3")]:
        y=sbhdr(y,lbl); y=tblk(y,airport.get(key,"N/A")); y-=2
    y-=3

    # Risk
    y=shdr(y,"AERODROME RISK SUMMARY  (AUTO - DATABASE)")
    if risk:
        rt=(f"RISK LEVEL: {risk['risk_level']}   |   CAT: {airport.get('category','')}   "
            f"|   {risk['ops_approval']}\nMITIGATION: {risk['mitigation']}")
    else: rt="Risk verisi bulunamadi."
    y=tblk(y,rt,bg=RISKB,pad=8); y-=3

    # Certification
    cert=("I hereby certify that route and aerodrome familiarization was completed "
          "for the flight in accordance with AMC1 ORO.FC.105 b(2);c and OM PART C.")
    ch=24; bx(ML,y,W,ch,fill=LIGHT,stroke=BORD)
    lns=wl(cert,FI,8,W-16); ty=y-6
    for ln in lns: tx(ln,ML+8,ty,FI,8,STEEL); ty-=10
    y-=ch
    today=datetime.date.today().strftime("%Y-%m-%d")
    cw3=[W*.22,W*.55,W*.23]; x=ML
    for text,w2,font,size,color,align in [
        ("Completed by:",cw3[0],FB,9,DARK,'center'),
        (fi.get("pic",""),cw3[1],FB,9,DARK,'center'),
        (today,cw3[2],FN,8,STEEL,'right')]:
        bx(x,y,w2,20,fill=LIGHT,stroke=BORD)
        tx(text,x,y-15,font,size,color,align,w2); x+=w2

    cv.save(); buf.seek(0)
    return buf.getvalue()

# ── UI ────────────────────────────────────────────────────────────────────────
airports, risks = load_db()

st.markdown("""
<div style="background:#C0392B;padding:18px 24px;border-radius:8px;margin-bottom:20px">
<h1 style="color:white;margin:0;font-size:22px">✈ REC HAVACILIK – RAQ Form Generator</h1>
<p style="color:#FADBD8;margin:4px 0 0 0;font-size:12px">Route and Aerodrome Qualification Training Form</p>
</div>
""", unsafe_allow_html=True)

icao = st.text_input("ICAO Kodu", max_chars=4, placeholder="EHAM").upper().strip()

if icao:
    if icao in airports:
        ap = airports[icao]
        rk = risks.get(icao)
        st.markdown(f"""
        <div class="info-card">
          <h3>✔ {ap['name']}</h3>
          <p>ICAO: {ap['icao']}   |   Kategori: {ap['category']}   |   Guncelleme: {ap['updated']}</p>
        </div>
        """, unsafe_allow_html=True)
        if rk:
            st.markdown(f"""
            <div class="risk-box">
              <p>RISK: {rk['risk_level']}  |  {rk['ops_approval']}</p>
            </div>
            """, unsafe_allow_html=True)
    elif len(icao) == 4:
        st.error("Meydan veritabaninda bulunamadi.")

st.divider()
st.subheader("Ucus Bilgileri")

col1, col2 = st.columns(2)
with col1:
    pic  = st.text_input("PIC (Ad Soyad / Kod)")
    date = st.date_input("Ucus Tarihi", value=datetime.date.today())
with col2:
    sic = st.text_input("SIC (Ad Soyad / Kod)")
    ac  = st.text_input("A/C Type", value="TC-REC")

st.divider()

if st.button("📄  RAQ FORM PDF OLUSTUR", use_container_width=True, type="primary"):
    if not icao or icao not in airports:
        st.error("Gecerli bir ICAO kodu girin.")
    elif not pic:
        st.error("PIC bilgisini girin.")
    else:
        with st.spinner("PDF olusturuluyor..."):
            try:
                pdf = generate_pdf(airports[icao], risks.get(icao), {
                    "date": date.strftime("%Y-%m-%d"),
                    "ac_type": ac, "pic": pic, "sic": sic,
                })
                fname = f"RAQ_{icao}_{date.strftime('%Y-%m-%d')}.pdf"
                st.success(f"✔ PDF hazir!")
                st.download_button(
                    "⬇  PDF Indir", pdf, fname,
                    "application/pdf", use_container_width=True)
            except Exception as e:
                st.error(f"Hata: {e}")

st.caption("© REC HAVACILIK  -  AMC1 ORO.FC.105 b(2);c")

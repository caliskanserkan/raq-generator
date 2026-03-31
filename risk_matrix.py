import streamlit as st
from utils import load_db, TOPICS

st.set_page_config(
    page_title="Risk Matrix - REC Havacilik",
    page_icon="✈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
#MainMenu{visibility:hidden}footer{visibility:hidden}
[data-testid="stToolbar"]{display:none!important}
</style>
""", unsafe_allow_html=True)

# ── Renk yardımcıları ──────────────────────────────────────────────────────────
RISK_COLORS = {
    "LOW":     {"bg": "#e6f1fb", "border": "#185FA5", "text": "#0C447C", "badge": "🟦"},
    "MEDIUM":  {"bg": "#fdf3e0", "border": "#BA7517", "text": "#633806", "badge": "🟨"},
    "HIGH":    {"bg": "#fde8e8", "border": "#C0392B", "text": "#7B241C", "badge": "🟧"},
    "EXTREME": {"bg": "#FADBD8", "border": "#922B21", "text": "#7B241C", "badge": "🟥"},
    "N/A":     {"bg": "#f5f5f5", "border": "#ccc",    "text": "#888",    "badge": "⬜"},
}

def score_color(v):
    if v >= 5: return "#922B21"
    if v >= 4: return "#C0392B"
    if v >= 3: return "#BA7517"
    if v >= 2: return "#1A5276"
    return "#1E8449"

ADDONS = [
    ("night", "Night Ops",               1),
    ("xw",    "Strong XW / Gust",        2),
    ("wet",   "RWY Wet / Contaminated",  2),
    ("lv",    "Low Vis / TS",            2),
    ("fam",   "Crew Low Familiarity",    2),
]

def compute_total(base_score, addon_state):
    addon_pts = sum(pts for key, _, pts in ADDONS if addon_state.get(key, False))
    total = base_score + addon_pts
    if total <= 6:   rl = "LOW"
    elif total <= 9: rl = "MEDIUM"
    elif total <= 12:rl = "HIGH"
    else:            rl = "EXTREME"
    return total, rl, addon_pts

# ── Veri yükle ─────────────────────────────────────────────────────────────────
airports, risks = load_db()

# ── Başlık ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:#1A252F;padding:16px 22px;border-radius:8px;margin-bottom:1rem">
<h1 style="color:white;margin:0;font-size:20px">✈ REC HAVACILIK – Airport Risk Matrix</h1>
<p style="color:#AEB6BF;margin:4px 0 0;font-size:12px">MATRIX_V8 · Google Sheets canlı veri · 5 dk önbellek</p>
</div>
""", unsafe_allow_html=True)

# ── ICAO arama ─────────────────────────────────────────────────────────────────
icao = st.text_input("ICAO Kodu", max_chars=4, placeholder="LTFJ / EDDF / EHAM").upper().strip()

if not icao:
    st.info("ICAO kodu girerek herhangi bir meydanın risk matrisini görüntüleyin.")
    st.stop()

if icao not in airports:
    st.error(f"**{icao}** veritabanında bulunamadı. Kodu kontrol edin veya admin panelinden ekleyin.")
    st.stop()

ap = airports[icao]
rk = risks.get(icao)

# ── Havalimanı başlığı ─────────────────────────────────────────────────────────
col_name, col_meta = st.columns([3, 1])
with col_name:
    st.markdown(f"### {ap['name']}")
    st.caption(f"ICAO: **{icao}**  ·  Kategori: **{ap['category']}**  ·  Güncelleme: {ap['updated']}")
with col_meta:
    if ap.get("ad_elev_ft"):
        st.metric("AD Elev", f"{ap['ad_elev_ft']} ft")

if not rk:
    st.warning("Bu meydan için risk skoru hesaplanamadı (MATRIX_STORE verisi eksik).")
    st.stop()

# ── Pilot Add-On seçimleri ─────────────────────────────────────────────────────
st.markdown("#### Operasyonel Faktörler")
st.caption("Uçuşa özel koşulları işaretleyin — toplam skora eklenir.")

addon_state = {}
cols = st.columns(len(ADDONS))
for i, (key, label, pts) in enumerate(ADDONS):
    with cols[i]:
        addon_state[key] = st.checkbox(f"{label}  (+{pts})", key=f"ao_{key}")

total, rl, addon_pts = compute_total(rk["base_score"], addon_state)
rc = RISK_COLORS.get(rl, RISK_COLORS["N/A"])

# OPS approval — add-on eklenince yeniden hesapla
if rl == "EXTREME":
    ops_txt = "OPS MANAGER APPROVAL REQUIRED"
elif rl == "HIGH" and ap["category"] == "C":
    ops_txt = "OPS MANAGER APPROVAL REQUIRED"
elif rl == "HIGH":
    ops_txt = "CAPTAIN REVIEW / DISPATCH COORDINATION"
else:
    ops_txt = "DISPATCH OK"

# ── Risk sonuç kartı ───────────────────────────────────────────────────────────
st.markdown("---")
c1, c2, c3 = st.columns([1, 2, 2])
with c1:
    st.markdown(
        f"<div style='background:{rc['bg']};border:2px solid {rc['border']};"
        f"border-radius:10px;padding:16px 10px;text-align:center'>"
        f"<div style='font-size:42px;font-weight:800;color:{rc['text']}'>{total}</div>"
        f"<div style='font-size:11px;color:{rc['text']};opacity:.7'>BASE {rk['base_score']}"
        f"{f' + {addon_pts}' if addon_pts else ''}</div></div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f"<div style='background:{rc['bg']};border:2px solid {rc['border']};"
        f"border-radius:10px;padding:16px 14px;height:100%'>"
        f"<div style='font-size:22px;font-weight:800;color:{rc['text']}'>{rc['badge']} {rl}</div>"
        f"<div style='font-size:12px;color:{rc['text']};margin-top:6px'>{ops_txt}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f"<div style='background:#f8f8f5;border:1px solid #ddd;"
        f"border-radius:10px;padding:12px 14px;font-size:12px;color:#444;height:100%'>"
        f"<b>Max S:</b> {rk['max_s']}  ·  <b>Max L:</b> {rk['max_l']}<br>"
        f"<b>Kategori:</b> {ap['category']}<br><br>"
        f"{rk['mitigation'][:120] + '…' if len(rk.get('mitigation','')) > 120 else rk.get('mitigation','—')}"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Sekmeler ──────────────────────────────────────────────────────────────────
st.markdown("---")
tab1, tab2, tab3 = st.tabs(["📊 Topic Scores", "📋 PPS Briefing", "🗺 5×5 Matrix"])

with tab1:
    st.caption("Her konu için Severity (S) × Likelihood (L) — Veritabanından otomatik")
    for i, topic in enumerate(TOPICS):
        sv = rk["s"][i] if i < len(rk["s"]) else 0
        lv = rk["l"][i] if i < len(rk["l"]) else 0
        score = int(sv * lv)

        c_t, c_s, c_x, c_l, c_sc = st.columns([4, 1, 0.3, 1, 1])
        with c_t:
            st.markdown(f"<span style='font-size:13px;color:#333'>{i+1}. {topic}</span>", unsafe_allow_html=True)
        with c_s:
            s_col = score_color(sv)
            st.markdown(f"<div style='background:{s_col};color:white;border-radius:5px;padding:3px 0;text-align:center;font-weight:700;font-size:13px'>S {int(sv)}</div>", unsafe_allow_html=True)
        with c_x:
            st.markdown("<div style='text-align:center;padding-top:4px;color:#aaa;font-size:12px'>×</div>", unsafe_allow_html=True)
        with c_l:
            l_col = score_color(lv)
            st.markdown(f"<div style='background:{l_col};color:white;border-radius:5px;padding:3px 0;text-align:center;font-weight:700;font-size:13px'>L {int(lv)}</div>", unsafe_allow_html=True)
        with c_sc:
            st.markdown(f"<div style='text-align:center;font-weight:700;font-size:14px;padding-top:3px;color:#1a1a1a'>= {score}</div>", unsafe_allow_html=True)

with tab2:
    for title, key in [
        ("Section 1 — Traffic / ATC / Taxi / Runway Ops", "section1"),
        ("Section 2 — Meteorology / Wind",                "section2"),
        ("Section 3 — Security / Handling / Navigation",  "section3"),
    ]:
        text = ap.get(key, "").strip()
        if text:
            with st.expander(title, expanded=True):
                st.markdown(
                    f"<div style='font-size:13px;line-height:1.8;white-space:pre-line;color:#333'>{text}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption(f"{title}: Veri yok")

with tab3:
    st.caption(f"Mevcut konum: S={rk['max_s']} × L={rk['max_l']} → Base {rk['base_score']} · Total (add-on dahil) {total}")

    header_cols = st.columns([1, 1, 1, 1, 1, 1])
    with header_cols[0]:
        st.markdown("<div style='font-size:10px;color:#888;text-align:center'>L \\ S</div>", unsafe_allow_html=True)
    for j, s in enumerate([1, 2, 3, 4, 5]):
        with header_cols[j + 1]:
            st.markdown(f"<div style='font-size:11px;font-weight:700;color:#555;text-align:center'>S{s}</div>", unsafe_allow_html=True)

    for l in [5, 4, 3, 2, 1]:
        row_cols = st.columns([1, 1, 1, 1, 1, 1])
        with row_cols[0]:
            st.markdown(f"<div style='font-size:11px;font-weight:700;color:#555;text-align:center;padding-top:8px'>L{l}</div>", unsafe_allow_html=True)
        for j, s in enumerate([1, 2, 3, 4, 5]):
            cell_score = l * s
            if cell_score >= 17:   bg, tc = "#FADBD8", "#922B21"
            elif cell_score >= 10: bg, tc = "#fdf3e0", "#7D6608"
            elif cell_score >= 4:  bg, tc = "#edfbe4", "#1E8449"
            else:                  bg, tc = "#e6f1fb", "#1A5276"

            is_cur = (l == rk["max_l"] and s == rk["max_s"])
            border = f"3px solid {rc['border']}" if is_cur else "1px solid #ddd"
            fw = "800" if is_cur else "600"
            with row_cols[j + 1]:
                st.markdown(
                    f"<div style='background:{bg};border:{border};border-radius:6px;"
                    f"padding:8px 0;text-align:center;font-size:13px;font-weight:{fw};color:{tc}'>"
                    f"{'▶ ' if is_cur else ''}{cell_score}</div>",
                    unsafe_allow_html=True,
                )

st.markdown("---")
st.caption("© REC HAVACILIK  ·  MATRIX_V8  ·  AMC1 ORO.FC.105 b(2);c")

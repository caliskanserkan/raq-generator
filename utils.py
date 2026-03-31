import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

TOPICS = [
    "Approach & Traffic Density",
    "Obstacles / Terrain",
    "Seasonal / Meteorology",
    "ATC Phraseology / Language",
    "Complex Taxi Routings",
    "RWY Ops / Late Clearance",
    "Security / Terror Threat",
    "Handling / Fuel / Pax Support",
    "Radio Nav / GNSS Reliability",
    "AD Elev / Max TMA MSA",
]

def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = {
        "type":                        st.secrets["gcp"]["type"],
        "project_id":                  st.secrets["gcp"]["project_id"],
        "private_key_id":              st.secrets["gcp"]["private_key_id"],
        "private_key":                 st.secrets["gcp"]["private_key"],
        "client_email":                st.secrets["gcp"]["client_email"],
        "client_id":                   st.secrets["gcp"]["client_id"],
        "auth_uri":                    st.secrets["gcp"]["auth_uri"],
        "token_uri":                   st.secrets["gcp"]["token_uri"],
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            f"https://www.googleapis.com/robot/v1/metadata/x509/"
            f"{st.secrets['gcp']['client_email']}"
        ),
    }
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["sheets"]["spreadsheet_id"])


def _safe_float(v):
    """Return float if v looks numeric, else 0.0"""
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def _compute_risk(s_vals, l_vals, alt_msa_score, category):
    """
    Replicate MATRIX_V8 / MATRIX_STORE formula exactly:
      base = ROUND(AVG_TOP3_S + AVG_TOP3_L - 1)
           + (1 if alt_msa_score >= 1)
           + (1 if category == "C")
    """
    top3_s = sorted(s_vals, reverse=True)[:3]
    top3_l = sorted(l_vals, reverse=True)[:3]
    if not top3_s or not top3_l:
        return 0, "N/A", "N/A"

    base = round(sum(top3_s) / len(top3_s) + sum(top3_l) / len(top3_l) - 1)
    base += 1 if alt_msa_score >= 1 else 0
    base += 1 if category == "C" else 0

    if base <= 6:
        rl, ops = "LOW", "DISPATCH OK"
    elif base <= 9:
        rl, ops = "MEDIUM", "DISPATCH OK"
    elif base <= 12:
        rl = "HIGH"
        ops = (
            "OPS MANAGER APPROVAL REQUIRED"
            if category == "C"
            else "CAPTAIN REVIEW / DISPATCH COORDINATION"
        )
    else:
        rl, ops = "EXTREME", "OPS MANAGER APPROVAL REQUIRED"

    return base, rl, ops


@st.cache_data(ttl=300)
def load_db():
    """
    Returns (airports, risks).

    airports[ICAO] = {icao, name, section1..3, updated, category,
                      ad_elev_ft, max_tma_msa, alt_msa_score}

    risks[ICAO]    = {base_score, risk_level, ops_approval, mitigation,
                      max_s, max_l,
                      s: [s1..s10],  l: [l1..l10]}
    """
    try:
        sh   = get_gsheet()
        adb  = sh.worksheet("AIRPORT_DB").get_all_values()
        mst  = sh.worksheet("MATRIX_STORE").get_all_values()

        # ── AIRPORT_DB ────────────────────────────────────────────────
        airports = {}
        for row in adb[1:]:
            if not row or not row[0]:
                continue
            icao = str(row[0]).upper().strip()
            def _g(r, i, default=""):
                return r[i] if len(r) > i and r[i] else default

            airports[icao] = {
                "icao":           icao,
                "name":           _g(row, 1, icao),
                "section1":       _g(row, 2),
                "section2":       _g(row, 3),
                "section3":       _g(row, 4),
                "updated":        str(_g(row, 6))[:10],
                "category":       _g(row, 8, "A"),
                "ad_elev_ft":     int(_safe_float(_g(row, 9,  0))),
                "max_tma_msa":    int(_safe_float(_g(row, 10, 0))),
                "alt_msa_score":  int(_safe_float(_g(row, 11, 0))),
            }

        # ── MATRIX_STORE ──────────────────────────────────────────────
        risks = {}
        for row in mst[1:]:
            if not row or not row[0]:
                continue
            icao = str(row[0]).upper().strip()

            # S1-S9  → columns B-J  (indices 1-9)
            # S10    → formula cell (index 10) — use alt_msa_score+1 from AIRPORT_DB
            # L1-L9  → columns L-T  (indices 11-19)
            # L10    → formula cell (index 20) — same as S10
            raw_s = [_safe_float(row[i]) if i < len(row) else 0.0 for i in range(1, 10)]
            raw_l = [_safe_float(row[i]) if i < len(row) else 0.0 for i in range(11, 20)]

            # Pull alt_msa_score from AIRPORT_DB if available
            ams = airports.get(icao, {}).get("alt_msa_score", 0)
            s10 = float(ams + 1)   # formula: =IFERROR(alt_msa_score+1, 2)
            l10 = float(ams + 1)

            s_all = raw_s + [s10]
            l_all = raw_l + [l10]

            cat = row[27] if len(row) > 27 and row[27] else airports.get(icao, {}).get("category", "A")
            mit = row[24] if len(row) > 24 else ""

            base, rl, ops = _compute_risk(s_all, l_all, ams, cat)

            max_s = round(sum(sorted(s_all, reverse=True)[:3]) / 3) if s_all else 0
            max_l = round(sum(sorted(l_all, reverse=True)[:3]) / 3) if l_all else 0

            risks[icao] = {
                "base_score":   base,
                "risk_level":   rl,
                "ops_approval": ops,
                "mitigation":   mit,
                "max_s":        max_s,
                "max_l":        max_l,
                "s":            s_all,
                "l":            l_all,
            }

        return airports, risks

    except Exception as e:
        st.error(f"Veritabani hatasi: {e}")
        return {}, {}


def update_airport(icao, fields):
    """
    Write fields to AIRPORT_DB.
    If ICAO exists → update in-place. Else → append new row.
    col_map uses 1-based gspread column indices.
    """
    col_map = {
        "name":     2,
        "section1": 3,
        "section2": 4,
        "section3": 5,
        "category": 9,
    }
    try:
        sh  = get_gsheet()
        ws  = sh.worksheet("AIRPORT_DB")
        rows = ws.get_all_values()

        for i, row in enumerate(rows):
            if row and str(row[0]).upper().strip() == icao.upper().strip():
                for field, val in fields.items():
                    if field in col_map:
                        ws.update_cell(i + 1, col_map[field], val)
                return True

        # ICAO not found — append new row
        new_row = [""] * 12
        new_row[0] = icao.upper()
        for field, val in fields.items():
            if field in col_map:
                new_row[col_map[field] - 1] = val
        ws.append_row(new_row)
        return True

    except Exception as e:
        st.error(f"Guncelleme hatasi: {e}")
        return False

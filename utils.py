from __future__ import annotations

import json
from typing import Any, Dict, Tuple

try:
    import streamlit as st
except Exception:
    st = None

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_OK = True
except Exception:
    GSPREAD_OK = False

JSON_FIELDS = {"ra_risk_basis", "ra_key_drivers", "ra_actions", "ra_briefing_items"}
SHEET_NAME  = "AIRPORT_DB"

COL_MAP = {
    "icao":             "icao",
    "airport_name":     "name",
    "section1b1:l2":    "section1",
    "section1":         "section1",
    "section2":         "section2",
    "section3":         "section3",
    "10_ad elev / max tma msa": "alt_msa_label",
    "last_update":      "last_update",
    "notes":            "notes",
    "category":         "category",
    "ad_elev_ft":       "ad_elev_ft",
    "max_tma_msa_ft":   "max_tma_msa_ft",
    "alt_msa_combined_score": "alt_msa_combined_score",
    "survey_last_updated":  "survey_last_updated",
    "survey_updated_by":    "survey_updated_by",
    "survey_version":       "survey_version",
    "aip_source_name":      "aip_source_name",
    "aip_source_url":       "aip_source_url",
    "aip_reference":        "aip_reference",
    "aip_last_checked":     "aip_last_checked",
    "ra_risk_level":        "ra_risk_level",
    "ra_risk_score":        "ra_risk_score",
    "ra_ops_approval":      "ra_ops_approval",
    "ra_mitigation":        "ra_mitigation",
    "ra_assessed_by":       "ra_assessed_by",
    "ra_assessment_date":   "ra_assessment_date",
    "ra_reassessment_due":  "ra_reassessment_due",
    "ra_risk_basis":        "ra_risk_basis",
    "ra_key_drivers":       "ra_key_drivers",
    "ra_actions":           "ra_actions",
    "ra_briefing_items":    "ra_briefing_items",
    "name":                 "name",
}


def _get_client():
    """Her seferinde taze client — önbelleğe ALINMAZ."""
    if not GSPREAD_OK:
        return None, "gspread veya google-auth paketi yüklü değil."
    try:
        creds_dict = dict(st.secrets["gcp"])
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds), None
    except KeyError:
        return None, "secrets.toml içinde [gcp] bölümü bulunamadı."
    except Exception as e:
        return None, f"Google auth hatası: {e}"


def _get_sheet():
    client, err = _get_client()
    if not client:
        return None, err
    try:
        spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
        sh = client.open_by_key(spreadsheet_id)
        all_titles = [ws.title for ws in sh.worksheets()]
        if SHEET_NAME not in all_titles:
            return None, (
                f"'{SHEET_NAME}' sekmesi bulunamadı. "
                f"Mevcut sekmeler: {all_titles}"
            )
        return sh.worksheet(SHEET_NAME), None
    except KeyError:
        return None, "secrets.toml içinde [sheets]/spreadsheet_id bulunamadı."
    except Exception as e:
        return None, f"Sheet açma hatası: {e}"


def _deserialize(key, value):
    if key not in JSON_FIELDS:
        return value
    if not value:
        return []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return []
        try:
            return json.loads(txt)
        except Exception:
            return [l.strip() for l in txt.splitlines() if l.strip()]
    return []


def _serialize(key, value):
    if key not in JSON_FIELDS:
        return str(value) if value is not None else ""
    if value is None:
        return json.dumps([])
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        lines = [l.strip() for l in value.splitlines() if l.strip()]
        return json.dumps(lines or ([value] if value else []))
    return json.dumps([])


@st.cache_data(ttl=60, show_spinner=False)
def load_db() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    ws, err = _get_sheet()
    if ws is None:
        return {}, {}
    try:
        raw = ws.get_all_values()
        if not raw:
            return {}, {}
        raw_headers = [h.lower().strip() for h in raw[0]]
        norm_headers = [COL_MAP.get(h, h) for h in raw_headers]
    except Exception:
        return {}, {}

    airports: Dict[str, Dict[str, Any]] = {}
    risks:    Dict[str, Dict[str, Any]] = {}

    for row in raw[1:]:
        row_dict = {
            norm_headers[i]: (row[i] if i < len(row) else "")
            for i in range(len(norm_headers))
        }
        icao = str(row_dict.get("icao", "")).upper().strip()
        if not icao:
            continue

        data: Dict[str, Any] = {k: _deserialize(k, v) for k, v in row_dict.items()}
        if not data.get("name"):
            data["name"] = data.get("airport_name", "")
        data["icao"] = icao
        airports[icao] = data

        if data.get("ra_risk_level"):
            risks[icao] = {
                "risk_level":          data.get("ra_risk_level"),
                "score":               data.get("ra_risk_score"),
                "basis":               data.get("ra_risk_basis") or [],
                "drivers":             data.get("ra_key_drivers") or [],
                "actions":             data.get("ra_actions") or [],
                "summary":             data.get("ra_briefing_items") or [],
                "assessment_date":     data.get("ra_assessment_date"),
                "reassessment_due":    data.get("ra_reassessment_due"),
                "assessed_by":         data.get("ra_assessed_by"),
                "survey_last_updated": data.get("survey_last_updated"),
                "survey_updated_by":   data.get("survey_updated_by"),
                "survey_version":      data.get("survey_version"),
            }

    return airports, risks


def update_airport(icao: str, updates: Dict[str, Any]) -> bool:
    icao = (icao or "").upper().strip()
    if not icao:
        return False
    ws, err = _get_sheet()
    if ws is None:
        if st and err:
            st.error(f"❌ Bağlantı hatası: {err}")
        return False
    try:
        raw = ws.get_all_values()
        if not raw:
            return False

        raw_headers = raw[0]
        norm_headers = [
            COL_MAP.get(h.lower().strip(), h.lower().strip())
            for h in raw_headers
        ]

        for key in updates:
            if key not in norm_headers:
                norm_headers.append(key)
                raw_headers.append(key)
                ws.update_cell(1, len(raw_headers), key)

        if "icao" not in norm_headers:
            if st:
                st.error("❌ Sheets'te 'icao' sütunu bulunamadı!")
            return False

        icao_idx = norm_headers.index("icao")
        icao_col = icao_idx + 1

        cell = ws.find(icao, in_column=icao_col)

        if cell:
            row_idx = cell.row
            existing_vals = ws.row_values(row_idx)
            existing = {
                norm_headers[i]: (existing_vals[i] if i < len(existing_vals) else "")
                for i in range(len(norm_headers))
            }
            existing.update({k: _serialize(k, v) for k, v in updates.items()})
            existing["icao"] = icao
            ws.update(f"A{row_idx}", [[existing.get(h, "") for h in norm_headers]])
        else:
            new_row = {"icao": icao}
            new_row.update({k: _serialize(k, v) for k, v in updates.items()})
            ws.append_row([new_row.get(h, "") for h in norm_headers])

        load_db.clear()
        return True

    except Exception as e:
        if st:
            st.error(f"❌ Sheets yazma hatası: {e}")
        return False


def run_diagnostics() -> dict:
    """Bağlantıyı adım adım test eder — admin debug paneli için."""
    result = {
        "gspread_ok": False,
        "client_ok":  False,
        "sheet_ok":   False,
        "row_count":  0,
        "icao_codes": [],
        "headers":    [],
        "sheet_tabs": [],
        "error":      None,
    }

    if not GSPREAD_OK:
        result["error"] = "gspread paketi yüklü değil."
        return result
    result["gspread_ok"] = True

    client, err = _get_client()
    if not client:
        result["error"] = err
        return result
    result["client_ok"] = True

    try:
        spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
        sh = client.open_by_key(spreadsheet_id)
        result["sheet_tabs"] = [ws.title for ws in sh.worksheets()]
    except Exception as e:
        result["error"] = f"Spreadsheet açılamadı: {e}"
        return result

    if SHEET_NAME not in result["sheet_tabs"]:
        result["error"] = (
            f"'{SHEET_NAME}' sekmesi bulunamadı. "
            f"Mevcut sekmeler: {result['sheet_tabs']}"
        )
        return result

    ws = sh.worksheet(SHEET_NAME)
    result["sheet_ok"] = True

    try:
        raw = ws.get_all_values()
        result["row_count"] = max(0, len(raw) - 1)
        if raw:
            result["headers"] = [h.lower().strip() for h in raw[0]]
            norm_h = [COL_MAP.get(h, h) for h in result["headers"]]
            for row in raw[1:]:
                row_dict = {norm_h[i]: (row[i] if i < len(row) else "") for i in range(len(norm_h))}
                icao = str(row_dict.get("icao", "")).upper().strip()
                if icao:
                    result["icao_codes"].append(icao)
    except Exception as e:
        result["error"] = f"Veri okuma hatası: {e}"

    return result

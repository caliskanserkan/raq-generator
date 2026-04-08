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


@st.cache_resource(show_spinner=False)
def _get_client():
    if not GSPREAD_OK:
        return None
    try:
        creds_dict = dict(st.secrets["gcp"])
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        if st: st.error(f"Google Sheets bağlantı hatası: {e}")
        return None


def _get_sheet():
    client = _get_client()
    if not client:
        return None
    try:
        spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
        sh = client.open_by_key(spreadsheet_id)
        try:
            return sh.worksheet(SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=SHEET_NAME, rows=600, cols=50)
            return ws
    except Exception as e:
        if st: st.error(f"Sheet açma hatası: {e}")
        return None


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
    ws = _get_sheet()
    if ws is None:
        return {}, {}
    try:
        raw = ws.get_all_values()
        if not raw:
            return {}, {}
        # Başlık satırını küçük harfe çevir
        headers = [h.lower().strip() for h in raw[0]]
        all_rows = [dict(zip(headers, row)) for row in raw[1:]]
    except Exception as e:
        if st: st.error(f"Sheets okuma hatası: {e}")
        return {}, {}

    airports: Dict[str, Dict[str, Any]] = {}
    risks:    Dict[str, Dict[str, Any]] = {}

    for row in all_rows:
        icao = str(row.get("icao", "")).upper().strip()
        if not icao:
            continue
        data: Dict[str, Any] = {k: _deserialize(k, v) for k, v in row.items()}
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
    ws = _get_sheet()
    if ws is None:
        return False
    try:
        headers = ws.row_values(1)
        if not headers:
            return False

        # Eksik kolonları başlığa ekle
        for key in updates:
            if key not in headers:
                headers.append(key)
                ws.update_cell(1, len(headers), key)

        icao_col = headers.index("icao") + 1
        cell = ws.find(icao, in_column=icao_col)

        if cell:
            row_idx = cell.row
            existing_vals = ws.row_values(row_idx)
            existing = {h: (existing_vals[i] if i < len(existing_vals) else "") for i, h in enumerate(headers)}
            existing.update({k: _serialize(k, v) for k, v in updates.items()})
            existing["icao"] = icao
            ws.update(f"A{row_idx}", [[existing.get(h, "") for h in headers]])
        else:
            new_row_dict = {"icao": icao}
            new_row_dict.update({k: _serialize(k, v) for k, v in updates.items()})
            ws.append_row([new_row_dict.get(h, "") for h in headers])

        load_db.clear()
        return True

    except Exception as e:
        if st: st.error(f"❌ Sheets yazma hatası: {e}")
        return False

from __future__ import annotations

import json, os, shutil, sqlite3, tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

try:
    import streamlit as st
except Exception:
    st = None

JSON_FIELDS = {"ra_risk_basis", "ra_key_drivers", "ra_actions", "ra_briefing_items"}

REQUIRED_COLUMNS = {
    "icao":               "TEXT PRIMARY KEY",
    "name":               "TEXT",
    "category":           "TEXT",
    "section1":           "TEXT",
    "section2":           "TEXT",
    "section3":           "TEXT",
    "ra_risk_level":      "TEXT",
    "ra_risk_score":      "REAL",
    "ra_risk_basis":      "TEXT",
    "ra_key_drivers":     "TEXT",
    "ra_actions":         "TEXT",
    "ra_briefing_items":  "TEXT",
    "ra_assessment_date": "TEXT",
    "ra_reassessment_due":"TEXT",
    "ra_assessed_by":     "TEXT",
    "ra_ops_approval":    "TEXT",
    "ra_mitigation":      "TEXT",
    "survey_last_updated":"TEXT",
    "survey_updated_by":  "TEXT",
    "survey_version":     "TEXT",
    "aip_source_name":    "TEXT",
    "aip_source_url":     "TEXT",
    "aip_reference":      "TEXT",
    "aip_last_checked":   "TEXT",
}


def _get_db_path() -> Path:
    # 1. Streamlit secrets
    if st is not None:
        try:
            p = st.secrets.get("database", {}).get("path", "")
            if p:
                return Path(p)
        except Exception:
            pass

    # 2. Env var
    p = os.getenv("FBAT_DB_PATH", "").strip()
    if p:
        return Path(p)

    # 3. Repo'daki DB — Streamlit Cloud'da read-only olabilir.
    #    /tmp'ye kopyala (yazılabilir).
    src = Path(__file__).resolve().parent / "airports.db"
    tmp_dir = Path(tempfile.gettempdir()) / "fbat_data"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dst = tmp_dir / "airports.db"

    try:
        if src.exists():
            src_mtime = src.stat().st_mtime
            dst_mtime = dst.stat().st_mtime if dst.exists() else 0
            if src_mtime > dst_mtime:
                shutil.copy2(str(src), str(dst))
        if dst.exists():
            return dst
    except Exception:
        pass

    return src


def _connect() -> sqlite3.Connection:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _get_cols(conn, table) -> Dict[str, str]:
    if not _table_exists(conn, table):
        return {}
    return {r["name"]: r["type"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema(conn=None):
    owns = conn is None
    conn = conn or _connect()
    try:
        if not _table_exists(conn, "airports"):
            col_sql = ", ".join(f"{n} {t}" for n, t in REQUIRED_COLUMNS.items())
            conn.execute(f"CREATE TABLE airports ({col_sql})")
        else:
            existing = _get_cols(conn, "airports")
            for col, typ in REQUIRED_COLUMNS.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE airports ADD COLUMN {col} {typ}")
        conn.commit()
    finally:
        if owns:
            conn.close()


def _deserialize(key, value):
    if key not in JSON_FIELDS:
        return value
    if value is None:
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
        return value
    if value is None:
        return json.dumps([])
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        lines = [l.strip() for l in value.splitlines() if l.strip()]
        return json.dumps(lines or ([value] if value else []))
    return json.dumps([])


def load_db() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    conn = _connect()
    try:
        ensure_schema(conn)
        airports, risks = {}, {}
        for row in conn.execute("SELECT * FROM airports ORDER BY icao").fetchall():
            data = {k: _deserialize(k, v) for k, v in dict(row).items()}
            icao = (data.get("icao") or "").upper().strip()
            if not icao:
                continue
            data["icao"] = icao
            airports[icao] = data
            if data.get("ra_risk_level"):
                risks[icao] = {
                    "risk_level":       data.get("ra_risk_level"),
                    "score":            data.get("ra_risk_score"),
                    "basis":            data.get("ra_risk_basis") or [],
                    "drivers":          data.get("ra_key_drivers") or [],
                    "actions":          data.get("ra_actions") or [],
                    "summary":          data.get("ra_briefing_items") or [],
                    "assessment_date":  data.get("ra_assessment_date"),
                    "reassessment_due": data.get("ra_reassessment_due"),
                    "assessed_by":      data.get("ra_assessed_by"),
                    "survey_last_updated": data.get("survey_last_updated"),
                    "survey_updated_by":   data.get("survey_updated_by"),
                    "survey_version":      data.get("survey_version"),
                }
        return airports, risks
    finally:
        conn.close()


def update_airport(icao: str, updates: Dict[str, Any]) -> bool:
    icao = (icao or "").upper().strip()
    if not icao:
        return False

    conn = _connect()
    try:
        ensure_schema(conn)

        # Yeni kolonlar varsa ekle
        existing = _get_cols(conn, "airports")
        for key in updates:
            if key != "icao" and key not in existing:
                conn.execute(f"ALTER TABLE airports ADD COLUMN {key} TEXT")
                existing[key] = "TEXT"
        conn.commit()

        # Mevcut satırı çek
        cur = conn.execute("SELECT * FROM airports WHERE icao=?", (icao,)).fetchone()

        if cur:
            # UPDATE — sadece gelen alanları değiştir
            set_parts, vals = [], []
            for key, val in updates.items():
                if key == "icao":
                    continue
                set_parts.append(f"{key} = ?")
                vals.append(_serialize(key, val))
            if set_parts:
                conn.execute(
                    f"UPDATE airports SET {', '.join(set_parts)} WHERE icao = ?",
                    vals + [icao]
                )
        else:
            # INSERT — yeni meydan
            all_data = {"icao": icao}
            all_data.update(updates)
            cols = [c for c in all_data if c in existing or c == "icao"]
            vals = [_serialize(c, all_data[c]) for c in cols]
            conn.execute(
                f"INSERT INTO airports ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                vals
            )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        try:
            if st:
                st.error(f"❌ DB Hatası: {e}")
        except Exception:
            pass
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    conn = _connect()
    try:
        ensure_schema(conn)
        print(f"Schema OK → {_get_db_path()}")
    finally:
        conn.close()

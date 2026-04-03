from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

try:
    import streamlit as st
except Exception:
    st = None


JSON_FIELDS = {
    "ra_risk_basis",
    "ra_key_drivers",
    "ra_actions",
    "ra_briefing_items",
}

REQUIRED_COLUMNS = {
    "icao": "TEXT PRIMARY KEY",
    "name": "TEXT",
    "category": "TEXT",
    "section1": "TEXT",
    "section2": "TEXT",
    "section3": "TEXT",
    "ra_risk_level": "TEXT",
    "ra_risk_score": "INTEGER",
    "ra_risk_basis": "TEXT",
    "ra_key_drivers": "TEXT",
    "ra_actions": "TEXT",
    "ra_briefing_items": "TEXT",
    "ra_assessment_date": "TEXT",
    "ra_reassessment_due": "TEXT",
    "ra_assessed_by": "TEXT",
    "survey_last_updated": "TEXT",
    "survey_updated_by": "TEXT",
    "survey_version": "TEXT",
    "aip_source_name": "TEXT",
    "aip_source_url": "TEXT",
    "aip_reference": "TEXT",
    "aip_last_checked": "TEXT",
}


def _get_db_path() -> Path:
    # Streamlit secrets first
    if st is not None:
        try:
            db_path = st.secrets.get("database", {}).get("path", "")
            if db_path:
                return Path(db_path)
        except Exception:
            pass

    # Environment variable fallback
    env_path = os.getenv("FBAT_DB_PATH", "").strip()
    if env_path:
        return Path(env_path)

    # Repo'daki DB read-only olabilir (Streamlit Cloud).
    # Yazılabilir bir tmp kopyasına taşı.
    import shutil, tempfile
    src = Path(__file__).resolve().parent / "airports.db"
    tmp_dir = Path(tempfile.gettempdir()) / "fbat_data"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dst = tmp_dir / "airports.db"
    # Kaynak varsa ve hedef yoksa (veya kaynak daha yeniyse) kopyala
    if src.exists() and (not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime):
        shutil.copy2(str(src), str(dst))
    if dst.exists():
        return dst
    return src


def _connect() -> sqlite3.Connection:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> Dict[str, str]:
    cols: Dict[str, str] = {}
    if not _table_exists(conn, table):
        return cols
    for row in conn.execute(f"PRAGMA table_info({table})").fetchall():
        cols[row["name"]] = row["type"]
    return cols


def ensure_schema(conn: sqlite3.Connection | None = None) -> None:
    owns_conn = conn is None
    conn = conn or _connect()
    try:
        if not _table_exists(conn, "airports"):
            col_sql = ", ".join(f"{name} {col_type}" for name, col_type in REQUIRED_COLUMNS.items())
            conn.execute(f"CREATE TABLE airports ({col_sql})")
            conn.commit()
            return

        existing = _get_existing_columns(conn, "airports")
        for col, col_type in REQUIRED_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE airports ADD COLUMN {col} {col_type}")
        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def _deserialize_value(key: str, value: Any) -> Any:
    if value is None:
        if key in JSON_FIELDS:
            return []
        return value

    if key in JSON_FIELDS:
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, str):
            txt = value.strip()
            if not txt:
                return []
            try:
                return json.loads(txt)
            except Exception:
                # tolerate newline text fallback
                return [line.strip() for line in txt.splitlines() if line.strip()]
        return []
    return value


def _serialize_value(key: str, value: Any) -> Any:
    if key in JSON_FIELDS:
        if value is None:
            return json.dumps([])
        if isinstance(value, str):
            # keep existing text but store consistently as JSON list when possible
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            return json.dumps(lines if lines else [value] if value else [])
        return json.dumps(value, ensure_ascii=False)
    return value


def load_db() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    conn = _connect()
    try:
        ensure_schema(conn)
        rows = conn.execute("SELECT * FROM airports ORDER BY icao").fetchall()
        airports: Dict[str, Dict[str, Any]] = {}
        risks: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            data = dict(row)
            clean = {k: _deserialize_value(k, v) for k, v in data.items()}
            icao = (clean.get("icao") or "").upper().strip()
            if not icao:
                continue
            clean["icao"] = icao
            airports[icao] = clean

            if clean.get("ra_risk_level"):
                risks[icao] = {
                    "risk_level": clean.get("ra_risk_level"),
                    "score": clean.get("ra_risk_score"),
                    "basis": clean.get("ra_risk_basis") or [],
                    "drivers": clean.get("ra_key_drivers") or [],
                    "actions": clean.get("ra_actions") or [],
                    "summary": clean.get("ra_briefing_items") or [],
                    "assessment_date": clean.get("ra_assessment_date"),
                    "reassessment_due": clean.get("ra_reassessment_due"),
                    "assessed_by": clean.get("ra_assessed_by"),
                    "survey_last_updated": clean.get("survey_last_updated"),
                    "survey_updated_by": clean.get("survey_updated_by"),
                    "survey_version": clean.get("survey_version"),
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

        # Add unexpected columns safely as TEXT so the app remains resilient.
        existing_cols = _get_existing_columns(conn, "airports")
        for key in updates.keys():
            if key not in existing_cols and key not in ("icao",):
                conn.execute(f"ALTER TABLE airports ADD COLUMN {key} TEXT")
        conn.commit()

        current = conn.execute("SELECT * FROM airports WHERE icao = ?", (icao,)).fetchone()
        merged: Dict[str, Any] = {"icao": icao}
        if current:
            merged.update(dict(current))
        merged.update(updates)
        merged["icao"] = icao

        cols = list(merged.keys())
        placeholders = ", ".join("?" for _ in cols)
        update_clause = ", ".join(f"{col}=excluded.{col}" for col in cols if col != "icao")
        values = [_serialize_value(col, merged[col]) for col in cols]

        sql = f"""
            INSERT INTO airports ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(icao) DO UPDATE SET
            {update_clause}
        """
        conn.execute(sql, values)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
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

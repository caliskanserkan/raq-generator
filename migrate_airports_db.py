from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REQUIRED_COLUMNS = {
    "survey_last_updated": "TEXT",
    "survey_updated_by": "TEXT",
    "survey_version": "TEXT",
    "aip_source_name": "TEXT",
    "aip_source_url": "TEXT",
    "aip_reference": "TEXT",
    "aip_last_checked": "TEXT",
}

BASELINE_COLUMNS = {
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
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("airports.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        if not table_exists(conn, "airports"):
            all_cols = {**BASELINE_COLUMNS, **REQUIRED_COLUMNS}
            col_sql = ", ".join(f"{name} {ctype}" for name, ctype in all_cols.items())
            conn.execute(f"CREATE TABLE airports ({col_sql})")
            conn.commit()
            print(f"Created airports table at: {db_path}")
            return 0

        existing = get_existing_columns(conn, "airports")
        added = []
        for col, ctype in REQUIRED_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE airports ADD COLUMN {col} {ctype}")
                added.append(col)

        conn.commit()
        if added:
            print("Added columns:")
            for col in added:
                print(f" - {col}")
        else:
            print("No migration needed. All columns already exist.")
        print(f"Database OK: {db_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

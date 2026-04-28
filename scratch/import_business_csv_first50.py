from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

from business_csv_import import (  # noqa: E402
    DEFAULT_BUSINESS_CSV_FILENAME,
    DEFAULT_SOURCE_TYPE,
    dump_business_csv_result,
    run_business_csv_import,
)
from database import SessionLocal  # noqa: E402


SOURCE_PATH = ROOT / "docs" / DEFAULT_BUSINESS_CSV_FILENAME
ROW_LIMIT = 50
OWNER = "codex_business_csv_import"


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(SOURCE_PATH)
    raw = SOURCE_PATH.read_bytes()
    db = SessionLocal()
    try:
        result = run_business_csv_import(
            db,
            raw=raw,
            filename=SOURCE_PATH.name,
            row_limit=ROW_LIMIT,
            source_type=DEFAULT_SOURCE_TYPE,
            owner=OWNER,
        )
        print(dump_business_csv_result(result))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

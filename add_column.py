from backend.database import engine, SessionLocal
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE intent_summaries ADD COLUMN sales_advice_v2 TEXT;"))
        conn.commit()
        print("Column sales_advice_v2 added!")
except Exception as e:
    print(f"Error: {e}")

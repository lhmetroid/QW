import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    for l in open(p):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import engine
from sqlalchemy import text

with engine.connect() as c:
    # 1. Check total rows
    total = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified")).scalar()
    print(f"Total rows in mail_raw_unified: {total}")
    
    # 2. Check NULL or empty subject/body
    null_subject = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE subject IS NULL")).scalar()
    empty_subject = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE TRIM(subject) = ''")).scalar()
    null_body = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE body_text IS NULL")).scalar()
    empty_body = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE TRIM(body_text) = ''")).scalar()
    
    print(f"NULL subject: {null_subject}")
    print(f"Empty subject: {empty_subject}")
    print(f"NULL body: {null_body}")
    print(f"Empty body: {empty_body}")
    
    # 3. Check 'test' in subject or body
    exact_test_subject = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE LOWER(TRIM(subject)) = 'test'")).scalar()
    exact_test_body = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE LOWER(TRIM(body_text)) = 'test'")).scalar()
    
    contains_test_subject = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE LOWER(subject) LIKE '%test%'")).scalar()
    contains_test_body = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified WHERE LOWER(body_text) LIKE '%test%'")).scalar()
    
    print(f"Exact 'test' subject: {exact_test_subject}")
    print(f"Exact 'test' body: {exact_test_body}")
    print(f"Contains 'test' in subject: {contains_test_subject}")
    print(f"Contains 'test' in body: {contains_test_body}")
    
    # 4. Check typical test/empty conditions in the database
    # Let's find top 20 most common subjects
    print("\n--- Top 20 most common subjects in mail_raw_unified ---")
    top_subjects = c.execute(text("""
        SELECT subject, COUNT(*) as cnt 
        FROM mail_raw_unified 
        GROUP BY subject 
        ORDER BY cnt DESC 
        LIMIT 20
    """)).fetchall()
    for row in top_subjects:
        print(f"  {str(row[0])[:50]:52s} : {row[1]:,}")

    # Let's find top 20 most common bodies
    print("\n--- Top 20 most common body_texts in mail_raw_unified ---")
    top_bodies = c.execute(text("""
        SELECT SUBSTRING(body_text, 1, 100), COUNT(*) as cnt 
        FROM mail_raw_unified 
        GROUP BY SUBSTRING(body_text, 1, 100) 
        ORDER BY cnt DESC 
        LIMIT 20
    """)).fetchall()
    for row in top_bodies:
        print(f"  {str(row[0]).strip().replace(chr(10), ' ').replace(chr(13), ' ')[:80]:82s} : {row[1]:,}")

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
    print("=== Analyzing 22,232 actual emails ===")
    
    # 1. Total emails in mail_cleaned
    total_cleaned = c.execute(text("SELECT COUNT(*) FROM mail_cleaned")).scalar()
    print(f"Total in mail_cleaned: {total_cleaned}")
    
    # 2. Check empty or null body_main_text
    empty_main_text = c.execute(text("SELECT COUNT(*) FROM mail_cleaned WHERE body_main_text IS NULL OR TRIM(body_main_text) = ''")).scalar()
    non_empty_main_text = total_cleaned - empty_main_text
    print(f"Empty body_main_text: {empty_main_text}")
    print(f"Non-empty body_main_text: {non_empty_main_text}")
    
    # 3. Check sender_side (customer vs sales)
    # Customer emails are incoming emails from clients which are candidates for reply.
    # Sales emails are sent by our sales reps, so we don't reply to them.
    sender_sides = c.execute(text("SELECT sender_side, COUNT(*) FROM mail_cleaned GROUP BY sender_side")).fetchall()
    print("\n--- Group by sender_side ---")
    for r in sender_sides:
        print(f"  {r[0]} : {r[1]:,}")
        
    # 4. Check is_auto_mail (system bounce emails, automatic replies, etc.)
    auto_mails = c.execute(text("SELECT is_auto_mail, COUNT(*) FROM mail_cleaned GROUP BY is_auto_mail")).fetchall()
    print("\n--- Group by is_auto_mail ---")
    for r in auto_mails:
        print(f"  {r[0]} : {r[1]:,}")
        
    # 5. Let's look at combination of sender_side and is_auto_mail
    combos = c.execute(text("""
        SELECT sender_side, is_auto_mail, COUNT(*) 
        FROM mail_cleaned 
        GROUP BY sender_side, is_auto_mail
        ORDER BY count DESC
    """)).fetchall()
    print("\n--- Group by sender_side and is_auto_mail ---")
    for r in combos:
        print(f"  Sender: {r[0]:8s} | Auto: {str(r[1]):5s} | Count: {r[2]:,}")
        
    # 6. Let's define:
    # - "有效且非空邮件": Actual emails where body_main_text is not empty.
    # - "能回复邮件" (Can reply): Received from customer (sender_side = 'customer'), not an auto-generated mail (is_auto_mail = False), and body_main_text is not empty.
    # - "不能回复邮件" (Cannot reply): The rest of the actual emails. (E.g. sender_side = 'sales', or is_auto_mail = True, or body_main_text is empty).
    # Let's count these specifically:
    
    valid_non_empty = c.execute(text("""
        SELECT COUNT(*) FROM mail_cleaned 
        WHERE body_main_text IS NOT NULL AND TRIM(body_main_text) != ''
    """)).scalar()
    
    can_reply = c.execute(text("""
        SELECT COUNT(*) FROM mail_cleaned 
        WHERE sender_side = 'customer' 
          AND is_auto_mail = False 
          AND body_main_text IS NOT NULL 
          AND TRIM(body_main_text) != ''
    """)).scalar()
    
    cannot_reply = total_cleaned - can_reply
    
    print("\n=== Summary of actual emails (22,232) ===")
    print(f"1. 有效且非空邮件数量 (body_main_text is not empty): {valid_non_empty}")
    print(f"2. 能回复邮件数量 (customer incoming & not auto & non-empty body): {can_reply}")
    print(f"3. 不能回复邮件数量 (outbound sales / auto mail / empty body): {cannot_reply}")
    
    # Let's also check if there is any other table or criteria in the system for email reply
    # e.g., is there a specific table like "email_thread_asset" or "thread"?
    print("\n=== Check email_thread_asset table counts ===")
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='email_thread_asset')")).scalar():
        total_eta = c.execute(text("SELECT COUNT(*) FROM email_thread_asset")).scalar()
        usable_eta = c.execute(text("SELECT COUNT(*) FROM email_thread_asset WHERE usable_for_reply = True")).scalar()
        unusable_eta = total_eta - usable_eta
        print(f"Total in email_thread_asset: {total_eta}")
        print(f"  usable_for_reply = True: {usable_eta}")
        print(f"  usable_for_reply = False: {unusable_eta}")
        
    print("\n=== Check thread table counts ===")
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='thread')")).scalar():
        total_thread = c.execute(text("SELECT COUNT(*) FROM thread")).scalar()
        print(f"Total rows in thread table: {total_thread}")

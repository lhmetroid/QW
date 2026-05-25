# -*- coding: utf-8 -*-
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

def analyze():
    print("=================== 本地 PostgreSQL 邮件数据分析 ===================")
    
    with engine.connect() as c:
        # 1. 大表总数
        total_raw = c.execute(text("SELECT COUNT(*) FROM mail_raw_unified")).scalar()
        total_cleaned = c.execute(text("SELECT COUNT(*) FROM mail_cleaned")).scalar()
        print(f"mail_raw_unified 总记录数: {total_raw}")
        print(f"mail_cleaned 总记录数: {total_cleaned}")
        
        # 2. 按 source_type 分布
        sources = c.execute(text("""
            SELECT source_type, COUNT(*) 
            FROM mail_raw_unified 
            GROUP BY source_type
        """)).fetchall()
        print("\nmail_raw_unified 按 source_type 分布:")
        for s in sources:
            print(f"  {s[0]}: {s[1]}")
            
        # 3. 空数据情况
        empty_clean = c.execute(text("""
            SELECT COUNT(*) FROM mail_cleaned 
            WHERE body_main_text IS NULL OR TRIM(body_main_text) = ''
        """)).scalar()
        print(f"\nmail_cleaned 中 main_text 为空或空白字符的记录数: {empty_clean}")
        
        # 4. test 类噪音邮件数量
        test_noise = c.execute(text("""
            SELECT COUNT(*) FROM mail_cleaned 
            WHERE normalized_subject ILIKE '%test%' 
               OR body_main_text ILIKE '%test%'
        """)).scalar()
        print(f"mail_cleaned 中包含 'test' (case-insensitive) 的数量: {test_noise}")
        
        # 5. 可回复邮件 (客户发来)
        inbound_useful = c.execute(text("""
            SELECT COUNT(*) FROM mail_cleaned 
            WHERE clean_status = 'completed'
              AND is_auto_mail = FALSE
              AND body_main_text IS NOT NULL AND TRIM(body_main_text) <> ''
              AND (normalized_subject NOT ILIKE '%test%' AND body_main_text NOT ILIKE '%test%')
              AND sender_side = 'customer'
        """)).scalar()
        print(f"\n可回复邮件 (客户发来, completed, 非空, 非test, 非自动回复): {inbound_useful}")
        
        # 6. 不可回复邮件 (我方发送)
        outbound_useful = c.execute(text("""
            SELECT COUNT(*) FROM mail_cleaned 
            WHERE clean_status = 'completed'
              AND is_auto_mail = FALSE
              AND body_main_text IS NOT NULL AND TRIM(body_main_text) <> ''
              AND (normalized_subject NOT ILIKE '%test%' AND body_main_text NOT ILIKE '%test%')
              AND sender_side = 'seller'
        """)).scalar()
        print(f"不可回复邮件 (我方发去, completed, 非空, 非test, 作为 Few-Shot 候选): {outbound_useful}")

        # 7. email_thread_asset 兼容表统计
        print("\n--- email_thread_asset 兼容表统计 ---")
        total_eta = c.execute(text("SELECT COUNT(*) FROM email_thread_asset")).scalar()
        print(f"email_thread_asset 总记录数: {total_eta}")
        
        eta_sources = c.execute(text("""
            SELECT source_type, COUNT(*) 
            FROM email_thread_asset 
            GROUP BY source_type
        """)).fetchall()
        print("email_thread_asset 按 source_type 分布:")
        for s in eta_sources:
            print(f"  {s[0]}: {s[1]}")
            
        empty_eta = c.execute(text("""
            SELECT COUNT(*) FROM email_thread_asset 
            WHERE content IS NULL OR TRIM(content) = ''
        """)).scalar()
        print(f"email_thread_asset 中 content 为空的记录数: {empty_eta}")
        
        test_eta = c.execute(text("""
            SELECT COUNT(*) FROM email_thread_asset 
            WHERE subject ILIKE '%test%' OR content ILIKE '%test%'
        """)).scalar()
        print(f"email_thread_asset 中包含 'test' 的记录数: {test_eta}")
        
        usable_eta = c.execute(text("""
            SELECT COUNT(*) FROM email_thread_asset WHERE usable_for_reply = TRUE
        """)).scalar()
        unusable_eta = c.execute(text("""
            SELECT COUNT(*) FROM email_thread_asset WHERE usable_for_reply = FALSE
        """)).scalar()
        print(f"email_thread_asset 可回复 (usable_for_reply=TRUE) 的数量: {usable_eta}")
        print(f"email_thread_asset 不能回复 (usable_for_reply=FALSE) 的数量: {unusable_eta}")

if __name__ == "__main__":
    analyze()

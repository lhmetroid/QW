# -*- coding: utf-8 -*-
"""
数据修复与重新清洗脚本
- 识别 mail_cleaned 中 body_main_text 为空或仅含空白字符，但 mail_raw_unified.body_text 非空的记录
- 使用最新的 clean_mail_payload / upsert_mail_cleaned 规则对其进行重新清洗与修复
- 统计并报告修复结果
"""
import sys
import os
import io
import logging
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

# 加载环境变量
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        return
    for line in open(env_path):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

load_env()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("repair_cleaned_emails")

from database import SessionLocal
from sqlalchemy import text
from raw_comm_service import upsert_mail_cleaned

def repair_data():
    db = SessionLocal()
    try:
        logger.info("开始扫描需要修复的邮件记录...")
        
        # 1. 查找 body_main_text 为空但 raw.body_text 非空的记录
        query = text("""
            SELECT ru.mail_uid, ru.source_type, ru.folder_name, ru.direction,
                   ru.internet_message_id, ru.in_reply_to, ru.references_text,
                   ru.subject, ru.body_text, ru.from_email, ru.to_emails, ru.cc_emails,
                   ru.sent_at, ru.received_at, ru.has_attachment, ru.raw_payload_path
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE (ru.body_text IS NOT NULL AND TRIM(ru.body_text) <> '')
              AND (mc.body_main_text IS NULL OR TRIM(mc.body_main_text) = '')
        """)
        
        rows = db.execute(query).fetchall()
        total_to_repair = len(rows)
        logger.info("共找到 %d 封需要重新清洗和恢复内容的邮件记录", total_to_repair)
        
        if total_to_repair == 0:
            logger.info("没有检测到需要修复的空正文记录。")
            return
            
        success_count = 0
        restored_content_count = 0
        
        for index, row in enumerate(rows):
            mail_uid = row[0]
            to_emails_raw = row[10]
            cc_emails_raw = row[11]
            
            # 解析 json 字符串或数组
            import json
            try:
                to_emails = json.loads(to_emails_raw) if to_emails_raw else []
                if isinstance(to_emails, str):
                    to_emails = [to_emails]
            except Exception:
                to_emails = [to_emails_raw] if to_emails_raw else []
                
            try:
                cc_emails = json.loads(cc_emails_raw) if cc_emails_raw else []
                if isinstance(cc_emails, str):
                    cc_emails = [cc_emails]
            except Exception:
                cc_emails = [cc_emails_raw] if cc_emails_raw else []
                
            raw_mail = {
                "mail_uid": mail_uid,
                "source_type": row[1],
                "folder_name": row[2],
                "direction": row[3],
                "internet_message_id": row[4],
                "in_reply_to": row[5],
                "references_text": row[6],
                "subject": row[7],
                "body_text": row[8],
                "from_email": row[9],
                "to_emails": to_emails,
                "cc_emails": cc_emails,
                "sent_at": str(row[12]) if row[12] else None,
                "received_at": str(row[13]) if row[13] else None,
                "has_attachment": row[14],
                "raw_payload_path": row[15]
            }
            
            try:
                # 重新清洗并更新数据库
                upsert_mail_cleaned(db, raw_mail)
                success_count += 1
                
                # 检查是否成功恢复了 body_main_text
                check_query = text("SELECT body_main_text FROM mail_cleaned WHERE mail_uid = :uid")
                new_main = db.execute(check_query, {"uid": mail_uid}).scalar()
                if new_main and new_main.strip():
                    restored_content_count += 1
                
                if success_count % 200 == 0:
                    db.commit()
                    logger.info("已完成 %d / %d 封邮件的重洗与修复...", success_count, total_to_repair)
                    
            except Exception as exc:
                db.rollback()
                logger.error("修复邮件 %s 失败: %s", mail_uid, exc)
                
        db.commit()
        logger.info("数据修复完成! 成功处理: %d 封, 成功恢复并找回正文内容: %d 封.", success_count, restored_content_count)
        
    except Exception as exc:
        logger.exception("修复任务遇到严重错误: %s", exc)
        db.rollback()
        raise exc
    finally:
        db.close()

if __name__ == "__main__":
    repair_data()

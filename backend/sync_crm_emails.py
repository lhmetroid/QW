# -*- coding: utf-8 -*-
"""
CRM (SQL Server) 邮件同步服务
- 从 SQL Server 的 usrCustomerFollowUpRecord (FollowUpMethod = 'Email') 中增量同步邮件
- 自动关联 usrCustomerContact 获取客户真实姓名和邮箱
- 写入本地 PostgreSQL 数据库 mail_raw_unified
- 自动调用 raw_comm_service.upsert_mail_cleaned 进行正文清洗和状态标记
"""
import sys
import os
import io
import re
import argparse
import logging
from datetime import datetime, timedelta, timezone

# 确保 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

# 加载 .env 环境变量
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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sync_crm_emails")

from database import SessionLocal
from crm_database import CRMSessionLocal
from sqlalchemy import text
from raw_comm_service import upsert_mail_cleaned, create_mail_batch

def _extract_subject_from_remark(remark: str, follow_up_id: str) -> str:
    """从 CustomerRemark 中利用正则提取邮件主题，如匹配不到则截断 Remark"""
    if not remark:
        return f"邮件跟进 ({follow_up_id})"
    
    # 尝试匹配 "(主题:RE: ...)"
    match = re.search(r'\(主题:([^)]+)\)', remark)
    if match:
        return match.group(1).strip()
    
    # 尝试匹配 "(PO发票付款)对账" 这种作为备选
    match_purpose = re.search(r'用途\(([^)]+)\)', remark)
    if match_purpose:
        purpose = match_purpose.group(1).strip()
        return f"邮件: {purpose}"
        
    # 如果都没匹配到，取前30个字
    clean_text = remark.strip().replace('\r', ' ').replace('\n', ' ')
    if len(clean_text) > 30:
        return clean_text[:30] + "..."
    return clean_text or f"邮件跟进 ({follow_up_id})"

def _utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()

def sync_emails_from_crm(days: int = 90, limit: int = 5000):
    logger.info("开始从 CRM (SQL Server) 增量抓取邮件数据 (最近 %d 天, 上限 %d 条)...", days, limit)
    
    pg_db = SessionLocal()
    crm_db = CRMSessionLocal()
    
    # 创建导入批次，类型设为 crm_sync
    batch_id = create_mail_batch(pg_db, source_name="CRM_SQLServer_FollowUp", import_type="crm_sync")
    logger.info("创建导入批次 ID: %d", batch_id)
    
    start_time = datetime.now() - timedelta(days=days)
    
    # SQL Server 查询语句
    crm_query = text("""
        SELECT 
            a.FollowUpId, 
            a.ContactId, 
            a.FollowUpTime, 
            a.CustomerRemark, 
            a.Note, 
            a.MsgIO, 
            a.IfSuccess,
            c.ContactName,
            c.Email as ContactEmail
        FROM usrCustomerFollowUpRecord as a
        LEFT JOIN usrCustomerContact as c on a.ContactId = c.ContactId
        WHERE a.FollowUpMethod = 'Email'
          AND a.IfSuccess = 1
          AND a.FollowUpTime >= :start_time
        ORDER BY a.FollowUpTime DESC
    """)
    
    try:
        rows = crm_db.execute(crm_query, {"start_time": start_time}).fetchall()
        logger.info("从 CRM SQL Server 查询到 %d 条符合条件的邮件跟进记录", len(rows))
        
        existing_uids_rows = pg_db.execute(text(
            "SELECT mail_uid FROM mail_raw_unified WHERE mail_uid LIKE 'sqlserver_followup_%'"
        )).fetchall()
        existing_uids = {r[0] for r in existing_uids_rows}
        logger.info("本地已存在 %d 封 CRM 邮件跟进记录，已载入内存进行高速查重", len(existing_uids))
        
        success_count = 0
        duplicate_count = 0
        failed_count = 0
        
        for row in rows[:limit]:
            follow_up_id = row[0]
            contact_id = row[1] or ""
            follow_up_time = row[2]
            customer_remark = row[3] or ""
            note = row[4] or ""
            msg_io = row[5] # 1 - inbound, 2 - outbound
            contact_name = row[7] or ""
            contact_email = (row[8] or "").strip().lower()
            
            # 1. 唯一标识符
            mail_uid = f"sqlserver_followup_{follow_up_id}"
            
            # 查重：内存高速查重
            if mail_uid in existing_uids:
                duplicate_count += 1
                continue
                
            # 2. 解析主题和正文
            subject = _extract_subject_from_remark(customer_remark, follow_up_id)
            body_text = note.strip() if note.strip() else customer_remark.strip()
            
            # 3. 路由方向
            sent_time_str = follow_up_time.isoformat() if follow_up_time else _utc_now_str()
            
            # 如果联系人邮箱为空，生成占位邮箱
            if not contact_email:
                contact_email = f"{contact_id or 'unknown'}@crm-customer.com"
                
            our_email = "sales@speed-asia.com"
            
            if msg_io == 1:
                # 客户发给我方
                from_email = contact_email
                to_emails = [our_email]
                direction = "inbound"
            else:
                # 我方发给客户
                from_email = our_email
                to_emails = [contact_email]
                direction = "outbound"
                
            # 4. 构建统一数据字典
            parsed_mail = {
                "mail_uid": mail_uid,
                "source_type": "sqlserver_email", # 标注为真实 SQL 邮件
                "source_account_id": None,
                "import_batch_id": batch_id,
                "folder_name": "crm-followup",
                "direction": direction,
                "internet_message_id": f"crm_msg_{follow_up_id}",
                "in_reply_to": None,
                "references_text": None,
                "conversation_key": "",
                "subject": subject,
                "body_text": body_text,
                "from_email": from_email,
                "to_emails": to_emails,
                "cc_emails": [],
                "sent_at": sent_time_str,
                "received_at": sent_time_str,
                "has_attachment": False,
                "raw_payload_path": f"sqlserver://followup/{follow_up_id}",
                "ingested_at": _utc_now_str()
            }
            
            try:
                # 写入 mail_raw_unified 表
                pg_db.execute(text("""
                    INSERT INTO mail_raw_unified (
                        mail_uid, source_type, source_account_id, import_batch_id, folder_name, direction,
                        internet_message_id, in_reply_to, references_text, conversation_key,
                        subject, body_text, from_email, to_emails, cc_emails,
                        sent_at, received_at, has_attachment, raw_payload_path, ingested_at
                    ) VALUES (
                        :uid, :stype, :acct, :batch, :folder, :dir,
                        :msgid, :irt, :refs, '',
                        :subj, :body, :from_, :to_, :cc_,
                        :sent, :rcvd, :att, :path, :now
                    ) ON CONFLICT (mail_uid) DO NOTHING
                """), {
                    "uid": parsed_mail["mail_uid"], "stype": parsed_mail["source_type"],
                    "acct": parsed_mail["source_account_id"], "batch": parsed_mail["import_batch_id"],
                    "folder": parsed_mail["folder_name"], "dir": parsed_mail["direction"],
                    "msgid": parsed_mail["internet_message_id"], "irt": parsed_mail["in_reply_to"],
                    "refs": parsed_mail["references_text"],
                    "subj": parsed_mail["subject"], "body": parsed_mail["body_text"],
                    "from_": parsed_mail["from_email"],
                    "to_": json_dumps(parsed_mail["to_emails"]),
                    "cc_": json_dumps(parsed_mail["cc_emails"]),
                    "sent": parsed_mail["sent_at"], "rcvd": parsed_mail["received_at"],
                    "att": parsed_mail["has_attachment"],
                    "path": parsed_mail["raw_payload_path"], "now": parsed_mail["ingested_at"]
                })
                
                # 自动触发清洗
                upsert_mail_cleaned(pg_db, parsed_mail)
                
                success_count += 1
                if success_count % 200 == 0:
                    pg_db.commit()
                    logger.info("已成功同步并清洗 %d 封 CRM 邮件...", success_count)
                    
            except Exception as exc:
                pg_db.rollback()
                failed_count += 1
                logger.error("同步/清洗单条邮件失败 %s: %s", follow_up_id, exc)
                
        # 提交最后一批未提交的更改
        pg_db.commit()
                
        pg_db.execute(text("""
            UPDATE mail_import_batch 
            SET file_count = :total, success_count = :success, failed_count = :failed, import_status = 'completed'
            WHERE id = :id
        """), {
            "total": success_count + failed_count,
            "success": success_count,
            "failed": failed_count,
            "id": batch_id
        })
        pg_db.commit()
        
        logger.info("同步完成! 新增成功: %d 封, 重复跳过: %d 封, 失败: %d 封.", success_count, duplicate_count, failed_count)
        return success_count, duplicate_count, failed_count
        
    except Exception as exc:
        logger.exception("同步 CRM 邮件总任务遇到严重错误: %s", exc)
        pg_db.execute(text("""
            UPDATE mail_import_batch 
            SET import_status = 'failed'
            WHERE id = :id
        """), {"id": batch_id})
        pg_db.commit()
        raise exc
        
    finally:
        pg_db.close()
        crm_db.close()

def json_dumps(val):
    import json
    return json.dumps(val)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CRM 邮件抓取与同步工具")
    parser.add_argument("--days", type=int, default=90, help="抓取最近多少天的邮件记录 (默认 90 天)")
    parser.add_argument("--limit", type=int, default=5000, help="单次抓取最大条数上限 (默认 5000)")
    args = parser.parse_args()
    
    try:
        sync_emails_from_crm(days=args.days, limit=args.limit)
    except Exception:
        sys.exit(1)

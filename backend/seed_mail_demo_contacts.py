"""邮件 AI 回复演示用测试案例灌库脚本（Phase 5 增强）

从 CRM 接口 fetch_crm_profile() 只读拉取 5 个不同维度的真实联系人，
脱敏后存入 PG 表 mail_demo_contact，供前端邮件质量诊断面板的 Live Demo 区做案例切换。

5 个维度:
  1. 熟联系人 · 多合同活跃     (合同 ≥ 3 + 近 30 天有 followup)
  2. 老联系人 · 单合同         (合同 1-2 张)
  3. 新联系人 · 有商机无合同   (合同 = 0 + active quotation ≥ 1)
  4. 沉默老客户               (合同 ≥ 1 + 最后 followup ≥ 180 天前)
  5. 高频活跃联系人            (近 30 天 followup ≥ 5 次)

使用:
    cd backend && python seed_mail_demo_contacts.py            # 正式灌库
    cd backend && python seed_mail_demo_contacts.py --dry-run  # 试跑不提交

CRM 数据库约束: 全程只读 (SELECT)，绝不 INSERT/UPDATE/DELETE/ALTER。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from crm_database import CRMSessionLocal  # noqa: E402
from crm_profile import fetch_crm_profile  # noqa: E402
from database import Base, MailDemoContact, SessionLocal, engine  # noqa: E402


# 5 个候选维度的选取 SQL。每个返回 TOP 候选 N 行（external_userid + contact_id 等）
# 让 Python 端选第一个能成功 fetch_crm_profile 的当结果。
DIMENSION_SQLS: list[dict] = [
    {
        "demo_index": 1,
        "demo_label": "熟联系人 · 多合同活跃",
        "demo_label_detail": "至少 3 张销售合同 + 近 30 天有跟进记录。典型推新业务场景。",
        "default_scenario": "new_business_promotion",
        "default_suite_step": 1,
        "sql": """
            SELECT TOP 30 w.external_userid, c.ContactId
            FROM usrCustomerContact c
            INNER JOIN usrCustomerContactWebChartIDRelate r ON c.ContactId=r.ContactId
            INNER JOIN usrCustomerContactWebChartList w ON r.WebChartID=w.external_userid
            WHERE c.Deleter IS NULL
              AND w.external_userid IS NOT NULL
              AND (SELECT COUNT(DISTINCT ContractId) FROM usrContract
                   WHERE ContactId=c.ContactId AND Deleter IS NULL) >= 3
              AND EXISTS (SELECT 1 FROM usrCustomerFollowUpRecord
                          WHERE ContactId=c.ContactId
                            AND FollowUpTime > DATEADD(DAY, -30, CURRENT_TIMESTAMP)
                            AND ISNULL(IfSuccess,0)=1)
            ORDER BY (SELECT COUNT(DISTINCT ContractId) FROM usrContract
                      WHERE ContactId=c.ContactId AND Deleter IS NULL) DESC
        """,
    },
    {
        "demo_index": 2,
        "demo_label": "老联系人 · 单合同",
        "demo_label_detail": "历史 1 到 2 张合同。典型唤醒续约或推增项场景。",
        "default_scenario": "re_activation",
        "default_suite_step": 1,
        "sql": """
            SELECT TOP 30 w.external_userid, c.ContactId
            FROM usrCustomerContact c
            INNER JOIN usrCustomerContactWebChartIDRelate r ON c.ContactId=r.ContactId
            INNER JOIN usrCustomerContactWebChartList w ON r.WebChartID=w.external_userid
            WHERE c.Deleter IS NULL
              AND w.external_userid IS NOT NULL
              AND (SELECT COUNT(DISTINCT ContractId) FROM usrContract
                   WHERE ContactId=c.ContactId AND Deleter IS NULL) BETWEEN 1 AND 2
            ORDER BY c.ContactId DESC
        """,
    },
    {
        "demo_index": 3,
        "demo_label": "新联系人 · 有商机无合同",
        "demo_label_detail": "0 张合同，但有进行中的商机询价。典型新接手联系人介绍场景。",
        "default_scenario": "new_contact_intro",
        "default_suite_step": 1,
        "sql": """
            SELECT TOP 30 w.external_userid, c.ContactId
            FROM usrCustomerContact c
            INNER JOIN usrCustomerContactWebChartIDRelate r ON c.ContactId=r.ContactId
            INNER JOIN usrCustomerContactWebChartList w ON r.WebChartID=w.external_userid
            WHERE c.Deleter IS NULL
              AND w.external_userid IS NOT NULL
              AND (SELECT COUNT(DISTINCT ContractId) FROM usrContract
                   WHERE ContactId=c.ContactId AND Deleter IS NULL) = 0
              AND EXISTS (SELECT 1 FROM usrQuotation
                          WHERE ContactId=c.ContactId
                            AND Deleter IS NULL
                            AND Result='Working')
            ORDER BY c.ContactId DESC
        """,
    },
    {
        "demo_index": 4,
        "demo_label": "沉默老客户",
        "demo_label_detail": "曾有合同但最后跟进超过 180 天。典型唤醒重启关系场景。",
        "default_scenario": "re_activation",
        "default_suite_step": 2,
        "sql": """
            SELECT TOP 30 w.external_userid, c.ContactId
            FROM usrCustomerContact c
            INNER JOIN usrCustomerContactWebChartIDRelate r ON c.ContactId=r.ContactId
            INNER JOIN usrCustomerContactWebChartList w ON r.WebChartID=w.external_userid
            WHERE c.Deleter IS NULL
              AND w.external_userid IS NOT NULL
              AND (SELECT COUNT(DISTINCT ContractId) FROM usrContract
                   WHERE ContactId=c.ContactId AND Deleter IS NULL) >= 1
              AND ISNULL((SELECT DATEDIFF(DAY, MAX(FollowUpTime), CURRENT_TIMESTAMP)
                          FROM usrCustomerFollowUpRecord
                          WHERE ContactId=c.ContactId AND ISNULL(IfSuccess,0)=1), 9999) >= 180
            ORDER BY c.ContactId DESC
        """,
    },
    {
        "demo_index": 5,
        "demo_label": "高频活跃联系人",
        "demo_label_detail": "近 30 天有 5 次以上有效跟进。典型推新业务或深化合作场景。",
        "default_scenario": "new_business_promotion",
        "default_suite_step": 2,
        "sql": """
            SELECT TOP 30 w.external_userid, c.ContactId
            FROM usrCustomerContact c
            INNER JOIN usrCustomerContactWebChartIDRelate r ON c.ContactId=r.ContactId
            INNER JOIN usrCustomerContactWebChartList w ON r.WebChartID=w.external_userid
            WHERE c.Deleter IS NULL
              AND w.external_userid IS NOT NULL
              AND (SELECT COUNT(*) FROM usrCustomerFollowUpRecord
                   WHERE ContactId=c.ContactId
                     AND FollowUpTime > DATEADD(DAY, -30, CURRENT_TIMESTAMP)
                     AND ISNULL(IfSuccess,0)=1) >= 5
            ORDER BY (SELECT COUNT(*) FROM usrCustomerFollowUpRecord
                      WHERE ContactId=c.ContactId
                        AND FollowUpTime > DATEADD(DAY, -30, CURRENT_TIMESTAMP)
                        AND ISNULL(IfSuccess,0)=1) DESC
        """,
    },
]


# ===== 脱敏函数 =====
def _mask_external_userid(uid: str | None, demo_index: int) -> str:
    if not uid:
        return f"DEMO-UID-{demo_index}"
    if len(uid) <= 12:
        return f"{uid[:4]}***{demo_index}"
    return f"{uid[:8]}***{uid[-4:]}"


def _mask_contact_id(cid) -> str | None:
    if cid is None:
        return None
    s = str(cid)
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]


def _mask_contact_name(name: str | None) -> str | None:
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    if len(name) <= 1:
        return name + "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" + name[-1]


def _mask_company_name(company: str | None) -> str | None:
    if not company:
        return None
    company = str(company).strip()
    if len(company) <= 4:
        return company + "***"
    return company[:4] + "***"


def _mask_contact_email(demo_index: int) -> str:
    return f"contact{demo_index}@cust-demo-{demo_index}.demo.test"


def _mask_customer_key(demo_index: int) -> str:
    return f"CUST-DEMO-FROM-CRM-{demo_index}"


# 脱敏 followup 文本里出现的手机号、邮箱、长 ID
_PATTERN_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
_PATTERN_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def _mask_freetext(text_value: str | None) -> str | None:
    if not text_value:
        return text_value
    s = str(text_value)
    s = _PATTERN_PHONE.sub("***手机***", s)
    s = _PATTERN_EMAIL.sub("***邮箱***", s)
    return s


def _desensitize_profile(profile, demo_index: int) -> dict:
    """把 CRMProfileResponse pydantic 对象转成脱敏后的 dict。"""
    data = profile.model_dump() if hasattr(profile, "model_dump") else dict(profile)
    return {
        "crm_external_userid_masked": _mask_external_userid(data.get("crm_external_userid"), demo_index),
        "crm_contact_name_masked": _mask_contact_name(data.get("crm_contact_name")),
        "company_name_masked": _mask_company_name(data.get("company_name")),
        "company_industry": data.get("company_industry"),
        "recent_opportunities_masked": _mask_freetext(data.get("recent_opportunities")),
        "ongoing_contracts_masked": _mask_freetext(data.get("ongoing_contracts")),
        "contact_recent_followup_masked": _mask_freetext(data.get("contact_recent_followup")),
        "customer_lifecycle_stage": data.get("customer_lifecycle_stage"),
        "customer_tier": data.get("customer_tier"),
        "payment_risk_level": data.get("payment_risk_level"),
        "high_risk_flags": data.get("high_risk_flags") or [],
    }


def fetch_one_candidate_for_dimension(crm_db, dim: dict):
    """对一个维度跑 SQL 拿候选列表，逐个调 fetch_crm_profile 直到成功。
    返回 (external_userid, contact_id, profile) 或 None。
    """
    rows = crm_db.execute(text(dim["sql"])).fetchall()
    print(f"  [维度{dim['demo_index']}] SQL 命中 {len(rows)} 个候选")
    for row in rows:
        external_userid = row[0]
        contact_id = row[1]
        if not external_userid:
            continue
        try:
            profile = fetch_crm_profile(external_userid, crm_db)
        except Exception as exc:
            # 个别 external_userid 可能查不到完整画像，跳过
            continue
        return external_userid, contact_id, profile
    return None


def upsert_demo_contact(pg_db, dim: dict, external_userid: str, contact_id, profile):
    """把一个维度的画像快照 upsert 进 mail_demo_contact 表。"""
    masked = _desensitize_profile(profile, dim["demo_index"])
    snapshot = {
        "source": "fetch_crm_profile",
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        **masked,
    }

    existing = (
        pg_db.query(MailDemoContact)
        .filter(MailDemoContact.demo_index == dim["demo_index"])
        .first()
    )
    new_record = existing is None
    if new_record:
        item = MailDemoContact(demo_index=dim["demo_index"])
    else:
        item = existing

    item.demo_label = dim["demo_label"]
    item.demo_label_detail = dim["demo_label_detail"]
    item.crm_external_userid_masked = masked["crm_external_userid_masked"]
    item.crm_contact_id_masked = _mask_contact_id(contact_id)
    item.contact_name_masked = masked["crm_contact_name_masked"]
    item.company_name_masked = masked["company_name_masked"]
    item.contact_email_masked = _mask_contact_email(dim["demo_index"])
    item.company_industry = masked["company_industry"]
    item.customer_lifecycle_stage = masked["customer_lifecycle_stage"]
    item.customer_tier = masked["customer_tier"]
    item.payment_risk_level = masked["payment_risk_level"]
    item.high_risk_flags = masked["high_risk_flags"]
    item.crm_profile_snapshot = snapshot
    item.default_scenario = dim["default_scenario"]
    item.default_suite_step = dim["default_suite_step"]
    item.default_seller_name = "销售测试"
    item.default_seller_signature = "销售测试\nSpeedAsia 翻译与本地化部"
    item.source_note = f"维度 SQL: {dim['demo_label']}; 候选来自 CRM 真实 external_userid 脱敏存储。"
    item.refreshed_at = datetime.utcnow()

    if new_record:
        pg_db.add(item)
        pg_db.flush()
        action = "inserted"
    else:
        action = "updated"

    return action


def main():
    parser = argparse.ArgumentParser(description="Seed mail_demo_contact from CRM (read-only)")
    parser.add_argument("--dry-run", action="store_true", help="不提交事务，只打印将要做什么")
    args = parser.parse_args()

    # 1. 确保 PG 表存在（CREATE TABLE IF NOT EXISTS）
    print("[seed] 确保 mail_demo_contact 表存在 ...")
    Base.metadata.create_all(bind=engine, tables=[MailDemoContact.__table__])
    print("[seed] mail_demo_contact 表 OK")

    # 2. 对 5 个维度依次找候选
    crm_db = CRMSessionLocal()
    pg_db = SessionLocal()
    results = []
    try:
        for dim in DIMENSION_SQLS:
            print(f"\n[seed] === 维度{dim['demo_index']}: {dim['demo_label']} ===")
            try:
                got = fetch_one_candidate_for_dimension(crm_db, dim)
            except Exception as exc:
                print(f"  [维度{dim['demo_index']}] SQL/CRM 查询失败: {exc}")
                traceback.print_exc()
                results.append((dim, None))
                continue
            if got is None:
                print(f"  [维度{dim['demo_index']}] 未找到匹配的候选联系人")
                results.append((dim, None))
                continue

            external_userid, contact_id, profile = got
            action = upsert_demo_contact(pg_db, dim, external_userid, contact_id, profile)
            print(f"  [维度{dim['demo_index']}] {action}: external_userid={_mask_external_userid(external_userid, dim['demo_index'])}, "
                  f"contact={_mask_contact_name(profile.crm_contact_name)}, "
                  f"company={_mask_company_name(profile.company_name)}, "
                  f"industry={profile.company_industry}, "
                  f"tier={profile.customer_tier}, payment_risk={profile.payment_risk_level}")
            results.append((dim, action))

        if args.dry_run:
            pg_db.rollback()
            print("\n[seed] DRY-RUN 已回滚")
        else:
            pg_db.commit()
            print("\n[seed] COMMIT 完成")

        # 3. 统计当前表里 demo 数量
        total = pg_db.query(MailDemoContact).count()
        print(f"[seed] 当前 mail_demo_contact 表共 {total} 行")

        # 4. 简要报告
        success = sum(1 for _, action in results if action in {"inserted", "updated"})
        print(f"[seed] 5 个维度成功落地: {success}/5")
    finally:
        crm_db.close()
        pg_db.close()


if __name__ == "__main__":
    main()

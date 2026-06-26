# -*- coding: utf-8 -*-
"""
客户画像接口 - 从 CRM 系统获取客户相关信息
"""
import calendar
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from crm_database import get_crm_db


router = APIRouter(prefix="/api", tags=["crm_profile"])


def _subtract_months(value: datetime, months: int) -> datetime:
    month = value.month - max(0, months)
    year = value.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, 0, 0, 0)


def _resolve_crm_setting_time_range(time_from_value, time_to_value) -> tuple[datetime, datetime]:
    if time_from_value == "RecentMonths":
        try:
            months = int(time_to_value)
        except (TypeError, ValueError):
            months = 6
        now = datetime.now()
        return _subtract_months(now, months), now

    def as_datetime(value, *, end_of_day: bool = False) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.max if end_of_day else time.min)
        parsed_date = date.fromisoformat(str(value)[:10])
        return datetime.combine(parsed_date, time.max if end_of_day else time.min)

    return as_datetime(time_from_value), as_datetime(time_to_value, end_of_day=True)


class CRMProfileResponse(BaseModel):
    """客户画像响应模型"""
    crm_external_userid: Optional[str] = None
    crm_contact_name: Optional[str] = None
    company_name: Optional[str] = None
    company_industry: Optional[str] = None
    recent_opportunities: Optional[str] = None
    recent_quote_summary: Optional[str] = None
    ongoing_contracts: Optional[str] = None
    contact_recent_followup: Optional[str] = None
    customer_lifecycle_stage: Optional[str] = None
    customer_tier: Optional[str] = None
    payment_risk_level: Optional[str] = None
    high_risk_flags: Optional[list[str]] = None


def resolve_crm_external_userid(external_userid: str, db: Session) -> str:
    """Allow a unique prefix match so historical truncated ids can still resolve to CRM."""
    normalized = (external_userid or "").strip()
    if not normalized:
        return ""

    exact_row = db.execute(
        text(
            """
            SELECT TOP 1 external_userid
            FROM usrCustomerContactWebChartList
            WHERE external_userid = :external_userid
            """
        ),
        {"external_userid": normalized},
    ).fetchone()
    if exact_row and exact_row[0]:
        return str(exact_row[0])

    if not normalized.startswith(("wm", "wo", "wb")):
        return normalized

    prefix_rows = db.execute(
        text(
            """
            SELECT DISTINCT TOP 5 external_userid
            FROM usrCustomerContactWebChartList
            WHERE external_userid LIKE :prefix
            ORDER BY external_userid
            """
        ),
        {"prefix": f"{normalized}%"},
    ).fetchall()
    candidates = [str(row[0]) for row in prefix_rows if row[0]]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise HTTPException(status_code=409, detail=f"external_userid 前缀匹配到多个 CRM 联系人: {normalized}")
    return normalized


def fetch_crm_profile(external_userid: str, db: Session) -> CRMProfileResponse:
    """根据 external_userid 获取客户 CRM 画像信息"""
    try:
        resolved_external_userid = resolve_crm_external_userid(external_userid, db)
        contact_query = text("""
            SELECT TOP 1
                c.ContactId,
                c.ContactName,
                d.CustomerId,
                d.CompanyName
            FROM usrCustomerContactWebChartIDRelate as a
            INNER JOIN usrCustomerContactWebChartList as b on a.WebChartID=b.external_userid
            INNER JOIN usrCustomerContact as c on a.ContactId=c.ContactId AND c.Deleter IS NULL
            INNER JOIN usrCustomer as d on c.CustomerId=d.CustomerId AND d.Deleter IS NULL
            WHERE b.external_userid = :external_userid
        """)

        contact_result = db.execute(contact_query, {"external_userid": resolved_external_userid}).fetchone()

        if not contact_result:
            raise HTTPException(status_code=404, detail=f"未找到 external_userid: {resolved_external_userid} 的客户信息")

        contact_id = contact_result[0]
        contact_name = contact_result[1]
        customer_id = contact_result[2]
        company_name = contact_result[3]

        opportunities_query = text("""
            SELECT TOP 1
                ISNULL(CAST(a.QuotationId AS NVARCHAR(MAX)), '') + '-' + ISNULL(CAST(a.Product AS NVARCHAR(MAX)), '') + '|负责人:' + ISNULL(CAST(a.StaffName AS NVARCHAR(MAX)), '') + '|' + ISNULL(CAST(a.BusinessDescription AS NVARCHAR(MAX)), '') as opportunities_summary
            FROM usrQuotation as a
            LEFT JOIN usrCustomerContact as b on a.ContactId=b.ContactId AND b.Deleter IS NULL
            LEFT JOIN usrCustomer as c on a.CustomerId=b.CustomerId AND c.Deleter IS NULL
            WHERE a.Deleter IS NULL
              AND a.CustomerId = :customer_id
              AND a.Result = 'Working'
            ORDER BY a.QuotationId DESC
        """)

        opportunities_result = db.execute(opportunities_query, {"customer_id": customer_id}).fetchone()
        recent_opportunities = opportunities_result[0] if opportunities_result else None

        contracts_query = text("""
            SELECT TOP 1
                ISNULL(CAST(a.ContractId AS NVARCHAR(MAX)), '') + '-业务类型:' + ISNULL(CAST(a.BusinessType AS NVARCHAR(MAX)), '') + '|' + ISNULL(CAST(a.ProductNameAll AS NVARCHAR(MAX)), '') + '|负责人:' + ISNULL(CAST(a.InChargeName AS NVARCHAR(MAX)), '') + '|' + ISNULL(CAST(a.ContractDescription AS NVARCHAR(MAX)), '') as contracts_summary
            FROM usrContract as a
            LEFT JOIN usrCustomerContact as b on a.ContactId=b.ContactId AND b.Deleter IS NULL
            LEFT JOIN usrCustomer as c on a.CustomerId=b.CustomerId AND c.Deleter IS NULL
            WHERE a.Deleter IS NULL
              AND a.CustomerId = :customer_id
              AND a.EndTime IS NOT NULL
              AND a.InputTime > DATEADD(YEAR, -1, CURRENT_TIMESTAMP)
            ORDER BY a.ContractId DESC
        """)

        contracts_result = db.execute(contracts_query, {"customer_id": customer_id}).fetchone()
        ongoing_contracts = contracts_result[0] if contracts_result else None

        last_followup_date_query = text("""
            SELECT TOP 1
                CONVERT(char(10), FollowUpTime, 21) AS follow_date,
                DATEDIFF(DAY, FollowUpTime, CURRENT_TIMESTAMP) AS days_ago
            FROM usrCustomerFollowUpRecord
            WHERE ContactId = :contact_id
              AND FollowUpTime <= CURRENT_TIMESTAMP
              AND ISNULL(IfSuccess, 0) = 1
            ORDER BY FollowUpTime DESC
        """)

        last_followup_result = db.execute(last_followup_date_query, {"contact_id": contact_id}).fetchone()

        contact_recent_followup = None

        if last_followup_result:
            follow_date = last_followup_result[0]
            days_ago = last_followup_result[1]

            followup_records_query = text("""
                SELECT
                    FollowUpId,
                    FollowUpMethod,
                    ISNULL(RemarkClass, '') AS intent,
                    ISNULL(ai_summary, ISNULL(CustomerRemark, '')) AS summary,
                    CONVERT(char(5), FollowUpTime, 108) AS time_hm,
                    ISNULL(MsgIO, 0) AS msg_io
                FROM usrCustomerFollowUpRecord
                WHERE ContactId = :contact_id
                  AND CONVERT(char(10), FollowUpTime, 21) = :follow_date
                  AND FollowUpTime <= CURRENT_TIMESTAMP
                  AND ISNULL(IfSuccess, 0) = 1
                ORDER BY FollowUpTime
            """)

            followup_records = db.execute(
                followup_records_query,
                {"contact_id": contact_id, "follow_date": follow_date}
            ).fetchall()

            if followup_records:
                if days_ago == 0:
                    date_label = "当天收到邮件之前还发生过的往来记录："
                else:
                    date_label = f"{days_ago}天前以下具体时间点发生："

                record_items = []
                for rec in followup_records:
                    time_str = rec[4]
                    method_display = _get_method_display_name(rec[1], rec[5])
                    summary = rec[3]
                    record_items.append(f"{time_str}，{method_display}，内容为：{summary}")

                contact_recent_followup = date_label + "\n" + "\n----------------------\n".join(record_items)

        customer_lifecycle_stage = _get_customer_lifecycle_stage(contact_id, db)
        company_industry = _infer_company_industry(company_name, recent_opportunities, ongoing_contracts)
        customer_tier = _infer_customer_tier(customer_lifecycle_stage, recent_opportunities, ongoing_contracts)
        payment_risk_level = _infer_payment_risk(contact_recent_followup)
        high_risk_flags = _build_high_risk_flags(payment_risk_level, customer_tier, recent_opportunities)

        return CRMProfileResponse(
            crm_external_userid=resolved_external_userid,
            crm_contact_name=contact_name,
            company_name=company_name,
            company_industry=company_industry,
            recent_opportunities=recent_opportunities,
            recent_quote_summary=recent_opportunities,
            ongoing_contracts=ongoing_contracts,
            contact_recent_followup=contact_recent_followup,
            customer_lifecycle_stage=customer_lifecycle_stage,
            customer_tier=customer_tier,
            payment_risk_level=payment_risk_level,
            high_risk_flags=high_risk_flags,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询CRM数据库出错: {str(e)}")


@router.get("/crm/profile/{external_userid}", response_model=CRMProfileResponse)
async def get_crm_profile(external_userid: str, db: Session = Depends(get_crm_db)):
    return fetch_crm_profile(external_userid, db)


def _get_method_display_name(method: str, msg_io: int) -> str:
    method_map = {
        "WebQQ": "QQ",
        "PhoneCall": "电话",
        "Email": "邮件",
        "VisitCall": "拜访",
        "SMS": "短信",
        "WeChat": "微信",
    }

    display = method_map.get(method, method)

    if method == "WebQQ" and msg_io == 2:
        display = f"截止{display}"

    return display


def _get_customer_lifecycle_stage(contact_id, db: Session) -> Optional[str]:
    """按联系人(ContactId)维度计算生命周期 — 只看这个人自己的销售合同, 不按公司汇总。

    同一家公司里不同联系人也按各自的合同数区分新人/老人, 不管公司, 只管人。

    规则：
    - 熟联系人：该联系人近 1 年有 3 个及以上销售合同。
    - 老联系人：该联系人历史上有过销售合同，不受窗口限制。
    - 新联系人：该联系人没有过销售合同。
    """
    try:
        if not contact_id:
            return None

        one_year_ago = datetime.now().replace(microsecond=0) - timedelta(days=365)
        params = {"contact_id": contact_id, "one_year_ago": one_year_ago}
        counts = db.execute(
            text("""
                SELECT
                    ISNULL(COUNT(DISTINCT ContractId), 0) AS total_contracts,
                    ISNULL(COUNT(DISTINCT CASE
                        WHEN COALESCE(ContractTime, StartTime, InputTime, DeadLine) >= :one_year_ago
                        THEN ContractId
                    END), 0) AS recent_contracts
                FROM usrContract
                WHERE Deleter IS NULL
                  AND ContractType = '销售合同'
                  AND ContactId = :contact_id
            """),
            params,
        ).fetchone()

        total_contracts = int(counts[0] or 0) if counts else 0
        recent_contracts = int(counts[1] or 0) if counts else 0
        if recent_contracts >= 3:
            return "熟联系人"
        if total_contracts > 0:
            return "老联系人"
        return "新联系人"

    except Exception:
        return None


def _infer_company_industry(company_name: Optional[str], recent_opportunities: Optional[str], ongoing_contracts: Optional[str]) -> Optional[str]:
    text_value = " ".join(filter(None, [company_name, recent_opportunities, ongoing_contracts])).lower()
    mapping = [
        ("medical", ["medical", "医院", "医学", "药", "临床"]),
        ("legal", ["law", "法律", "合同", "律所"]),
        ("manufacturing", ["factory", "制造", "工厂", "设备"]),
        ("exhibition", ["展会", "展台", "搭建"]),
        ("education", ["学校", "教育", "培训"]),
    ]
    for label, words in mapping:
        if any(word in text_value for word in words):
            return label
    return None


def _infer_customer_tier(
    lifecycle_stage: Optional[str],
    recent_opportunities: Optional[str],
    ongoing_contracts: Optional[str],
) -> Optional[str]:
    stage = lifecycle_stage or ""
    if ongoing_contracts and recent_opportunities:
        return "key"
    if any(word in stage for word in ["老联系人", "熟联系人"]):
        return "key"
    if ongoing_contracts:
        return "common"
    return None


def _infer_payment_risk(contact_recent_followup: Optional[str]) -> Optional[str]:
    text_value = (contact_recent_followup or "").lower()
    if any(word in text_value for word in ["逾期", "催款", "拖欠", "回款慢", "付款慢"]):
        return "high"
    if any(word in text_value for word in ["审批", "预算", "待确认"]):
        return "medium"
    return "low" if text_value else None


def _build_high_risk_flags(
    payment_risk_level: Optional[str],
    customer_tier: Optional[str],
    recent_opportunities: Optional[str],
) -> list[str]:
    flags: list[str] = []
    if payment_risk_level == "high":
        flags.append("payment_risk")
    if customer_tier == "key":
        flags.append("key_customer")
    if recent_opportunities and any(word in recent_opportunities for word in ["报价", "折扣", "Quotation"]):
        flags.append("historical_quote")
    return flags

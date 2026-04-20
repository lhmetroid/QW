# -*- coding: utf-8 -*-
"""
客户画像接口 - 从 CRM 系统获取客户相关信息
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from crm_database import get_crm_db


router = APIRouter(prefix="/api", tags=["crm_profile"])


class CRMProfileResponse(BaseModel):
    """客户画像响应模型"""
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


def fetch_crm_profile(external_userid: str, db: Session) -> CRMProfileResponse:
    """根据 external_userid 获取客户 CRM 画像信息"""
    try:
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

        contact_result = db.execute(contact_query, {"external_userid": external_userid}).fetchone()

        if not contact_result:
            raise HTTPException(status_code=404, detail=f"未找到 external_userid: {external_userid} 的客户信息")

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
    try:
        config_query = text("""
            SELECT TOP 1
                TimeFrom, TimeTo, ContractTimeType, QuotationTimeType,
                OldContractChecked, OldContractNumber, OldQuotationChecked, OldQuotationNumber, OldRelation,
                NewContractChecked, NewContractNumber, NewQuotationChecked, NewQuotationNumberFrom, NewQuotationNumberTo, NewRelation,
                QZContractChecked, QZQuotationChecked, QZQuotationNumberFrom, QZQuotationNumberTo, QZRelation
            FROM crmContactYeWuSetting
            WHERE ConditionType = 'Contact'
        """)

        config_result = db.execute(config_query).fetchone()
        if not config_result:
            return None

        time_from = config_result[0]
        time_to = config_result[1]
        contract_time_type = config_result[2]
        quotation_time_type = config_result[3]

        old_contract_number = float(config_result[5]) if config_result[4] == "是" else -1
        old_quotation_number = float(config_result[7]) if config_result[6] == "是" else -1
        old_relation = config_result[8]

        new_contract_number = float(config_result[10]) if config_result[9] == "是" else -1
        new_quotation_from = float(config_result[12]) if config_result[11] == "是" else -1
        new_quotation_to = float(config_result[13]) if config_result[11] == "是" else -1
        new_relation = config_result[14]

        qz_contract_checked = config_result[15]
        qz_quotation_checked = config_result[16]
        qz_quotation_from = float(config_result[17]) if config_result[16] == "是" else -1
        qz_quotation_to = float(config_result[18]) if config_result[16] == "是" else -1
        qz_relation = config_result[19]

        if contract_time_type == "endtime":
            contract_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.ContractId), 0) as ContractCount
                FROM usrContract a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.DeadLine, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.DeadLine, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContractType = '销售合同'
                  AND a.ContactId = :contact_id
            """)
        else:
            contract_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.ContractId), 0) as ContractCount
                FROM usrContract a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.StartTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.StartTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContractType = '销售合同'
                  AND a.ContactId = :contact_id
            """)

        if quotation_time_type == "endtime":
            quotation_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.QuotationId), 0) as QuotationCount
                FROM usrQuotation a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.EndTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.EndTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContactId = :contact_id
            """)
        else:
            quotation_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.QuotationId), 0) as QuotationCount
                FROM usrQuotation a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.QuotationTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.QuotationTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContactId = :contact_id
            """)

        params = {"time_from": time_from, "time_to": time_to, "contact_id": contact_id}

        contract_result = db.execute(contract_count_query, params).fetchone()
        contract_count = float(contract_result[0]) if contract_result else 0

        quotation_result = db.execute(quotation_count_query, params).fetchone()
        quotation_count = float(quotation_result[0]) if quotation_result else 0

        if old_contract_number != -1:
            if old_quotation_number != -1:
                if old_relation == "是":
                    if contract_count >= old_contract_number and quotation_count >= old_quotation_number:
                        return "老联系人"
                else:
                    if contract_count >= old_contract_number or quotation_count >= old_quotation_number:
                        return "老联系人"
            else:
                if contract_count >= old_contract_number:
                    return "老联系人"
        else:
            if old_quotation_number != -1 and quotation_count >= old_quotation_number:
                return "老联系人"

        if new_contract_number != -1:
            if new_quotation_from != -1:
                if new_relation == "是":
                    if contract_count >= new_contract_number and new_quotation_from <= quotation_count <= new_quotation_to:
                        return "熟联系人"
                else:
                    if contract_count >= new_contract_number or (new_quotation_from <= quotation_count <= new_quotation_to):
                        return "熟联系人"
            else:
                if contract_count >= new_contract_number:
                    return "熟联系人"
        else:
            if new_quotation_from != -1 and new_quotation_from <= quotation_count <= new_quotation_to:
                return "熟联系人"

        if qz_contract_checked == "是" or qz_quotation_checked == "是":
            if qz_contract_checked == "是" and qz_quotation_checked == "是":
                if qz_relation == "是":
                    if contract_count >= 0 and qz_quotation_from <= quotation_count <= qz_quotation_to:
                        return "新联系人"
                else:
                    if contract_count >= 0 or (qz_quotation_from <= quotation_count <= qz_quotation_to):
                        return "新联系人"
            elif qz_contract_checked == "是":
                if contract_count >= 0:
                    return "新联系人"
            elif qz_quotation_checked == "是":
                if qz_quotation_from <= quotation_count <= qz_quotation_to:
                    return "新联系人"

        return None

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

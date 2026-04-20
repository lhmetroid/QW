# backend/routers/crm_profile.py
# -*- coding: utf-8 -*-
"""
客户画像接口 - 从CRM系统获取客户相关信息
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from crm_database import get_crm_db

router = APIRouter(tags=["crm_profile"])


class CRMProfileResponse(BaseModel):
    """客户画像响应模型"""
    crm_contact_name: Optional[str] = None  # 客户真名
    company_name: Optional[str] = None  # 客户所属企业主体名称
    recent_opportunities: Optional[str] = None  # 近期处于跟进中的商机名称/概述
    ongoing_contracts: Optional[str] = None  # 正在执行中的合同简述
    contact_recent_followup: Optional[str] = None  # 近期手动跟进概要
    customer_lifecycle_stage: Optional[str] = None  # 客户业务生命周期状态：新客/VIP/挽留/开发期/成熟期


@router.get("/crm/profile/{external_userid}", response_model=CRMProfileResponse)
async def get_crm_profile(external_userid: str, db: Session = Depends(get_crm_db)):
    """
    根据 external_userid 获取客户CRM画像信息

    Args:
        external_userid: 外部用户ID（来自企业微信等外部系统），对应 WebChartID

    Returns:
        CRMProfileResponse: 客户画像数据
    """
    try:
        # 获取联系人名称和公司名称
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

        # 获取近期商机（跟进中的报价）
        opportunities_query = text("""
            SELECT TOP 1
                CONCAT(a.QuotationId, '-', a.Product, '|负责人:', a.StaffName, '|', a.BusinessDescription) as opportunities_summary
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

        # 获取执行中的合同
        contracts_query = text("""
            SELECT TOP 1
                CONCAT(a.ContractId, '-业务类型:', a.BusinessType, '|', a.ProductNameAll, '|负责人:', a.InChargeName, '|', a.ContractDescription) as contracts_summary
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

        # 获取最近跟进记录 - 第一步：找最近一个有跟进记录的日期
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

            # 第二步：获取该日期的所有跟进记录
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
                # 构建日期标签
                if days_ago == 0:
                    date_label = "当天收到邮件之前还发生过的往来记录："
                else:
                    date_label = f"{days_ago}天前以下具体时间点发生："

                # 构建记录列表，格式：时间，方式，内容为：概要
                record_items = []
                for rec in followup_records:
                    time_str = rec[4]  # time_hm
                    method_display = _get_method_display_name(rec[1], rec[5])  # FollowUpMethod, MsgIO
                    summary = rec[3]  # summary
                    record_items.append(f"{time_str}，{method_display}，内容为：{summary}")

                # 拼接最终结果，用\n分隔（Python中用\n代替\r\n）
                contact_recent_followup = date_label + "\n" + "\n----------------------\n".join(record_items)

        # 获取客户生命周期阶段
        customer_lifecycle_stage = _get_customer_lifecycle_stage(contact_id, db)

        return CRMProfileResponse(
            crm_contact_name=contact_name,
            company_name=company_name,
            recent_opportunities=recent_opportunities,
            ongoing_contracts=ongoing_contracts,
            contact_recent_followup=contact_recent_followup,
            customer_lifecycle_stage=customer_lifecycle_stage
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询CRM数据库出错: {str(e)}")


def _get_method_display_name(method: str, msg_io: int) -> str:
    """
    根据跟进方式和消息方向获取显示名称

    Args:
        method: 跟进方式（如：WebQQ, PhoneCall, Email等）
        msg_io: 消息方向（0=无, 1=进, 2=出等）

    Returns:
        显示名称
    """
    method_map = {
        "WebQQ": "QQ",
        "PhoneCall": "电话",
        "Email": "邮件",
        "VisitCall": "拜访",
        "SMS": "短信",
        "WeChat": "微信",
    }

    display = method_map.get(method, method)

    # 如果是WebQQ且msg_io为2，表示截止时间
    if method == "WebQQ" and msg_io == 2:
        display = f"截止{display}"

    return display


def _get_customer_lifecycle_stage(contact_id, db: Session) -> Optional[str]:
    """
    根据联系人在一定时间范围内的合同和报价数量，判断其生命周期阶段

    算法说明：
    1. 从crmContactYeWuSetting表读取配置（时间范围、数量标准、合并关系等）
    2. 查询指定时间范围内的合同和报价数量
    3. 根据配置逐级判断：老联系人 -> 熟联系人 -> 新联系人

    Args:
        contact_id: 联系人ID
        db: 数据库会话

    Returns:
        生命周期阶段：老联系人、熟联系人、新联系人 或 None
    """
    try:
        # 第一步：获取配置信息
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

        # 解析配置
        time_from = config_result[0]
        time_to = config_result[1]
        contract_time_type = config_result[2]  # endtime 或 starttime
        quotation_time_type = config_result[3]  # endtime 或 starttime

        # 老客户配置
        old_contract_number = float(config_result[5]) if config_result[4] == "是" else -1
        old_quotation_number = float(config_result[7]) if config_result[6] == "是" else -1
        old_relation = config_result[8]  # "是"(AND) 或其他(OR)

        # 熟客户配置（标记为New在配置中）
        new_contract_number = float(config_result[10]) if config_result[9] == "是" else -1
        new_quotation_from = float(config_result[12]) if config_result[11] == "是" else -1
        new_quotation_to = float(config_result[13]) if config_result[11] == "是" else -1
        new_relation = config_result[14]

        # 新客户配置（标记为QZ）
        qz_contract_checked = config_result[15]
        qz_quotation_checked = config_result[16]
        qz_quotation_from = float(config_result[17]) if config_result[16] == "是" else -1
        qz_quotation_to = float(config_result[18]) if config_result[16] == "是" else -1
        qz_relation = config_result[19]

        # 第二步：构建并执行合同查询
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
        else:  # starttime
            contract_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.ContractId), 0) as ContractCount
                FROM usrContract a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.StartTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.StartTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContractType = '销售合同'
                  AND a.ContactId = :contact_id
            """)

        # 第三步：构建并执行报价查询
        if quotation_time_type == "endtime":
            quotation_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.QuotationId), 0) as QuotationCount
                FROM usrQuotation a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.EndTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.EndTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContactId = :contact_id
            """)
        else:  # starttime
            quotation_count_query = text("""
                SELECT ISNULL(COUNT(DISTINCT a.QuotationId), 0) as QuotationCount
                FROM usrQuotation a
                WHERE a.Deleter IS NULL
                  AND CONVERT(char(10), a.QuotationTime, 21) >= CONVERT(char(10), :time_from, 121)
                  AND CONVERT(char(10), a.QuotationTime, 21) <= CONVERT(char(10), :time_to, 121)
                  AND a.ContactId = :contact_id
            """)

        # 执行查询获取数量
        params = {"time_from": time_from, "time_to": time_to, "contact_id": contact_id}

        contract_result = db.execute(contract_count_query, params).fetchone()
        contract_count = float(contract_result[0]) if contract_result else 0

        quotation_result = db.execute(quotation_count_query, params).fetchone()
        quotation_count = float(quotation_result[0]) if quotation_result else 0

        # 第四步：根据配置和计数判断阶段

        # 判断老联系人
        if old_contract_number != -1:
            if old_quotation_number != -1:
                if old_relation == "是":  # AND 关系
                    if contract_count >= old_contract_number and quotation_count >= old_quotation_number:
                        return "老联系人"
                else:  # OR 关系
                    if contract_count >= old_contract_number or quotation_count >= old_quotation_number:
                        return "老联系人"
            else:
                if contract_count >= old_contract_number:
                    return "老联系人"
        else:
            if old_quotation_number != -1 and quotation_count >= old_quotation_number:
                return "老联系人"

        # 判断熟联系人
        if new_contract_number != -1:
            if new_quotation_from != -1:
                if new_relation == "是":  # AND 关系
                    if contract_count >= new_contract_number and new_quotation_from <= quotation_count <= new_quotation_to:
                        return "熟联系人"
                else:  # OR 关系
                    if contract_count >= new_contract_number or (new_quotation_from <= quotation_count <= new_quotation_to):
                        return "熟联系人"
            else:
                if contract_count >= new_contract_number:
                    return "熟联系人"
        else:
            if new_quotation_from != -1 and new_quotation_from <= quotation_count <= new_quotation_to:
                return "熟联系人"

        # 判断新联系人
        if qz_contract_checked == "是" or qz_quotation_checked == "是":
            if qz_contract_checked == "是" and qz_quotation_checked == "是":
                if qz_relation == "是":  # AND 关系
                    if contract_count >= 0 and qz_quotation_from <= quotation_count <= qz_quotation_to:
                        return "新联系人"
                else:  # OR 关系
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

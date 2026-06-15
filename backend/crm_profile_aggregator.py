# -*- coding: utf-8 -*-
"""Realtime CRM profile aggregator for the WeCom reply flow.

This adapts ``other/crm_profile_aggregator_standalone.py`` to the existing
backend CRM connection. It is read-only, keeps only an in-process day cache,
and returns JSON-safe values for API payloads and JSON columns.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text

from crm_database import CRMSessionLocal


_BASE_COLS = [
    "contact_id",
    "contact_name",
    "duty",
    "division",
    "contact_type",
    "customer_id",
    "company_name",
    "business",
    "scale",
    "category",
    "company_property",
    "customer_from",
    "source_tag",
]


def _resolve_base(db, external_userid: Optional[str], contact_id: Any) -> Optional[dict[str, Any]]:
    sel = """SELECT TOP 1 c.ContactId, c.ContactName, c.Duty, c.Division, c.ContactType,
               d.CustomerId, d.CompanyName, d.Business, d.Scale, d.Category, d.CompanyProperty,
               d.CustomerFrom, d.SourceTag """
    if contact_id is not None:
        row = db.execute(
            text(
                sel
                + """FROM usrCustomerContact c
                 LEFT JOIN usrCustomer d ON c.CustomerId=d.CustomerId AND d.Deleter IS NULL
                 WHERE c.ContactId=:cid AND c.Deleter IS NULL"""
            ),
            {"cid": contact_id},
        ).fetchone()
    else:
        row = db.execute(
            text(
                sel
                + """FROM usrCustomerContactWebChartIDRelate a
                 INNER JOIN usrCustomerContactWebChartList b ON a.WebChartID=b.external_userid
                 INNER JOIN usrCustomerContact c ON a.ContactId=c.ContactId AND c.Deleter IS NULL
                 LEFT JOIN usrCustomer d ON c.CustomerId=d.CustomerId AND d.Deleter IS NULL
                 WHERE b.external_userid=:uid"""
            ),
            {"uid": external_userid},
        ).fetchone()
    return dict(zip(_BASE_COLS, row)) if row else None


def _contracts(db, customer_id: Any, contact_id: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        # 公司级汇总：成交单数 / 历史成交额 / 最近成交时间（代表整个公司关系，口径不变）。
        # 未开票额改口径：只计【仍有应收账款】(IsReceived=0/未回款) 的未开票，
        #   剔除"已回款/已销账但未开票"(如国外付款历史不开票)——它们 IsReceived=1，不是待跟进未开票。
        row = db.execute(
            text(
                """SELECT COUNT(*) cnt, SUM(OriginalMoney) total, MAX(ContractTime) last_t,
                          SUM(UnInvoicedMoney) uninvoiced_raw,
                          SUM(CASE WHEN IsReceived=0 THEN UnInvoicedMoney ELSE 0 END) uninvoiced_due
                   FROM usrContract WHERE CustomerId=:cid AND Deleter IS NULL"""
            ),
            {"cid": customer_id},
        ).fetchone()
        if row:
            out.update(
                contract_count=row[0] or 0,
                contract_total_money=row[1],
                last_contract_time=row[2],
                uninvoiced_money_raw=row[3],
                uninvoiced_money=row[4],
            )

        # 首次成交时间改口径：先按【联系人】取其与本司的首单，查不到再回退【公司级】首单。
        # （公司级 MIN 易被其它联系人的历史脏数据污染，如 ERP 上线前误录的 2002 年合同。）
        first_t = None
        first_src = None
        if contact_id is not None:
            first_t = db.execute(
                text(
                    """SELECT MIN(ContractTime) FROM usrContract
                       WHERE ContactId=:ctid AND Deleter IS NULL"""
                ),
                {"ctid": contact_id},
            ).scalar()
            if first_t is not None:
                first_src = "联系人级"
        if first_t is None:
            first_t = db.execute(
                text(
                    """SELECT MIN(ContractTime) FROM usrContract
                       WHERE CustomerId=:cid AND Deleter IS NULL"""
                ),
                {"cid": customer_id},
            ).scalar()
            if first_t is not None:
                first_src = "公司级"
        out["first_contract_time"] = first_t
        out["first_contract_time_source"] = first_src
    except Exception as exc:
        out["contracts_error"] = str(exc)[:120]

    try:
        rows = db.execute(
            text(
                """SELECT TOP 60 ProductNameAll FROM usrContract
                   WHERE CustomerId=:cid AND Deleter IS NULL
                     AND ProductNameAll IS NOT NULL AND LTRIM(RTRIM(ProductNameAll))<>''
                   ORDER BY ContractTime DESC"""
            ),
            {"cid": customer_id},
        ).fetchall()
        seen: list[str] = []
        for (raw,) in rows:
            for piece in re.split(r"[;；、,，/]+", str(raw)):
                piece = piece.strip()
                if piece and piece not in seen:
                    seen.append(piece)
        out["cooperated_products"] = seen[:8]
    except Exception:
        out["cooperated_products"] = []
    return out


def _quotations(db, customer_id: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        row = db.execute(
            text(
                """SELECT COUNT(*) cnt, MAX(QuotationTime) last_t
                   FROM usrQuotation WHERE CustomerId=:cid AND Deleter IS NULL"""
            ),
            {"cid": customer_id},
        ).fetchone()
        if row:
            out.update(quotation_count=row[0] or 0, last_quotation_time=row[1])
    except Exception as exc:
        out["quotation_error"] = str(exc)[:120]

    try:
        succ = db.execute(
            text(
                """SELECT AVG(CAST(SuccessRate AS float)) FROM usrQuotation
                   WHERE CustomerId=:cid AND Deleter IS NULL
                     AND SuccessRate IS NOT NULL AND ISNUMERIC(SuccessRate)=1"""
            ),
            {"cid": customer_id},
        ).scalar()
        out["avg_success_rate"] = succ
    except Exception:
        out["avg_success_rate"] = None

    try:
        rows = db.execute(
            text(
                """SELECT TOP 5 ProductTypes FROM usrQuotation
                   WHERE CustomerId=:cid AND Deleter IS NULL
                     AND ProductTypes IS NOT NULL AND LTRIM(RTRIM(ProductTypes))<>''
                   ORDER BY QuotationTime DESC"""
            ),
            {"cid": customer_id},
        ).fetchall()
        out["recent_quote_products"] = [row[0] for row in rows][:5]
    except Exception:
        out["recent_quote_products"] = []
    return out


def _followups(db, contact_id: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        row = db.execute(
            text(
                """SELECT COUNT(*) cnt, MAX(FollowUpTime) last_t
                   FROM usrCustomerFollowUpRecord WHERE ContactId=:cid AND Deleter IS NULL"""
            ),
            {"cid": contact_id},
        ).fetchone()
        if row:
            out.update(followup_count=row[0] or 0, last_followup_time=row[1])
    except Exception as exc:
        out["followup_error"] = str(exc)[:120]

    try:
        rows = db.execute(
            text(
                """SELECT TOP 3 CustomerRemark, FollowUpTime FROM usrCustomerFollowUpRecord
                   WHERE ContactId=:cid AND Deleter IS NULL
                     AND CustomerRemark IS NOT NULL AND LTRIM(RTRIM(CustomerRemark))<>''
                   ORDER BY FollowUpTime DESC"""
            ),
            {"cid": contact_id},
        ).fetchall()
        out["recent_followups"] = [
            {"remark": str(row[0])[:120], "time": str(row[1])}
            for row in rows
        ]
    except Exception:
        out["recent_followups"] = []
    return out


def _account_period(db, contact_id: Any, customer_id: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"account_time": 60, "account_period_source": "默认60天"}

    def query_period(key: Any, types_sql: str) -> Optional[int]:
        row = db.execute(
            text(
                f"""SELECT TOP 1 Account FROM usrCustomerAccountAndDiscountHistory
                    WHERE CustomerId=:k AND CustomerType IN ({types_sql})
                      AND Account IS NOT NULL AND StartTime<=GETDATE()
                    ORDER BY StartTime DESC"""
            ),
            {"k": key},
        ).fetchone()
        if row and row[0] is not None:
            try:
                return int(float(row[0]))
            except (TypeError, ValueError):
                return None
        return None

    try:
        if contact_id is not None:
            value = query_period(contact_id, "N'客户联系人'")
            if value is not None:
                return {"account_time": value, "account_period_source": "联系人级"}
        if customer_id:
            value = query_period(customer_id, "N'客户公司', N'公司组'")
            if value is not None:
                return {"account_time": value, "account_period_source": "公司级"}
    except Exception as exc:
        out["account_period_error"] = str(exc)[:120]
    return out


def aggregate_profile(external_userid: Optional[str] = None, contact_id: Any = None) -> Optional[dict[str, Any]]:
    if not external_userid and contact_id is None:
        return None
    db = CRMSessionLocal()
    try:
        base = _resolve_base(db, external_userid, contact_id)
        if not base:
            return None
        profile = dict(base)
        customer_id = base.get("customer_id")
        resolved_contact_id = base.get("contact_id")
        if customer_id:
            profile.update(_contracts(db, customer_id, resolved_contact_id))
            profile.update(_quotations(db, customer_id))
        if resolved_contact_id is not None:
            profile.update(_followups(db, resolved_contact_id))
        profile.update(_account_period(db, resolved_contact_id, customer_id))
        followup_count = profile.get("followup_count") or 0
        profile["relationship_level"] = (
            "熟客" if followup_count >= 20 else ("有往来" if followup_count >= 5 else "新客/少往来")
        )
        return _json_safe(profile)
    finally:
        db.close()


def _clean(value: Any) -> Optional[str]:
    text_value = str(value or "").strip()
    if not text_value or text_value in {"0", "待定", "未知", "无", "0)待定"} or text_value.startswith("0)"):
        return None
    return text_value


def _fmt_money(value: Any) -> Optional[str]:
    try:
        return f"约{float(value):,.0f}元" if value not in (None, "") else None
    except Exception:
        return None


def build_profile_text(profile: Optional[dict[str, Any]]) -> str:
    """Build the full profile text used by the current WeCom prompt.

    User requirement for this integration is to keep exact historical money
    facts visible instead of masking them.
    """
    if not profile:
        return ""
    lines: list[str] = []
    if profile.get("company_name"):
        line = f"公司：{profile['company_name']}"
        extras = [
            value
            for value in [
                _clean(profile.get("business")),
                _clean(profile.get("scale")),
                _clean(profile.get("company_property")),
            ]
            if value
        ]
        if extras:
            line += "（" + "·".join(map(str, extras)) + "）"
        lines.append(line)
    if profile.get("contact_name"):
        contact = f"联系人：{profile['contact_name']}"
        if profile.get("duty"):
            contact += f"（{profile['duty']}）"
        lines.append(contact)
    lines.append(
        f"关系：{profile.get('relationship_level', '')}，累计跟进{profile.get('followup_count', 0)}次"
        + (f"，最近联系{str(profile.get('last_followup_time'))[:10]}" if profile.get("last_followup_time") else "")
    )
    if profile.get("contract_count"):
        segment = f"合作：成交{profile['contract_count']}单"
        total_money = _fmt_money(profile.get("contract_total_money"))
        if total_money:
            segment += f"，历史成交{total_money}"
        if profile.get("first_contract_time"):
            segment += f"，首次成交{str(profile['first_contract_time'])[:10]}"
        if profile.get("last_contract_time"):
            segment += f"，最近成交{str(profile['last_contract_time'])[:10]}"
        lines.append(segment)
    if profile.get("cooperated_products"):
        lines.append("合作产品：" + "、".join(map(str, profile["cooperated_products"][:6])))
    if profile.get("avg_success_rate") is not None:
        try:
            lines.append(f"报价成功率：约{float(profile['avg_success_rate']):.0f}%")
        except Exception:
            pass
    if profile.get("uninvoiced_money"):
        try:
            uninvoiced = float(profile["uninvoiced_money"])
        except Exception:
            uninvoiced = 0
        if uninvoiced > 0:
            lines.append(f"未开票额：{_fmt_money(profile.get('uninvoiced_money'))}")
    if _clean(profile.get("account_time")):
        lines.append(f"账期：{profile['account_time']}天")
    if profile.get("customer_from") or profile.get("source_tag"):
        lines.append("来源：" + str(profile.get("customer_from") or profile.get("source_tag")))
    return ("【客户画像（聚合）】\n" + "\n".join(lines)) if lines else ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


_DAY_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_CACHE_MAX = 20000


def get_realtime_profile(
    external_userid: Optional[str] = None,
    contact_id: Any = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    key = f"u:{external_userid}" if external_userid else f"c:{contact_id}"
    today = datetime.date.today().isoformat()
    if not force_refresh:
        cached = _DAY_CACHE.get(key)
        if cached and cached[0] == today:
            return {**cached[1], "cached": True}

    profile = aggregate_profile(external_userid=external_userid, contact_id=contact_id)
    full_text = build_profile_text(profile)
    result = {
        "found": bool(profile),
        "text": full_text,
        "model_text": full_text,
        "data": profile or {},
        "computed_date": today,
    }
    if len(_DAY_CACHE) >= _CACHE_MAX:
        _DAY_CACHE.clear()
    _DAY_CACHE[key] = (today, result)
    return {**result, "cached": False}

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

FACT_SOURCE_TYPES = {"message_extract", "thread_fact", "crm_fact", "attachment_fact"}
EMAILISH_SOURCE_TYPES = {"email_excel", "email_digest", "excellent_reply_extract"}
REPLYABLE_LIBRARY_TYPES = {"reference"}
ATTACHMENT_KEYWORDS = ["附件", "报价单", "合同", "PO", "pdf", "doc", "docx", "xls", "xlsx", "zip", "文件"]
QUOTE_KEYWORDS = ["报价", "quote", "含税", "未税", "单价", "价格", "费用", "PO", "采购单"]
PAYMENT_KEYWORDS = ["付款", "打款", "回款", "到账", "首付", "尾款", "发票", "对公"]
SHIPMENT_KEYWORDS = ["发货", "物流", "快递", "顺丰", "寄出", "到货", "在途"]
AFTER_SALES_KEYWORDS = ["售后", "投诉", "返工", "异常", "补偿", "问题", "抱怨", "退款"]
CAPABILITY_KEYWORDS = ["能做", "可做", "支持", "擅长", "经验", "案例"]
PROCESS_KEYWORDS = ["流程", "步骤", "安排", "交付", "周期", "排期", "如何"]
PRICE_COMMITMENT_PATTERNS = [
    r"按\s*\d+(?:\.\d+)?\s*元",
    r"就按这个价格",
    r"直接给您报价",
    r"可以按.*报价",
    r"确认.*价格",
]
PAYMENT_DONE_PATTERNS = [r"已到账", r"已经收到款", r"款已经到了", r"回款已确认"]
SHIPMENT_DONE_PATTERNS = [r"已发货", r"已经寄出", r"在路上了", r"物流已安排"]
AFTER_SALES_DONE_PATTERNS = [r"售后已经处理", r"补偿已经安排", r"问题已经解决"]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clamp_score(value: float, digits: int = 4) -> float:
    return round(max(0.0, min(1.0, float(value))), digits)


def merge_tags(tags: dict | None, **extra: Any) -> dict | None:
    merged = dict(tags or {})
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        merged[key] = value
    return merged or None


def infer_library_type(
    *,
    source_type: str | None,
    knowledge_type: str | None,
    chunk_type: str | None,
    tags: dict | None = None,
) -> str:
    explicit = _text((tags or {}).get("library_type")).lower()
    if explicit in {"reference", "fact"}:
        return explicit
    if _text(source_type) in FACT_SOURCE_TYPES:
        return "fact"
    if _text(chunk_type) in {"template", "rule", "faq", "definition", "example", "constraint"}:
        return "reference"
    if _text(knowledge_type) in {"pricing", "capability", "process", "faq"}:
        return "reference"
    return "reference"


def infer_function_fragment(
    *,
    title: str | None,
    content: str | None,
    source_type: str | None,
    tags: dict | None = None,
) -> str | None:
    explicit = _text((tags or {}).get("function_fragment")).lower()
    if explicit:
        return explicit
    title_text = _text(title).lower()
    content_text = _text(content).lower()
    haystack = f"{title_text}\n{content_text}"
    if _text(source_type) not in EMAILISH_SOURCE_TYPES and "邮件" not in haystack and "dear " not in haystack:
        return None
    if any(word in haystack for word in ["hello", "hi ", "dear ", "您好", "您好，", "问候"]):
        return "greeting"
    if any(word in haystack for word in ["背景", "情况", "前情", "目前", "需求如下"]):
        return "background"
    if any(word in haystack for word in ["亮点", "优势", "案例", "经验", "保障"]):
        return "highlight"
    if any(word in haystack for word in ["请确认", "烦请", "欢迎", "期待", "是否方便", "call to action", "下一步"]):
        return "cta"
    if any(word in haystack for word in ["祝好", "此致", "best regards", "谢谢", "感谢"]):
        return "closing"
    if any(word in haystack for word in ["回复", "建议", "方案", "报价", "安排", "可支持"]):
        return "core_answer"
    return "background"


def infer_scenario_intent(
    *,
    title: str | None,
    content: str | None,
    tags: dict | None = None,
) -> tuple[str | None, str | None, str | None]:
    tags = tags or {}
    text = f"{_text(title)}\n{_text(content)}"
    scenario = _text(tags.get("scenario_label") or tags.get("scenario")).lower() or None
    intent = _text(tags.get("intent_label") or tags.get("intent_type")).lower() or None
    style = _text(tags.get("language_style")).lower() or None
    if not scenario:
        if any(word in text for word in QUOTE_KEYWORDS):
            scenario = "quotation"
        elif any(word in text for word in PAYMENT_KEYWORDS):
            scenario = "payment"
        elif any(word in text for word in SHIPMENT_KEYWORDS):
            scenario = "shipment"
        elif any(word in text for word in AFTER_SALES_KEYWORDS):
            scenario = "after_sales"
        elif any(word in text for word in PROCESS_KEYWORDS):
            scenario = "process"
        elif any(word in text for word in CAPABILITY_KEYWORDS):
            scenario = "capability"
    if not intent:
        if any(word in text for word in ["案例", "经验", "客户案例", "项目案例"]):
            intent = "example"
        elif any(word in text for word in QUOTE_KEYWORDS):
            intent = "pricing"
        elif any(word in text for word in PROCESS_KEYWORDS):
            intent = "process"
        elif any(word in text for word in CAPABILITY_KEYWORDS):
            intent = "capability"
        else:
            intent = scenario
    if not style:
        style = "formal_email" if any(word in text.lower() for word in ["dear ", "best regards", "您好", "请您"]) else "concise_wechat"
    return scenario, intent, style


def detect_mixed_knowledge(content: str | None, tags: dict | None = None) -> dict[str, Any]:
    text = _text(content)
    lower = text.lower()
    categories = set()
    if any(word in text for word in QUOTE_KEYWORDS):
        categories.add("pricing")
    if any(word in text for word in PAYMENT_KEYWORDS):
        categories.add("payment")
    if any(word in text for word in SHIPMENT_KEYWORDS):
        categories.add("shipment")
    if any(word in text for word in AFTER_SALES_KEYWORDS):
        categories.add("after_sales")
    if any(word in text for word in CAPABILITY_KEYWORDS):
        categories.add("capability")
    if any(word in text for word in PROCESS_KEYWORDS):
        categories.add("process")
    if any(word in lower for word in ["案例", "case study", "客户案例", "项目案例"]):
        categories.add("example")
    mixed = len(categories) >= 3
    return {"mixed": mixed, "categories": sorted(categories)}


def score_content_governance(
    *,
    title: str | None,
    content: str | None,
    knowledge_type: str | None,
    chunk_type: str | None,
    source_type: str | None,
    tags: dict | None = None,
    pricing_rule: dict | None = None,
    has_source_ref: bool = False,
    metadata: dict | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    text = _text(content)
    title_text = _text(title)
    library_type = infer_library_type(
        source_type=source_type,
        knowledge_type=knowledge_type,
        chunk_type=chunk_type,
        tags=tags,
    )
    fragment = infer_function_fragment(title=title, content=content, source_type=source_type, tags=tags)
    metadata_fields = [
        metadata.get("business_line"),
        metadata.get("language_pair"),
        metadata.get("service_scope"),
        metadata.get("customer_tier"),
        (tags or {}).get("scenario_label"),
        (tags or {}).get("intent_label"),
        (tags or {}).get("thread_id"),
    ]
    metadata_ratio = sum(1 for item in metadata_fields if _text(item)) / max(len(metadata_fields), 1)
    text_len = len(text)
    sentence_count = len([item for item in re.split(r"[。！？!?;\n]+", text) if item.strip()])
    title_bonus = 0.15 if title_text else 0.0
    clarity = 0.35 + title_bonus + min(text_len / 500.0, 0.3) + min(sentence_count / 6.0, 0.2)
    completeness = 0.25 + (metadata_ratio * 0.35) + (0.2 if text_len >= 40 else 0.0) + (0.2 if pricing_rule else 0.0)
    if fragment:
        completeness += 0.1
    evidence = 0.3 + (0.2 if has_source_ref else 0.0) + (0.25 if pricing_rule else 0.0) + (metadata_ratio * 0.2)
    if library_type == "fact":
        evidence += 0.05
    reusability = 0.3 + min(text_len / 600.0, 0.2) + (0.2 if fragment else 0.0) + (0.2 if library_type == "reference" else -0.05)
    if re.search(r"[\d]{4,}|[A-Z]{3,}", text):
        reusability -= 0.08
    if any(word in text for word in ["这个客户", "该客户", "本次这单", "这票"]):
        reusability -= 0.06
    mixed = detect_mixed_knowledge(content, tags)
    if mixed["mixed"]:
        clarity -= 0.12
        completeness -= 0.08
        reusability -= 0.15
    clarity = clamp_score(clarity)
    completeness = clamp_score(completeness)
    evidence = clamp_score(evidence)
    reusability = clamp_score(reusability)
    useful = clamp_score((clarity * 0.25) + (completeness * 0.3) + (reusability * 0.2) + (evidence * 0.25))
    publishable = useful >= 0.58 and evidence >= 0.5 and not mixed["mixed"]
    allowed_for_generation = library_type in REPLYABLE_LIBRARY_TYPES and useful >= 0.65 and not mixed["mixed"]
    usable_for_reply = allowed_for_generation and reusability >= 0.55 and evidence >= 0.58
    return {
        "library_type": library_type,
        "function_fragment": fragment,
        "topic_clarity_score": clarity,
        "completeness_score": completeness,
        "reusability_score": reusability,
        "evidence_reliability_score": evidence,
        "useful_score": useful,
        "publishable": publishable,
        "allowed_for_generation": allowed_for_generation,
        "usable_for_reply": usable_for_reply,
        "quality_notes": {
            "mixed_knowledge": mixed,
            "metadata_ratio": clamp_score(metadata_ratio),
            "content_length": text_len,
            "sentence_count": sentence_count,
        },
    }


def extract_attachment_mentions(messages: list[dict] | None) -> list[str]:
    mentions: list[str] = []
    for item in messages or []:
        content = _text(item.get("content"))
        if not content:
            continue
        for keyword in ATTACHMENT_KEYWORDS:
            if keyword.lower() in content.lower() and keyword not in mentions:
                mentions.append(keyword)
    return mentions[:12]


def build_thread_business_fact(
    *,
    session_id: str,
    summary: dict | None,
    crm_context: dict | None,
    messages: list[dict] | None,
    external_userid: str | None = None,
    sales_userid: str | None = None,
) -> dict[str, Any]:
    summary = summary or {}
    crm_context = crm_context or {}
    key_facts = summary.get("key_facts") or {}
    content_blob = "\n".join(_text(item.get("content")) for item in (messages or []))
    fact_blob = "\n".join([
        _text(summary.get("topic")),
        _text(summary.get("core_demand")),
        _text(summary.get("status")),
        _text(summary.get("risks")),
        _text(summary.get("to_be_confirmed")),
        _text(key_facts),
        _text(crm_context.get("recent_quote_summary")),
        _text(crm_context.get("ongoing_contracts")),
        content_blob,
    ])
    stage_signals = {
        "has_formal_quote": any(word.lower() in fact_blob.lower() for word in QUOTE_KEYWORDS) or bool(crm_context.get("recent_quote_summary")),
        "payment_discussed": any(word in fact_blob for word in PAYMENT_KEYWORDS),
        "payment_confirmed": any(word in fact_blob for word in ["已到账", "到账", "打款完成", "已付款"]),
        "shipment_discussed": any(word in fact_blob for word in SHIPMENT_KEYWORDS),
        "shipment_confirmed": any(word in fact_blob for word in ["已发货", "已经寄出", "在途", "到货"]),
        "after_sales_open": any(word in fact_blob for word in AFTER_SALES_KEYWORDS),
        "waiting_customer_material": any(word in fact_blob for word in ["附件", "资料", "源文件", "待确认", "待补充", "请提供"]),
    }
    if stage_signals["after_sales_open"]:
        business_state = "after_sales"
    elif stage_signals["shipment_discussed"] or stage_signals["shipment_confirmed"]:
        business_state = "shipment"
    elif stage_signals["payment_discussed"] or stage_signals["payment_confirmed"]:
        business_state = "payment"
    elif stage_signals["has_formal_quote"]:
        business_state = "formal_quote"
    else:
        business_state = "inquiry"

    scenario_label = "general"
    if stage_signals["after_sales_open"]:
        scenario_label = "after_sales"
    elif stage_signals["shipment_discussed"]:
        scenario_label = "shipment"
    elif stage_signals["payment_discussed"]:
        scenario_label = "payment"
    elif stage_signals["has_formal_quote"]:
        scenario_label = "quotation"
    elif any(word in fact_blob for word in CAPABILITY_KEYWORDS):
        scenario_label = "capability"
    elif any(word in fact_blob for word in PROCESS_KEYWORDS):
        scenario_label = "process"

    intent_label = scenario_label
    if any(word in fact_blob for word in ["案例", "经验", "项目案例"]):
        intent_label = "example"
    elif any(word in fact_blob for word in CAPABILITY_KEYWORDS):
        intent_label = "capability"
    elif any(word in fact_blob for word in PROCESS_KEYWORDS):
        intent_label = "process"
    elif stage_signals["has_formal_quote"]:
        intent_label = "pricing"

    attachment_summary = extract_attachment_mentions(messages)
    avg_len = 0.0
    if messages:
        avg_len = sum(len(_text(item.get("content"))) for item in messages) / len(messages)
    language_style = "wechat_brief" if avg_len and avg_len < 60 else "consultative"
    fact_count = sum(1 for value in stage_signals.values() if value)
    quality_score = clamp_score(0.28 + (fact_count * 0.09) + (0.12 if _text(summary.get("core_demand")) else 0.0) + (0.1 if attachment_summary else 0.0))
    usable_for_reply = quality_score >= 0.45
    allowed_for_generation = usable_for_reply and business_state in {"inquiry", "formal_quote", "payment", "shipment", "after_sales"}
    guard_reasons: list[str] = []
    if not stage_signals["has_formal_quote"]:
        guard_reasons.append("未识别到正式报价事实，禁止给确定性成交价格承诺")
    if stage_signals["waiting_customer_material"]:
        guard_reasons.append("线程仍依赖客户补充资料或附件确认")
    if quality_score < 0.45:
        guard_reasons.append("线程事实完整度不足")
    merged_facts = {
        "topic": summary.get("topic"),
        "core_demand": summary.get("core_demand"),
        "summary_status": summary.get("status"),
        "key_facts": key_facts,
        "crm_recent_quote_summary": crm_context.get("recent_quote_summary"),
        "crm_customer_tier": crm_context.get("customer_tier"),
        "crm_payment_risk_level": crm_context.get("payment_risk_level"),
        "attachment_summary": attachment_summary,
    }
    return {
        "session_id": session_id,
        "thread_id": session_id,
        "external_userid": external_userid,
        "sales_userid": sales_userid,
        "topic": summary.get("topic"),
        "core_demand": summary.get("core_demand"),
        "scenario_label": scenario_label,
        "intent_label": intent_label,
        "language_style": language_style,
        "business_state": business_state,
        "stage_signals": stage_signals,
        "merged_facts": merged_facts,
        "attachment_summary": attachment_summary,
        "quality_score": quality_score,
        "usable_for_reply": usable_for_reply,
        "allowed_for_generation": allowed_for_generation,
        "reply_guard_reason": "；".join(guard_reasons) if guard_reasons else "",
        "fact_source": {
            "summary_status": summary.get("status"),
            "crm_profile_status": crm_context.get("crm_profile_status"),
            "message_count": len(messages or []),
            "updated_at": datetime.utcnow().isoformat(),
        },
    }


def validate_thread_state_consistency(response_text: str | None, thread_fact: dict | None) -> dict[str, list[str]]:
    text = _text(response_text)
    if not text or not thread_fact:
        return {"warnings": [], "blocking_issues": []}
    warnings: list[str] = []
    blocking_issues: list[str] = []
    stage_signals = thread_fact.get("stage_signals") or {}
    if not stage_signals.get("has_formal_quote") and any(re.search(pattern, text) for pattern in PRICE_COMMITMENT_PATTERNS):
        blocking_issues.append("线程事实未进入正式报价阶段，回复中不应给出确定性报价承诺。")
    if not stage_signals.get("payment_confirmed") and any(re.search(pattern, text) for pattern in PAYMENT_DONE_PATTERNS):
        blocking_issues.append("线程事实未确认到账，回复中不应表述为已收款。")
    if not stage_signals.get("shipment_confirmed") and any(re.search(pattern, text) for pattern in SHIPMENT_DONE_PATTERNS):
        blocking_issues.append("线程事实未确认发货，回复中不应表述为已发货。")
    if not stage_signals.get("after_sales_open") and any(re.search(pattern, text) for pattern in AFTER_SALES_DONE_PATTERNS):
        warnings.append("线程事实未识别为售后处理中，售后结论型表述需要人工确认。")
    if not thread_fact.get("allowed_for_generation"):
        warnings.append(thread_fact.get("reply_guard_reason") or "线程事实层未通过自动回复门禁。")
    return {"warnings": warnings, "blocking_issues": blocking_issues}

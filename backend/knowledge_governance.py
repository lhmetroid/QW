from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

FACT_SOURCE_TYPES = {"message_extract", "thread_fact", "crm_fact", "attachment_fact"}
EMAILISH_SOURCE_TYPES = {"email_excel", "email_digest", "excellent_reply_extract", "excellent_reply"}
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
WAITING_CUSTOMER_MATERIAL_PATTERNS = [
    r"请(?:先)?(?:发送|提供|补充|发下|发我).{0,12}(?:文件|资料|附件|源文件|稿件|内容)",
    r"(?:收到|看下).{0,12}(?:文件|资料|附件|源文件).{0,12}(?:后|再)",
    r"待(?:客户)?(?:补充|提供|发送|确认).{0,12}(?:文件|资料|附件|源文件|内容)",
]


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


def _has_explicit_pricing_signal(text: str | None, pricing_rule: dict | None) -> bool:
    if not pricing_rule:
        return False
    normalized = _text(text)
    if any(pricing_rule.get(key) is not None for key in ["price_min", "price_max", "min_charge", "urgent_multiplier"]):
        return True
    haystack = "\n".join(
        [
            normalized,
            _text(pricing_rule.get("unit")),
            _text(pricing_rule.get("currency")),
            _text(pricing_rule.get("tax_policy")),
            _text(pricing_rule.get("source_ref")),
        ]
    ).lower()
    if any(term in haystack for term in ["最低收费", "起步价", "min charge", "per_", "千字", "字符", "单词", "word", "words", "页", "小时", "天", "项目"]):
        return bool(re.search(r"\d+(?:\.\d+)?", haystack))
    return False


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
    structured_pricing_ready = (
        _text(knowledge_type) == "pricing"
        and library_type == "reference"
        and not mixed["mixed"]
        and _has_explicit_pricing_signal(text, pricing_rule)
    )
    if structured_pricing_ready:
        completeness = max(completeness, 0.55)
        evidence = max(evidence, 0.6)
        reusability = max(reusability, 0.58)
    clarity = clamp_score(clarity)
    completeness = clamp_score(completeness)
    evidence = clamp_score(evidence)
    reusability = clamp_score(reusability)
    useful = clamp_score((clarity * 0.25) + (completeness * 0.3) + (reusability * 0.2) + (evidence * 0.25))
    publishable = useful >= 0.58 and evidence >= 0.5 and not mixed["mixed"]
    allowed_for_generation = library_type in REPLYABLE_LIBRARY_TYPES and useful >= 0.65 and not mixed["mixed"]
    usable_for_reply = allowed_for_generation and (
        structured_pricing_ready or (reusability >= 0.55 and evidence >= 0.58)
    )
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


def _attachment_kind_from_text(text: str) -> str:
    lower = text.lower()
    if any(ext in lower for ext in [".pdf", " pdf"]):
        return "pdf"
    if any(ext in lower for ext in [".doc", ".docx", " doc", " docx"]):
        return "word"
    if any(ext in lower for ext in [".xls", ".xlsx", " xls", " xlsx"]):
        return "excel"
    if any(ext in lower for ext in [".zip", ".rar", " zip", " rar"]):
        return "archive"
    if "po" in lower:
        return "po"
    if "鍚堝悓" in text:
        return "contract"
    if "鎶ヤ环" in text:
        return "quote"
    if "鍥剧墖" in text or "image" in lower or "jpg" in lower or "png" in lower:
        return "image"
    return "file"


def _extract_attachment_filenames(text: str) -> list[str]:
    filenames = re.findall(
        r"([A-Za-z0-9_\-\u4e00-\u9fa5]+\.(?:pdf|docx?|xlsx?|zip|rar|png|jpg|jpeg))",
        text,
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(name[:120] for name in filenames))


def sanitize_attachment_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", _text(text))
    return compact[:180]

def _split_attachment_names(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    items: list[str] = []
    for block in text.replace("；", ";").replace("，", ",").split(";"):
        for token in [part.strip() for part in block.split(",") if part.strip()]:
            if token and token not in items:
                items.append(token[:120])
    return items


def _attachment_signals(text: str) -> list[str]:
    lower = text.lower()
    signals: list[str] = []
    if any(word.lower() in lower for word in QUOTE_KEYWORDS):
        signals.append("pricing")
    if any(word.lower() in lower for word in PAYMENT_KEYWORDS):
        signals.append("payment")
    if any(word.lower() in lower for word in SHIPMENT_KEYWORDS):
        signals.append("shipment")
    if any(word.lower() in lower for word in AFTER_SALES_KEYWORDS):
        signals.append("after_sales")
    if "po" in lower:
        signals.append("po")
    if "合同" in text:
        signals.append("contract")
    if "发票" in text or "invoice" in lower:
        signals.append("invoice")
    return list(dict.fromkeys(signals))


def _attachment_summary_text(text: str) -> str:
    compact = sanitize_attachment_text(text)
    if len(compact) <= 90:
        return compact
    return compact[:87] + "..."


def extract_attachment_mentions(
    messages: list[dict] | None,
    extra_texts: list[str] | None = None,
    attachment_items: list[dict] | None = None,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_attachment(raw_text: Any, source: str, *, filename: str | None = None, kind: str | None = None) -> None:
        text = _text(raw_text)
        filename_value = _text(filename) or None
        if not text and not filename_value:
            return
        lower = text.lower()
        matched = any(keyword.lower() in lower for keyword in ATTACHMENT_KEYWORDS) or bool(filename_value)
        filenames = [filename_value] if filename_value else _extract_attachment_filenames(text)
        if not matched and not filenames:
            return

        if filenames:
            for filename_item in filenames:
                key = (source, filename_item.lower())
                if key in seen:
                    continue
                seen.add(key)
                payload_text = text or filename_item
                mentions.append(
                    {
                        "source": source,
                        "kind": kind or _attachment_kind_from_text(filename_item),
                        "filename": filename_item,
                        "raw": sanitize_attachment_text(payload_text),
                        "summary": _attachment_summary_text(payload_text),
                        "signals": _attachment_signals(payload_text),
                    }
                )
            return

        key = (source, text[:80].lower())
        if key in seen:
            return
        seen.add(key)
        mentions.append(
            {
                "source": source,
                "kind": kind or _attachment_kind_from_text(text),
                "filename": None,
                "raw": sanitize_attachment_text(text),
                "summary": _attachment_summary_text(text),
                "signals": _attachment_signals(text),
            }
        )

    for item in messages or []:
        add_attachment(item.get("content"), "message")
        raw_attachments = item.get("attachments") or []
        if isinstance(raw_attachments, dict):
            raw_attachments = [raw_attachments]
        for attachment in raw_attachments:
            if not isinstance(attachment, dict):
                add_attachment(attachment, "message_attachment")
                continue
            attachment_text = (
                attachment.get("text")
                or attachment.get("content")
                or attachment.get("summary")
                or attachment.get("raw")
            )
            attachment_names = _split_attachment_names(
                attachment.get("filename")
                or attachment.get("name")
                or attachment.get("attachment_name")
                or attachment.get("attachment_names")
            )
            if attachment_names:
                for filename_item in attachment_names:
                    add_attachment(
                        attachment_text or filename_item,
                        "message_attachment",
                        filename=filename_item,
                        kind=_text(attachment.get("kind")) or None,
                    )
                continue
            add_attachment(attachment_text, "message_attachment", kind=_text(attachment.get("kind")) or None)
    for attachment in attachment_items or []:
        if not isinstance(attachment, dict):
            add_attachment(attachment, "attachment_item")
            continue
        attachment_text = (
            attachment.get("text")
            or attachment.get("content")
            or attachment.get("summary")
            or attachment.get("raw")
        )
        attachment_names = _split_attachment_names(
            attachment.get("filename")
            or attachment.get("name")
            or attachment.get("attachment_name")
            or attachment.get("attachment_names")
        )
        if attachment_names:
            for filename_item in attachment_names:
                add_attachment(
                    attachment_text or filename_item,
                    "attachment_item",
                    filename=filename_item,
                    kind=_text(attachment.get("kind")) or None,
                )
            continue
        add_attachment(attachment_text, "attachment_item", kind=_text(attachment.get("kind")) or None)
    for text in extra_texts or []:
        add_attachment(text, "summary")
    return mentions[:12]


def summarize_attachment_mentions(mentions: list[dict[str, Any]] | None) -> dict[str, Any]:
    mentions = mentions or []
    kind_counter: dict[str, int] = defaultdict(int)
    signal_counter: dict[str, int] = defaultdict(int)
    filenames: list[str] = []
    for item in mentions:
        kind = _text(item.get("kind"))
        if kind:
            kind_counter[kind] += 1
        for signal in item.get("signals") or []:
            signal_value = _text(signal)
            if signal_value:
                signal_counter[signal_value] += 1
        filename = _text(item.get("filename"))
        if filename and filename not in filenames:
            filenames.append(filename)
    return {
        "count": len(mentions),
        "kinds": dict(sorted(kind_counter.items())),
        "signals": dict(sorted(signal_counter.items())),
        "filenames": filenames[:10],
        "has_structured_attachments": any(bool(item.get("filename")) for item in mentions),
    }


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value))


def _extract_time_mentions(text: str | None) -> list[str]:
    raw_text = _text(text)
    if not raw_text:
        return []
    patterns = [
        r"\d{1,2}月\d{1,2}日",
        r"(?:本周|下周)?周[一二三四五六日天]",
        r"\d{1,2}点半?",
        r"(?:上午|中午|下午|晚上)\d{1,2}点半?",
        r"\d{1,2}点到\d{1,2}点",
    ]
    values: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, raw_text):
            value = _text(match)
            if value and value not in values:
                values.append(value)
    return values[:6]


def _detect_latest_customer_reply_type(text: str | None) -> str:
    raw_text = _text(text)
    compact = _compact_text(text)
    if not compact:
        return "other"
    if re.search(r"(到公司|回头|稍后|晚点|方便时|一会儿).{0,8}(发|给你|发你|发送)", raw_text):
        return "promise_send_later"
    if (
        _extract_time_mentions(raw_text)
        and any(token in raw_text for token in ["开始", "到", "到场", "下午", "上午", "周三", "本周", "6月", "会议"])
    ):
        return "schedule_confirmation"
    if re.fullmatch(r"(收到|收到了|收到啦|好|好的|好滴|ok|OK|嗯|嗯嗯|收到\[?OK\]?)[!！。.]?", compact, flags=re.IGNORECASE):
        return "ack_only"
    if "?" in raw_text or "？" in raw_text or any(token in raw_text for token in ["吗", "么", "是否", "可否", "能否"]):
        return "question"
    return "other"


def _sales_asked_schedule(latest_sales_message: str | None) -> bool:
    return bool(re.search(r"(时间|几点|几号|开始|到场|定了|安排|会议|会前|周三|本周|下午)", _text(latest_sales_message)))


def _sales_asked_material(latest_sales_message: str | None) -> bool:
    return bool(re.search(r"(发我|给我|发你|资料|文件|附件|PPT|材料)", _text(latest_sales_message), re.IGNORECASE))


def _response_reasks_schedule(response_text: str | None, latest_customer_message: str | None) -> bool:
    response = _text(response_text)
    if not response or not _extract_time_mentions(latest_customer_message):
        return False
    if not re.search(r"(吗|吧|确认|没问题吧|可以吧|是否|几点|几号|开始|到场|安排)", response):
        return False
    customer_times = _extract_time_mentions(latest_customer_message)
    return any(time_value in response for time_value in customer_times)


def _response_reasks_material(response_text: str | None) -> bool:
    response = _text(response_text)
    return bool(
        re.search(r"(发我|给我|资料|文件|附件|PPT|材料)", response, re.IGNORECASE)
        and re.search(r"(收到后|看下|看看|发来|方便时)", response)
    )


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
    normalized_messages = list(messages or [])
    key_facts = summary.get("key_facts") or {}
    attachment_records: list[dict[str, Any]] = []
    for item in normalized_messages:
        raw_attachments = item.get("attachments") or []
        if isinstance(raw_attachments, dict):
            raw_attachments = [raw_attachments]
        for attachment in raw_attachments:
            if isinstance(attachment, dict):
                attachment_records.append(dict(attachment))
    content_blob = "\n".join(_text(item.get("content")) for item in normalized_messages)
    current_fact_blob = "\n".join([
        _text(summary.get("topic")),
        _text(summary.get("core_demand")),
        _text(summary.get("status")),
        _text(summary.get("risks")),
        _text(summary.get("to_be_confirmed")),
        _text(key_facts),
        content_blob,
    ])
    fact_blob = "\n".join([
        current_fact_blob,
        _text(crm_context.get("recent_quote_summary")),
        _text(crm_context.get("ongoing_contracts")),
    ])
    sales_message_count = sum(1 for item in normalized_messages if _text(item.get("sender_type")) == "sales")
    customer_message_count = sum(1 for item in normalized_messages if _text(item.get("sender_type")) == "customer")
    latest_sender = _text(normalized_messages[-1].get("sender_type")) if normalized_messages else ""
    consecutive_sales_messages = 0
    for item in reversed(normalized_messages):
        if _text(item.get("sender_type")) == "sales":
            consecutive_sales_messages += 1
            continue
        break
    sales_messages = [_text(item.get("content")) for item in normalized_messages if _text(item.get("sender_type")) == "sales" and _text(item.get("content"))]
    latest_sales_message = sales_messages[-1] if sales_messages else ""
    recent_sales_messages = sales_messages[-2:] if sales_messages else []
    trailing_customer_messages: list[str] = []
    if latest_sender == "customer":
        for item in reversed(normalized_messages):
            if _text(item.get("sender_type")) != "customer":
                break
            content = _text(item.get("content"))
            if content:
                trailing_customer_messages.append(content)
        trailing_customer_messages.reverse()
    latest_customer_message = "\n".join(trailing_customer_messages).strip() if trailing_customer_messages else next(
        (_text(item.get("content")) for item in reversed(normalized_messages) if _text(item.get("sender_type")) == "customer"),
        "",
    )
    latest_customer_reply_type = _detect_latest_customer_reply_type(latest_customer_message)
    latest_customer_time_mentions = _extract_time_mentions(latest_customer_message)
    awaiting_customer_reply = latest_sender == "sales" and sales_message_count > 0
    sales_only_conversation = sales_message_count > 0 and customer_message_count == 0
    followup_after_no_reply = awaiting_customer_reply and consecutive_sales_messages >= 2
    material_wait_blob = "\n".join([
        _text(summary.get("core_demand")),
        _text(summary.get("to_be_confirmed")),
        content_blob,
    ])
    stage_signals = {
        "has_formal_quote": any(word.lower() in current_fact_blob.lower() for word in QUOTE_KEYWORDS),
        "crm_has_quote_history": bool(crm_context.get("recent_quote_summary")),
        "payment_discussed": any(word in fact_blob for word in PAYMENT_KEYWORDS),
        "payment_confirmed": any(word in fact_blob for word in ["已到账", "到账", "打款完成", "已付款"]),
        "shipment_discussed": any(word in fact_blob for word in SHIPMENT_KEYWORDS),
        "shipment_confirmed": any(word in fact_blob for word in ["已发货", "已经寄出", "在途", "到货"]),
        "after_sales_open": any(word in fact_blob for word in AFTER_SALES_KEYWORDS),
        "waiting_customer_material": any(re.search(pattern, material_wait_blob, re.IGNORECASE) for pattern in WAITING_CUSTOMER_MATERIAL_PATTERNS),
        "awaiting_customer_reply": awaiting_customer_reply,
        "sales_only_conversation": sales_only_conversation,
        "followup_after_no_reply": followup_after_no_reply,
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
    elif stage_signals["followup_after_no_reply"]:
        scenario_label = "followup"
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
    elif stage_signals["followup_after_no_reply"]:
        intent_label = "followup"
    elif any(word in fact_blob for word in CAPABILITY_KEYWORDS):
        intent_label = "capability"
    elif any(word in fact_blob for word in PROCESS_KEYWORDS):
        intent_label = "process"
    elif stage_signals["has_formal_quote"]:
        intent_label = "pricing"

    attachment_summary = extract_attachment_mentions(
        messages,
        extra_texts=[
            _text(summary.get("core_demand")),
            _text(summary.get("to_be_confirmed")),
            _text(key_facts),
        ],
        attachment_items=attachment_records,
    )
    attachment_rollup = summarize_attachment_mentions(attachment_summary)
    avg_len = 0.0
    if normalized_messages:
        avg_len = sum(len(_text(item.get("content"))) for item in normalized_messages) / len(normalized_messages)
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
    if stage_signals["followup_after_no_reply"]:
        guard_reasons.append("当前属于我方已触达但客户未回复，下一条话术必须换角度推进，不能重复上一条原话")
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
        "last_sender": latest_sender or None,
        "sales_message_count": sales_message_count,
        "customer_message_count": customer_message_count,
        "consecutive_sales_messages": consecutive_sales_messages,
        "awaiting_customer_reply": awaiting_customer_reply,
        "sales_only_conversation": sales_only_conversation,
        "followup_after_no_reply": followup_after_no_reply,
        "latest_sales_message": latest_sales_message[:160] if latest_sales_message else None,
        "recent_sales_messages": [item[:160] for item in recent_sales_messages if item][:2],
        "latest_customer_message": latest_customer_message[:160] if latest_customer_message else None,
        "latest_customer_reply_type": latest_customer_reply_type,
        "latest_customer_time_mentions": latest_customer_time_mentions,
        "crm_has_quote_history": bool(crm_context.get("recent_quote_summary")),
        "attachment_summary": attachment_summary,
        "attachment_rollup": attachment_rollup,
        "attachment_types": sorted({item.get("kind") for item in attachment_summary if item.get("kind")}),
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
            "message_count": len(normalized_messages),
            "last_sender": latest_sender or None,
            "attachment_count": attachment_rollup["count"],
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
    merged_facts = thread_fact.get("merged_facts") or {}
    if not stage_signals.get("has_formal_quote") and any(re.search(pattern, text) for pattern in PRICE_COMMITMENT_PATTERNS):
        blocking_issues.append("线程事实未进入正式报价阶段，回复中不应给出确定性报价承诺。")
    if not stage_signals.get("payment_confirmed") and any(re.search(pattern, text) for pattern in PAYMENT_DONE_PATTERNS):
        blocking_issues.append("线程事实未确认到账，回复中不应表述为已收款。")
    if not stage_signals.get("shipment_confirmed") and any(re.search(pattern, text) for pattern in SHIPMENT_DONE_PATTERNS):
        blocking_issues.append("线程事实未确认发货，回复中不应表述为已发货。")
    if not stage_signals.get("after_sales_open") and any(re.search(pattern, text) for pattern in AFTER_SALES_DONE_PATTERNS):
        warnings.append("线程事实未识别为售后处理中，售后结论型表述需要人工确认。")
    if stage_signals.get("followup_after_no_reply") or stage_signals.get("awaiting_customer_reply"):
        compact_response = re.sub(r"\s+", "", text)
        recent_sales_messages = merged_facts.get("recent_sales_messages") or []
        if not recent_sales_messages:
            latest_sales_message = _text(merged_facts.get("latest_sales_message"))
            if latest_sales_message:
                recent_sales_messages = [latest_sales_message]
        repeated_cues = [
            "之前合作", "合作记录", "项目资料", "现在还负责", "是否还负责", "您还负责", "也想了解一下",
            "最近在整理", "想简单问一下", "我是负责", "我是岚汇", "我是tiffany",
        ]
        responsibility_patterns = [
            r"还.*负责", r"是否.*负责", r"谁.*负责", r"哪位.*负责", r"现在.*负责",
            r"其他同事.*对接", r"谁在对接", r"对接.*同事", r"负责人",
        ]
        response_hit_count = sum(1 for cue in repeated_cues if cue in compact_response)
        response_repeats_responsibility = any(re.search(pattern, compact_response) for pattern in responsibility_patterns)
        for previous_message in recent_sales_messages:
            previous_compact = re.sub(r"\s+", "", _text(previous_message))
            if not previous_compact:
                continue
            shared_substrings = [
                cue for cue in repeated_cues
                if cue in compact_response and cue in previous_compact
            ]
            previous_tokens = {
                token for token in re.findall(r"[\u4e00-\u9fff]{2,}", previous_compact)
                if len(token) >= 2
            }
            response_tokens = {
                token for token in re.findall(r"[\u4e00-\u9fff]{2,}", compact_response)
                if len(token) >= 2
            }
            shared_tokens = {
                token for token in previous_tokens & response_tokens
                if token not in {"您好", "打扰了", "如果方便", "辛苦了", "这边", "目前", "项目", "合作"}
            }
            previous_asked_responsibility = any(re.search(pattern, previous_compact) for pattern in responsibility_patterns)
            if (
                shared_substrings
                or response_hit_count >= 2
                or len(shared_tokens) >= 4
                or (response_repeats_responsibility and previous_asked_responsibility)
            ):
                blocking_issues.append("当前属于客户未回复后的跟进，回复与最近我方外联过于相似，必须换角度推进，不能复述旧话术。")
                break
    if merged_facts.get("last_sender") == "customer":
        latest_customer_message = _text(merged_facts.get("latest_customer_message"))
        latest_sales_message = _text(merged_facts.get("latest_sales_message"))
        latest_customer_reply_type = _text(merged_facts.get("latest_customer_reply_type"))
        if (
            latest_customer_reply_type == "schedule_confirmation"
            and _sales_asked_schedule(latest_sales_message)
            and _response_reasks_schedule(text, latest_customer_message)
        ):
            blocking_issues.append("客户刚确认时间安排，回复不应再次追问同一时间问题，应改为确认收到并说明我方动作。")
        if (
            latest_customer_reply_type == "promise_send_later"
            and _sales_asked_material(latest_sales_message)
            and _response_reasks_material(text)
        ):
            blocking_issues.append("客户已承诺稍后发送资料，回复不应重复催问同一材料，应先承接并说明收到后的动作。")
    if not thread_fact.get("allowed_for_generation"):
        warnings.append(thread_fact.get("reply_guard_reason") or "线程事实层未通过自动回复门禁。")
    return {"warnings": warnings, "blocking_issues": blocking_issues}

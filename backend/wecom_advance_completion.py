# -*- coding: utf-8 -*-
"""WeCom reply advance-completion guard.

This is the in-process version of the provided advance_completion_guard code.
It runs after the normal WeCom reply generators and rewrites an existing draft
only when the draft is passive or pending, while preserving red-line checks.
"""

from __future__ import annotations

import re

import requests

from config import settings


RE_ELICIT = re.compile(
    r"您先|请您|麻烦您|您把|您给|您发|发我|发给我|给我看|告诉我|您看下|您确认|确认下|确认一下|方便吗|方便的话|"
    r"大概什么时候|多少量|几位|几天|几点|预算|约个|约时间|什么时候能|要不您|您这边.*?(发|给|确认|看)|"
    r"您回复|您回个|回个确认|您定了|定了(招呼|我就|您|您就)|您先确认|麻烦.{0,5}回复|\?|？"
)
RE_ACTION = re.compile(
    r"我这就|我马上|马上(安排|统计|核|发|给|去)|这就(安排|统计|核|去|帮)|我去(问|核|安排|协调|对|催)|"
    r"我尽快(完成|更新|发|给|安排|出|统计|回)|尽快完成|尽快更新|更新完成|统计报价|"
    r"我核(字数|全文|完|一版|给您|给你|下)|我帮您|我来安排|我对接|我跟进|我整理|我加(进|上)|"
    r"我编辑|我匹配|我同步|我让同事|我先把|安排开译|安排翻译|安排排期|锁排期|安排开工|走流程|"
    r"走起来|我协调|盖好?章|填好?资料|我盯着|我尽量赶|赶在|争取(明天|今天|明早|下班前)"
)
RE_DEFER = re.compile(r"核算|报您|报你|我看下|我确认下再|稍等|我估|核完|核一版|再帮您核|我先看")

ADVANCING = {"推进-索取/约访", "推进-承诺动作"}

RE_COMPLAINT = re.compile(
    r"不满|不对|错误|错了|有误|差距|不过脑|投诉|质量问题|没盖章|漏了|不准确|太差|返工|不专业|搞错|弄错|催.*没|怎么还"
)
RE_DECLINE = re.compile(
    r"暂(时)?(无|没)|没(有)?需求|不需要|以后(再)?(联系|说)|不做了|自己翻|用AI|用软件翻|固定(的)?供应商|"
    r"不麻烦你们|别(再)?发|退订|费用控制|预算.*(没|不)"
)
RE_CLOSING = re.compile(r"^(好的?|谢谢|多谢|祝好|辛苦了?|再见|拜拜|客气|麻烦您?了?)[。!~\s]*$")
RE_STRONG_DECLINE = re.compile(
    r"自己翻|用软件翻|用AI翻|软件翻译|不麻烦你们|固定(的)?(翻译)?(公司|供应商)|不做了|"
    r"(?<!需)不需要(?!.{0,2}吗|.{0,2}\?)|别(再)?发|退订|暂(时)?(不|没).{0,4}(需求|需要|做|要|打算)"
)
RE_HIGH_VALUE = re.compile(
    r"朋友|同事|推荐(给|了|过)|介绍给|帮(我|你)推|转介绍|每年|长期合作|长期的合同|"
    r"未来.{0,4}年|之后.{0,6}(也|还).{0,4}(会|要|找|需要)|接手|换(人|对接)|前任|离职|"
    r"我姓.{1,3}.{0,8}(签|合同|合作|对接)|签过.{0,4}合同"
)

RE_MONEY = re.compile(r"[¥￥]\s*\d|\d+\s*元(?!/?\s*千|起|宝)|\d+\.\d+\s*元|\d+\s*块|\d+\s*/\s*千字.*\d|单价\s*\d")
RE_DATE = re.compile(
    r"\d+\s*个?\s*工作日|\d+\s*天(内|交|出|完成)|周[一二三四五六日天].{0,3}(交|出|前|完成)|"
    r"(明|后)(天|早).{0,7}(出稿|出|交付|交|发回|发|寄|盖出|完成)|今(天|日).{0,7}(出稿|交付|交|发回|完成)|"
    r"(上午|下午|中午|晚上|早上)\s*\d+\s*点|\d+\s*点(前|半|钟|整)|\d+\s*点[^,，。!！?？]{0,4}(交|出|发|寄|完成)"
)

MERGE_SYSTEM_PROMPT = (
    "你是资深翻译外包行业销售,在企业微信上回客户。给你:对话上文、客户最新消息、以及一版你写的草稿回复。"
    "请基于草稿输出【最终回复】:先自然确认/回应客户当前这句,然后顺势补上一个【具体的下一步推进动作】"
    "(按情况:请客户发文件/确认规格或语种/问期望交期或预算/约时间/提议打样/促确认开工/请转介绍/给低门槛钩子等),"
    "揉成一句口语化、简短(1到3句)的企微话,口吻像真实销售。\n"
    "硬规则:① 即使草稿看着完整,最终回复也必须以一个【具体的下一步推进动作】收尾;"
    "② 最终回复不得比草稿更被动、更短、更敷衍(只多不少地往前推);"
    "③ 不写死具体金额和交期,一律改为'核算后给您准价/确认后告知交期'(计价口径如按千字、6%专票可说);"
    "④ 不复述也不新增任何人名、称呼、电话、微信等个人信息;⑤ 只用自然中文、不夹英文;"
    "⑥ 只输出最终回复本身,不要解释、不要加前缀。"
)

DEEPSEEK_SYSTEM_PROMPT = (
    "你是资深翻译外包行业销售,在企业微信上回客户。给你:对话上文、客户最新消息、以及一版草稿回复。"
    "请输出【最终回复】,按情况处理:\n"
    "- 推进型情况(咨询能力/问价比价/确认方案细节/有潜在需求/转介绍/老客复购等)且草稿只是被动确认:"
    "在确认客户当前句后,补一个【具体的下一步推进动作】(请客户发文件/确认规格或语种/问期望交期或预算/约时间/促确认开工/请转介绍/给低门槛钩子等)。\n"
    "- 客户在投诉/抱怨:先共情、表态去核实改进,这一轮绝不推销或横拓其他业务。"
    "- 客户明确拒绝/暂时没需求/要自己做或用AI:礼貌留个口子,不硬推。\n"
    "- 草稿已经带了推进动作:保持,必要时润色更自然。\n"
    "硬规则:① 简洁,一般1到2句、最多3句;只做'确认+一个推进动作',点到为止;"
    "② 不写死具体金额和交期,一律改为'交期我确认后告知您''核算后给您准价';"
    "③ 不复述也不新增任何电话/微信/邮箱;上文出现过人名也尽量用'您老板/对接人'指代;"
    "④ 只用自然中文、不夹英文;只输出最终回复本身,不要解释、不要加前缀。"
)


def advance_label(reply: str | None) -> str:
    text = (reply or "").strip()
    if not text:
        return "空"
    if RE_ELICIT.search(text):
        return "推进-索取/约访"
    if RE_ACTION.search(text):
        return "推进-承诺动作"
    if RE_DEFER.search(text):
        return "待定-延后回价"
    return "被动确认"


def advance_tag(reply: str | None) -> str:
    label = advance_label(reply)
    if label in ADVANCING:
        return "推进"
    if label == "待定-延后回价":
        return "待定"
    if label == "被动确认":
        return "被动"
    return ""


def _norm(text: str) -> str:
    return re.sub(r"[\s。，,.!！~、；;]", "", text or "")


def _echoes(draft: str, customer_msg: str) -> bool:
    draft_norm = re.sub(r"\s", "", draft or "")
    customer_norm = re.sub(r"\s", "", customer_msg or "")
    if len(customer_norm) < 6:
        return False
    return customer_norm in draft_norm or (bool(draft_norm) and draft_norm[:len(customer_norm)] == customer_norm)


def _redline_ok(text: str) -> bool:
    return not (RE_MONEY.search(text or "") or RE_DATE.search(text or ""))


def _context_to_text(context_turns: list[dict] | None) -> str:
    lines: list[str] = []
    for idx, item in enumerate(context_turns or [], 1):
        content = str((item or {}).get("content") or "").strip()
        if content:
            role = str((item or {}).get("role") or "客户")
            lines.append(f"{idx}. {role}: {content}")
    return "\n".join(lines)


def should_advance(draft: str, customer_msg: str) -> tuple[bool, str]:
    if not (draft or "").strip():
        return False, "empty_draft"
    if RE_COMPLAINT.search(customer_msg or ""):
        return False, "complaint_first"
    if RE_DECLINE.search(customer_msg or ""):
        return False, "decline"
    if RE_CLOSING.match((customer_msg or "").strip()):
        return False, "closing"
    if _echoes(draft, customer_msg):
        return True, "echo_fix"
    if advance_tag(draft) == "推进":
        return False, "already_advancing"
    return True, "passive_or_pending"


def _ollama_chat(system_prompt: str, user_prompt: str, *, timeout: int) -> str | None:
    url = str(settings.WECOM_ADVANCE_COMPLETION_OLLAMA_CHAT_URL or "").strip()
    model = str(settings.WECOM_ADVANCE_COMPLETION_LOCAL_MODEL or "").strip()
    if not url or not model:
        return None
    url = url.rstrip("/")
    if not url.endswith("/api/chat"):
        url = f"{url}/api/chat"
    session = requests.Session()
    session.trust_env = settings.HTTP_TRUST_ENV
    response = session.post(
        url,
        json={
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "stream": False,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        return None
    payload = response.json() if response.content else {}
    return str(((payload.get("message") or {}) if isinstance(payload, dict) else {}).get("content") or "").strip() or None


def _merge_with_local(draft: str, customer_msg: str, context_text: str, *, strict_redline: bool = False, force_advance: bool = False) -> str | None:
    user_prompt = f"【对话上文】\n{context_text}\n\n【客户最新消息】{customer_msg}\n\n【草稿回复】{draft}\n\n请输出最终回复:"
    system_prompt = MERGE_SYSTEM_PROMPT
    if strict_redline:
        system_prompt += "\n【特别强调】上一版出现了写死的金额或交期,这次务必把任何具体数字金额/具体日期天数改成'核算后报价/确认后告知交期'。"
    if force_advance:
        system_prompt += "\n【特别强调】上一版没有真正往前推,这次务必在确认之后明确补上一个具体下一步动作,不能只是确认或客气。"
    try:
        return _ollama_chat(system_prompt, user_prompt, timeout=max(1, int(settings.WECOM_ADVANCE_COMPLETION_TIMEOUT_SECONDS or 70)))
    except Exception:
        return None


def _complete_advance_local(draft: str, customer_msg: str, context_text: str = "") -> dict:
    need, reason = should_advance(draft, customer_msg)
    if not need:
        return {"final": draft, "acted": False, "reason": reason, "redline_ok": _redline_ok(draft), "provider": "local"}
    merged = _merge_with_local(draft, customer_msg, context_text)
    if not merged:
        return {"final": draft, "acted": False, "reason": "merge_failed", "redline_ok": _redline_ok(draft), "provider": "local"}
    if _norm(merged) == _norm(draft):
        forced = _merge_with_local(draft, customer_msg, context_text, force_advance=True)
        if forced and _norm(forced) != _norm(draft):
            merged = forced
    if not _redline_ok(merged):
        retry = _merge_with_local(draft, customer_msg, context_text, strict_redline=True, force_advance=True)
        if retry and _redline_ok(retry):
            merged = retry
        else:
            return {
                "final": draft,
                "acted": False,
                "reason": "redline_violation_fallback",
                "redline_ok": _redline_ok(draft),
                "provider": "local",
            }
    return {"final": merged, "acted": True, "reason": reason, "redline_ok": True, "provider": "local"}


def _deepseek_chat(system_prompt: str, user_prompt: str) -> tuple[str | None, str]:
    api_key = str(settings.LLM2_API_KEY or "").strip()
    api_url = str(settings.LLM2_API_URL or "").strip()
    model = str(settings.LLM2_MODEL or "").strip() or "deepseek-chat"
    if not api_key or not api_url:
        return None, "not_configured"
    url = api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    try:
        session = requests.Session()
        session.trust_env = settings.HTTP_TRUST_ENV
        response = session.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "stream": False,
                "temperature": 0.3,
            },
            timeout=max(1, int(settings.WECOM_ADVANCE_COMPLETION_TIMEOUT_SECONDS or 70)),
        )
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        payload = response.json() if response.content else {}
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") if isinstance(payload, dict) else ""
        return (str(content or "").strip() or None), "ok"
    except Exception as exc:
        return None, f"error:{str(exc)[:80]}"


def _complete_advance_deepseek(draft: str, customer_msg: str, context_text: str = "") -> dict:
    user_prompt = f"【对话上文】\n{context_text}\n\n【客户最新消息】{customer_msg}\n\n【草稿回复】{draft}\n\n请输出最终回复:"
    final, status = _deepseek_chat(DEEPSEEK_SYSTEM_PROMPT, user_prompt)
    if not final:
        fallback = _complete_advance_local(draft, customer_msg, context_text)
        fallback["reason"] = f"deepseek_fallback_{status}"
        fallback["provider"] = "deepseek_fallback_local"
        return fallback
    if not _redline_ok(final):
        retry, _ = _deepseek_chat(
            f"{DEEPSEEK_SYSTEM_PROMPT}\n【强调】上一版出现了写死的金额或交期,这次务必改成'核算后报价/确认后告知交期'。",
            user_prompt,
        )
        if retry and _redline_ok(retry):
            final = retry
        else:
            fallback = _complete_advance_local(draft, customer_msg, context_text)
            fallback["reason"] = "deepseek_redline_fallback_local"
            fallback["provider"] = "deepseek_fallback_local"
            return fallback
    return {"final": final, "acted": _norm(final) != _norm(draft), "reason": "deepseek", "redline_ok": True, "provider": "deepseek"}


def _should_escalate(draft: str, customer_msg: str, local_result: dict) -> tuple[bool, str]:
    if RE_COMPLAINT.search(customer_msg or ""):
        return False, "complaint_keep_local"
    if RE_HIGH_VALUE.search(customer_msg or ""):
        return True, "high_value"
    if (not local_result.get("acted")) and advance_tag(draft) in {"被动", "待定"}:
        reason = local_result.get("reason")
        if reason == "already_advancing":
            return True, "gate_conflict"
        if reason in {"decline", "closing"} and not RE_STRONG_DECLINE.search(customer_msg or ""):
            return True, "gate_conflict_softdecline"
    if local_result.get("acted") and _norm(local_result.get("final", "")) == _norm(draft):
        return True, "local_noop"
    return False, ""


def process_advance_completion(
    *,
    customer_message: str,
    context_turns: list[dict] | None,
    draft: str,
    provider: str | None = None,
) -> dict:
    """Rewrite an existing generated WeCom reply draft in-process.

    Returns the same shape as the standalone service: final, draft, acted,
    reason, redline_ok, provider.
    """
    draft_text = str(draft or "").strip()
    context_text = _context_to_text(context_turns)
    selected_provider = str(provider or settings.WECOM_ADVANCE_COMPLETION_PROVIDER or "hybrid").strip().lower()
    if not draft_text:
        return {"final": "", "draft": "", "acted": False, "reason": "empty_draft", "redline_ok": True, "provider": selected_provider}
    if selected_provider == "deepseek":
        result = _complete_advance_deepseek(draft_text, customer_message, context_text)
    elif selected_provider == "hybrid":
        local_result = _complete_advance_local(draft_text, customer_message, context_text)
        escalate, reason = _should_escalate(draft_text, customer_message, local_result)
        if escalate:
            result = _complete_advance_deepseek(draft_text, customer_message, context_text)
            result["reason"] = f"escalate:{reason}>{result.get('reason')}"
            result["provider"] = "hybrid_deepseek"
        else:
            result = local_result
            result["provider"] = "hybrid_local"
    else:
        result = _complete_advance_local(draft_text, customer_message, context_text)
        result["provider"] = "local"
    result["draft"] = draft_text
    return result

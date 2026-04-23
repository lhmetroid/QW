from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOC = ROOT / "docs" / "笔译报价.doc"
OUT_DIR = ROOT / "测试数据" / "笔译报价抽取_20260420"

COLUMNS = [
    "title",
    "content",
    "knowledge_type",
    "chunk_type",
    "business_line",
    "sub_service",
    "language_pair",
    "service_scope",
    "region",
    "customer_tier",
    "priority",
    "risk_level",
    "effective_from",
    "effective_to",
    "unit",
    "currency",
    "price_min",
    "price_max",
    "min_charge",
    "urgent_multiplier",
    "tax_policy",
    "tags",
]

LANG_LABELS = {
    "en->zh": "英译中",
    "ja->zh": "日译中",
    "zh->en": "中译英",
    "zh->ja": "中译日",
    "fr->zh": "法译中",
    "zh->fr": "中译法",
    "de->zh": "德译中",
    "zh->de": "中译德",
    "ko->zh": "韩译中",
    "zh->ko": "中译韩",
    "ru->zh": "俄译中",
    "zh->ru": "中译俄",
    "it->zh": "意译中",
    "zh->it": "中译意",
    "es->zh": "西译中",
    "zh->es": "中译西",
    "ar->zh": "阿译中",
    "zh->ar": "中译阿",
    "da->zh": "丹麦语译中",
    "zh->da": "中译丹麦语",
    "pt->zh": "葡译中",
    "zh->pt": "中译葡",
    "nl->zh": "荷译中",
    "zh->nl": "中译荷",
    "sv->zh": "瑞典语译中",
    "zh->sv": "中译瑞典语",
    "no->zh": "挪威语译中",
    "zh->no": "中译挪威语",
    "el->zh": "希腊语译中",
    "zh->el": "中译希腊语",
    "tr->zh": "土耳其语译中",
    "zh->tr": "中译土耳其语",
    "fr->en": "法译英",
    "de->en": "德译英",
    "en->fr": "英译法",
    "en->de": "英译德",
    "en->ja": "英译日",
    "ja->en": "日译英",
    "en->en": "英文润稿",
}


@dataclass(frozen=True)
class QuoteSpec:
    language_pairs: tuple[str, ...]
    service_scope: str
    scope_label: str
    price: float
    unit: str
    source_section: str
    note: str = ""


def extract_doc_text(source: Path) -> list[str]:
    data = source.read_bytes()
    text = data.decode("utf-16le", errors="ignore")
    runs = re.findall(r"[\u4e00-\u9fffA-Za-z0-9（）()/．.：:,，、。;；\s\-]+", text)
    lines: list[str] = []
    previous = None
    for run in runs:
        cleaned = re.sub(r"\s+", " ", run).strip()
        if len(cleaned) < 2:
            continue
        if not (re.search(r"[\u4e00-\u9fff]", cleaned) or re.search(r"\d+\s*(元|/)", cleaned)):
            continue
        if cleaned != previous:
            lines.append(cleaned)
        previous = cleaned
    return lines


def quote_specs() -> Iterable[QuoteSpec]:
    foreign_to_chinese = ("en->zh", "ja->zh")
    chinese_to_foreign = ("zh->en", "zh->ja")

    for scope, price in [
        ("普通类/技术类", 200),
        ("合同、条款类", 240),
        ("公关、新闻稿", 400),
        ("菜单、铭牌、产品名和简介、广告语、古文等文学类", 400),
    ]:
        yield QuoteSpec(foreign_to_chinese, service_scope_for(scope), scope, price, "per_1000_chars", "1. 外(英、日)译中，并输入排版")
    yield QuoteSpec(foreign_to_chinese, "presentation", "幻灯片类", 30, "per_slide", "1. 外(英、日)译中，并输入排版", "每个幻灯片外文单词数<80时")

    for scope, price in [
        ("普通类/技术类", 280),
        ("合同、条款类", 320),
        ("公关、新闻稿", 560),
        ("菜单、铭牌、产品名和简介、广告语、古文等文学类", 560),
    ]:
        yield QuoteSpec(chinese_to_foreign, service_scope_for(scope), scope, price, "per_1000_chars", "2. 中译外(英、日)，并输入排版")
    yield QuoteSpec(chinese_to_foreign, "native_polishing", "中国译员翻译后加外籍译员母语润稿", 800, "per_1000_chars", "2. 中译外(英、日)，并输入排版")
    yield QuoteSpec(chinese_to_foreign, "native_translation", "直接外籍译员母语翻译", 1200, "per_1000_chars", "2. 中译外(英、日)，并输入排版")
    yield QuoteSpec(("en->en",), "native_polishing", "英文外籍译员母语润稿", 1.4, "per_english_word", "2. 中译外(英、日)，并输入排版")

    for pairs, price_in, price_out, label, scope in [
        (("fr", "de"), 300, 400, "法/德", "general"),
        (("ko",), 340, 450, "韩", "general"),
        (("ru", "it", "es"), 450, 550, "俄/意/西班牙等小语种", "general"),
        (("ar", "da", "pt", "nl", "sv", "no", "el", "tr"), 600, 700, "阿拉伯、丹麦、葡萄牙、荷兰、瑞典、挪威、希腊、土耳其等欧洲稀有语种", "rare_language"),
    ]:
        yield QuoteSpec(tuple(f"{lang}->zh" for lang in pairs), scope, label, price_in, "per_1000_chars", "3. 其它语种和中文间的翻译")
        yield QuoteSpec(tuple(f"zh->{lang}" for lang in pairs), scope, label, price_out, "per_1000_chars", "3. 其它语种和中文间的翻译")

    yield QuoteSpec(("fr->en", "de->en"), "bilingual_foreign", "法/德译英", 1.14, "per_source_word", "4. 双外语翻译")
    yield QuoteSpec(("en->fr", "en->de"), "bilingual_foreign", "英译法/德", 1.08, "per_english_word", "4. 双外语翻译")
    yield QuoteSpec(("en->ja",), "bilingual_foreign", "英译日", 0.96, "per_english_word", "4. 双外语翻译")
    yield QuoteSpec(("ja->en",), "bilingual_foreign", "日译英", 0.80, "per_japanese_char", "4. 双外语翻译")

    yield QuoteSpec(("",), "formatting", "纯文字输入并排版(非PPT)", 20, "per_a4_original", "5. 输入或排版服务")
    yield QuoteSpec(("",), "formatting", "PowerPoint排版(客户不提供PPT原稿软件)", 15, "per_slide", "5. 输入或排版服务")


def service_scope_for(scope_label: str) -> str:
    if "合同" in scope_label or "条款" in scope_label:
        return "legal"
    if "技术" in scope_label:
        return "technical"
    if "公关" in scope_label or "新闻稿" in scope_label:
        return "marketing"
    if "菜单" in scope_label or "文学" in scope_label or "广告语" in scope_label:
        return "literary_marketing"
    return "general"


def build_rows() -> list[dict]:
    rows = []
    for spec in quote_specs():
        for language_pair in spec.language_pairs:
            language_label = LANG_LABELS.get(language_pair, "无固定语种")
            title = f"{language_label}{spec.scope_label}报价 {spec.price:g}元/{unit_label(spec.unit)}"
            content = (
                f"{language_label}可做，{spec.scope_label}报价 {spec.price:g} 元 / {unit_label(spec.unit)}。"
                f"来源：笔译报价单（中外文互译）{spec.source_section}。"
            )
            if spec.note:
                content += f"备注：{spec.note}。"
            if spec.unit == "per_1000_chars":
                content += "计价说明：中文字符包含标点符号，不计空格、空行；中外互译500中文字符起算。"
            rows.append(
                {
                    "title": title,
                    "content": content,
                    "knowledge_type": "pricing",
                    "chunk_type": "rule",
                    "business_line": "translation",
                    "sub_service": "written_translation" if spec.service_scope != "formatting" else "formatting",
                    "language_pair": language_pair,
                    "service_scope": spec.service_scope,
                    "region": "",
                    "customer_tier": "",
                    "priority": 95,
                    "risk_level": "high",
                    "effective_from": "2026-04-20",
                    "effective_to": "2030-12-31",
                    "unit": spec.unit,
                    "currency": "CNY",
                    "price_min": spec.price,
                    "price_max": spec.price,
                    "min_charge": "",
                    "urgent_multiplier": "",
                    "tax_policy": "",
                    "tags": f"source=笔译报价.doc;section={spec.source_section};scope={spec.scope_label}",
                }
            )
    return rows


def unit_label(unit: str) -> str:
    return {
        "per_1000_chars": "1000中文字符",
        "per_slide": "幻灯片",
        "per_english_word": "英文单词",
        "per_source_word": "原文单词",
        "per_japanese_char": "日文字符",
        "per_a4_original": "A4原稿",
    }.get(unit, unit)


def write_workbook(rows: list[dict], output: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "kb_pricing_import"
    sheet.append(COLUMNS)
    for row in rows:
        sheet.append([row.get(column, "") for column in COLUMNS])
    for index, column in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[chr(64 + index) if index <= 26 else "Z"].width = min(max(len(column) + 2, 12), 32)
    workbook.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract legacy Word quote sheet into KB pricing import rows.")
    parser.add_argument("--source", type=Path, default=SOURCE_DOC)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_lines = extract_doc_text(args.source)
    raw_text = "\n".join(raw_lines)
    raw_path = args.out_dir / "笔译报价_raw_text.txt"
    raw_path.write_text(raw_text, encoding="utf-8")

    rows = build_rows()
    excel_path = args.out_dir / "笔译报价_结构化入库.xlsx"
    write_workbook(rows, excel_path)

    required_hits = [
        "翻译报价单",
        "中译英或日",
        "法/德",
        "400元 / 1000中文字符",
        "英文外籍译员母语润稿",
        "英译日",
        "日译英",
    ]
    report = {
        "source": str(args.source.relative_to(ROOT)),
        "raw_text": str(raw_path.relative_to(ROOT)),
        "structured_excel": str(excel_path.relative_to(ROOT)),
        "raw_meaningful_lines": len(raw_lines),
        "structured_pricing_rows": len(rows),
        "source_hits": {hit: hit in raw_text for hit in required_hits},
        "sample_rows": rows[:8],
    }
    report_path = args.out_dir / "笔译报价_结构化报告.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

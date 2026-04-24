from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


OUT_FILE = Path(__file__).resolve().parent / "知识库导入测试数据.xlsx"
MARK = "e2e-ui-20260424"


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "kb_import"
    ws.append(
        [
            "title",
            "content",
            "knowledge_class",
            "auto_split",
            "business_line",
            "language_pair",
            "service_scope",
            "priority",
            "risk_level",
            "effective_from",
            "effective_to",
            "unit",
            "currency",
            "price_min",
            "price_max",
            "min_charge",
            "tax_policy",
            "tags",
        ]
    )
    ws.append(
        [
            f"{MARK} translation quote baseline",
            "English to French general business translation is quoted at 220 CNY per 1000 source words. Minimum charge is 300 CNY. Tax is excluded and urgent fee must be confirmed separately.",
            "",
            0,
            "translation",
            "en->fr",
            "general",
            95,
            "high",
            "2026-04-24",
            "2030-12-31",
            "per_source_word",
            "CNY",
            220,
            220,
            300,
            "tax excluded",
            f"{MARK},pricing",
        ]
    )
    ws.append(
        [
            f"{MARK} urgent fee constraint",
            "Urgent surcharge cannot be promised as a fixed amount before confirming file volume, delivery time and quality requirements with operations.",
            "pricing_constraint",
            0,
            "translation",
            "en->fr",
            "general",
            90,
            "high",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            f"{MARK},constraint",
        ]
    )
    ws.append(
        [
            f"{MARK} onboarding faq pack",
            "Q1: What information should be collected before evaluation? A1: Collect the source file, language pair, intended use, expected deadline, and whether the client needs formatting consistency. If these facts are incomplete, only give a general introduction and do not promise a fixed plan. Q2: How should formatting requirements be handled? A2: Confirm whether the client needs layout consistency, editable files, or image-to-text reconstruction, then align the handling method with operations before delivery. Q3: What happens after delivery? A3: Deliver the final file, ask the client to confirm receipt, collect revision feedback, and record any follow-up requirement for the next round.",
            "faq",
            1,
            "translation",
            "en->fr",
            "general",
            80,
            "medium",
            "2026-04-24",
            "2030-12-31",
            "",
            "",
            "",
            "",
            "",
            "",
            f"{MARK},process",
        ]
    )
    ws.append(
        [
            f"{MARK} language capability",
            "The team can handle English to French general business translation, quotation explanation and delivery planning with manual review.",
            "capability",
            0,
            "translation",
            "en->fr",
            "general",
            80,
            "medium",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            f"{MARK},capability",
        ]
    )
    wb.save(OUT_FILE)
    print(OUT_FILE)


if __name__ == "__main__":
    main()

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_helpers() -> dict[str, Any]:
    wanted = {
        "_normalize_mail_recipient_domain",
        "_mail_brand_display_text",
        "_mail_is_own_company_name",
        "_mail_remove_internal_business_codes",
        "_mail_prompt_fact",
        "_mail_prompt_variable_value",
        "_mail_prompt_contract_case_examples",
        "_mail_prompt_customer_salutation",
        "_mail_prompt_company_short_name",
        "_mail_prompt_strip_company_suffixes",
        "_mail_prompt_company_six_char_boundary",
        "_mail_prompt_success_case_studies",
        "_mail_prompt_history_summary",
        "_mail_prompt_template_variable_values",
        "_mail_apply_prompt_template_variables",
        "_MAIL_PROMPT_COMPANY_NAME_BY_DOMAIN",
        "_MAIL_PROMPT_COMPANY_PREFIX_ALIASES",
        "_MAIL_PROMPT_COMPANY_LEGAL_SUFFIXES",
        "_MAIL_PROMPT_COMPANY_REGION_PREFIXES",
        "_MAIL_PROMPT_COMPANY_GENERIC_SUFFIXES",
        "_MAIL_PROMPT_COMPANY_PROTECTED_BOUNDARY_WORDS",
    }
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            selected.append(node)
        elif isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted:
                selected.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in wanted:
            selected.append(node)
    namespace: dict[str, Any] = {
        "Any": Any,
        "MailDraftIntentProfile": Any,
        "re": re,
        "sanitize_text": lambda value: str(value or "").strip(),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(Path(__file__).with_name("main.py")), "exec"), namespace)
    return namespace


def _profile(**overrides):
    values = {
        "contact_email": "contact@example.com",
        "company_name": "示例有限公司",
        "recipient_name": "王芳",
        "recipient_english_name": "",
        "recipient_gender": "女",
        "seller_name": "测试销售",
        "recent_opportunities": "",
        "ongoing_contracts": "",
        "contact_recent_followup": "",
        "prompt_contract_case_examples": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MailPromptWildcardChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_helpers()

    def test_company_record_suffix_two_is_not_part_of_short_name(self):
        short_name = self.helpers["_mail_prompt_company_short_name"]
        self.assertEqual(short_name(_profile(company_name="3M2有限公司")), "3M")
        self.assertEqual(short_name(_profile(company_name="欧莱雅2有限公司")), "欧莱雅")

    def test_solventum_domain_uses_confirmed_chinese_company_name(self):
        profile = _profile(contact_email="buyer@solventum.com", company_name="Solventum China Ltd.")
        self.assertEqual(self.helpers["_mail_prompt_company_short_name"](profile), "舒万诺")

    def test_danaher_is_not_blindly_truncated_to_six_characters(self):
        profile = _profile(company_name="丹纳赫商务服务（上海）有限公司")
        self.assertEqual(self.helpers["_mail_prompt_company_short_name"](profile), "丹纳赫")

    def test_legal_and_generic_suffixes_are_removed_without_broken_words(self):
        short_name = self.helpers["_mail_prompt_company_short_name"]
        cases = {
            "空气化工产品（天津）有限公司": "空气化工",
            "空气化工产品系统（上海）有限公司": "空气化工",
            "空气化工产品（中国）投资有限公司": "空气化工",
            "百特医疗用品贸易（上海）有限公司": "百特医疗",
            "BMG企业管理咨询（上海）有限公司": "BMG",
            "万城国际咨询服务有限公司": "万城国际",
            "上海伏勒密展览服务有限公司": "伏勒密",
            "上海东方明珠进出口有限公司": "东方明珠",
            "上海万国纸业企业管理有限公司": "万国纸业",
            "上海919文化传播有限公司": "919",
        }
        for company, expected in cases.items():
            with self.subTest(company=company):
                self.assertEqual(short_name(_profile(company_name=company)), expected)

    def test_six_character_boundary_backs_up_before_generic_word(self):
        short_name = self.helpers["_mail_prompt_company_short_name"]
        cases = {
            "上海中医药国际服务贸易促进中心": "中医药",
            "伟控电气有限公司上海": "伟控电气",
            "上海詹鼎智能科技发展有限公司": "詹鼎",
            "上海美特斯邦威服饰有限公司": "美特斯邦威",
            "纳博特斯克（上海）传动设备商贸有限公司": "纳博特斯克",
            "上海乔治费歇尔管路系统有限公司": "乔治费歇尔",
            "雨果博斯（上海）商贸有限公": "雨果博斯",
            "阿特拉斯·科普柯（沈阳）建筑矿山设备有限公司": "阿特拉斯",
            "上海中熠投资有限管理公司": "中熠投资",
            "捷图科技科技发展": "捷图",
            "图尔克 （天津） 传感器有限公司上海代表处": "图尔克",
        }
        for company, expected in cases.items():
            with self.subTest(company=company):
                self.assertEqual(short_name(_profile(company_name=company)), expected)

    def test_industry_brand_words_are_preserved(self):
        short_name = self.helpers["_mail_prompt_company_short_name"]
        self.assertEqual(short_name(_profile(company_name="三菱化学（中国）有限公司")), "三菱化学")
        self.assertEqual(short_name(_profile(company_name="奥的斯电梯有限公司")), "奥的斯电梯")

    def test_case_studies_wildcard_is_assigned_from_retrieved_contract_cases(self):
        profile = _profile(
            prompt_contract_case_examples=[
                {
                    "contract_id": "CASE-001",
                    "business_type": "多媒体",
                    "product_name_all": "培训视频本地化",
                    "business_line_inferred": "multimedia",
                    "mail_case_text": "为同类客户统一处理字幕、配音和成片交付。",
                }
            ]
        )
        values = self.helpers["_mail_prompt_template_variable_values"](
            profile,
            industry="生命科学",
            crm_history="历史合作",
        )
        rendered = self.helpers["_mail_apply_prompt_template_variables"](
            "公司：{company_name}\n成功案例：{case_studies}",
            values,
        )

        self.assertNotIn("{case_studies}", rendered)
        self.assertIn("CASE-001", rendered)
        self.assertIn("字幕、配音和成片交付", rendered)


if __name__ == "__main__":
    unittest.main()

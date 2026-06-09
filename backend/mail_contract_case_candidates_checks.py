import unittest
import sys
import os
import datetime
import decimal
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.main import (
    app,
    _desensitize_company_name,
    _generate_mail_case_text,
    _mail_contract_case_business_line
)
from backend.database import SessionLocal, MailContractCase

class TestMailContractCaseCandidates(unittest.TestCase):
    def test_desensitize_company_name(self):
        test_cases = [
            ("爱通物流有限公司", "某国际物流企业"),
            ("思源电气股份有限公司", "某上市电力设备巨头"),
            ("欧莱雅（中国）有限公司", "某知名美妆巨头"),
            ("3M中国有限公司", "某跨国制造集团"),
            ("南德认证检测公司", "某跨国检测认证机构"),
            ("英飞凌科技", "某知名半导体厂商"),
            ("CHAGEE （CA） LLC", "某知名新式茶饮巨头"),
            ("博柏利上海", "某知名奢侈品巨头"),
            ("拜耳医药", "某知名医药巨头"),
            ("碧迪医疗器械", "某知名医疗器械巨头"),
            ("东陶卫浴", "某知名卫浴品牌"),  # will match "东陶" -> "某知名卫浴品牌"
            ("高仪卫浴", "某知名卫浴建材企业"),
            ("渣打银行", "某知名外资银行"),
            ("罗兰贝格咨询", "某知名管理咨询公司"),
            ("地中海邮轮", "某知名国际邮轮公司"),
            ("东电电子", "某知名半导体设备巨头"),
            ("无名氏企业", "某知名企业")
        ]
        for name, expected in test_cases:
            res = _desensitize_company_name(name)
            self.assertEqual(res, expected, f"Failed for {name}: got {res}, expected {expected}")

    def test_mail_contract_case_business_line_priority(self):
        # "展会搭建;礼品;印刷" -> exhibition priority over printing
        line = _mail_contract_case_business_line("展会搭建;礼品;印刷", "展会搭建;圆珠笔;印刷品")
        self.assertEqual(line, "exhibition")

        # "口译;同传设备租赁;设计印刷" -> interpretation priority
        line = _mail_contract_case_business_line("口译;同传设备租赁;设计印刷", "英语;同传耳机")
        self.assertEqual(line, "interpretation")

        # "礼品;印刷" -> gift priority over printing
        line = _mail_contract_case_business_line("礼品;印刷", "不干胶;手机充电线")
        self.assertEqual(line, "gift")

    def test_generate_mail_case_text_length_and_content(self):
        # We want to test that case texts generated for different inputs are under 50 characters
        test_inputs = [
            ("爱通物流", "笔译", "英译中", "文献翻译"),
            ("思源电气", "笔译", "中译英", "合同协议翻译"),
            ("欧莱雅", "口译", "英语", "同传设备耳机"),
            ("南德认证", "展会搭建;礼品;印刷", "展会搭建;圆珠笔", "CMEF上海"),
            ("英飞凌", "口译;同传设备租赁", "英语;同传主机", "技术峰会"),
            ("CHAGEE", "口译", "英语", "洛杉矶陪同口译"),
            ("地中海邮轮", "设计印刷", "易拉宝;彩色制版", "易拉宝印刷"),
            ("东陶", "设计印刷", "产品手册;印刷", "中文版手册印刷"),
            ("3M", "礼品;印刷", "充电宝", "移动电源定制"),
            ("高仪", "输入排版;笔译", "德译中", "锅炉图纸排版")
        ]
        for comp, biz, prod, desc in test_inputs:
            text_res = _generate_mail_case_text(comp, biz, prod, desc)
            self.assertTrue(len(text_res) <= 50, f"Text too long ({len(text_res)} chars): {text_res}")
            # Ensure desensitized company is used
            des_comp = _desensitize_company_name(comp)
            self.assertIn(des_comp, text_res, f"Expected {des_comp} in {text_res}")
            # Ensure real company name, brands, or model numbers do not leak
            self.assertNotIn(comp, text_res)

    def test_list_mail_contract_case_candidates_endpoint(self):
        client = TestClient(app)
        db = SessionLocal()
        try:
            # Clean up potential leftovers
            db.query(MailContractCase).filter(MailContractCase.contract_id == "XS_TEST_CHECK_99").delete()
            db.commit()

            # Insert a mock contract case
            temp_case = MailContractCase(
                contract_id="XS_TEST_CHECK_99",
                customer_id="KH_TEST_99",
                contact_id="KH_TEST_99-001",
                total_money=decimal.Decimal("15000.00"),
                amount_bucket="gt_10000",
                product_name_all="笔译;口译",
                business_type="翻译;同传",
                contract_description="技术手册笔译及年会现场同传",
                company_name="测试化学工业有限公司",
                input_time=datetime.datetime(2026, 6, 9, 12, 0, 0),
                contract_time=datetime.datetime(2026, 6, 9, 12, 0, 0),
                start_time=datetime.datetime(2026, 6, 9, 12, 0, 0),
                end_time=datetime.datetime(2026, 6, 19, 12, 0, 0),
                business_line_inferred="translation",
                language_pair_inferred="英语",
                industry_inferred="chemical",
                quality_flags=["可初筛"],
                mail_case_text="曾为某知名化学巨头提供技术手册笔译及年会同传服务。",
                ingested_to_knowledge=False,
                desensitized=False
            )
            db.add(temp_case)
            db.commit()

            # Call the endpoint
            response = client.get("/api/v1/mail/contract-case-candidates?limit=10&min_amount=10000&product_keyword=笔译")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Assert schema and values
            self.assertEqual(data["version"], "mail_contract_case_candidates.v2")
            self.assertEqual(data["source"], "PostgreSQL local mail_contract_case cache")
            self.assertTrue(data["ingested_to_knowledge"])
            self.assertIn("total", data)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["limit"], 10)
            self.assertTrue(data["pages"] >= 1)
            
            # Verify our inserted contract is present
            items = data["items"]
            matched = [item for item in items if item["contract_id"] == "XS_TEST_CHECK_99"]
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["customer_id"], "KH_TEST_99")
            self.assertEqual(matched[0]["total_money"], 15000.00)
            self.assertEqual(matched[0]["business_line_inferred"], "translation")
            self.assertEqual(matched[0]["industry_inferred"], "chemical")
            
        finally:
            # Clean up
            db.query(MailContractCase).filter(MailContractCase.contract_id == "XS_TEST_CHECK_99").delete()
            db.commit()
            db.close()

if __name__ == "__main__":
    unittest.main()

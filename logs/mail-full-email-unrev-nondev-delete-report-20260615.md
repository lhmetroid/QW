# 邮件黄金库 · 删除"未评审 full_email 中非开发邮件"报告

时间：2026-06-15 · 指令：切片 `full_email` 且**状态=未评审**的，**不是开发邮件的删除**；**不认可(rejected)人工确认过的保留**；approved/needs_revision 不动。

## 起因
用户指出 #474（拖链综合样本 KABELSCHLEPP 印刷前的最终确认）被系统 `selection_reason` 标成"宣传邮件"，实为印刷定稿确认（操作类）。核查发现 `full_email_promo_reason_v1` 这个 promo 分类器**几乎对所有邮件都判 is_promotional=True**（28/28 rejected 全被标"宣传邮件"），不可信。故对未评审池按 SOP §3 强操作信号清理混入的非开发邮件。

## 精度把控（关键：不裸杀服务词）
SOP §61 明确"印刷/制版/打样/报价/交付"等在服务介绍类营销邮件里是正常内容。初版宽口径误判 349/1109（抽样见大量"我是事必达的X…提供翻译印刷服务"开发邮件被误标）。**两轮收紧**到"邮件目的本身即交易/结算/确认"的强信号后：
- 仅 **15 条**命中，且**逐条人工核验全部为纯操作/交易邮件**（对账/付款/费用明细/翻译费结算/三联单/合同版本确认）。
- 误判的开发/介绍邮件（即便附带报价单或列过往服务清单）一律**保留**。
- 拿不准的一律保留（偏保守，可能漏删个别，宁可少删不误删）。

## 删除清单（15 条，已全量备份，可恢复）
| 编号 | 标题(注:部分为前序替换的通用标题) | 实际内容 |
|---|---|---|
| mail_gold_v2_1005_scn_2017 | 翻译费用 | 订单明细/总计RMB |
| mail_gold_v2_1011_scn_2018 | 27April ING Event | 会议同传合同版本请确认 |
| mail_gold_v2_1016_scn_2017 | 三联单 | 三联单快递已送出 |
| mail_gold_v2_1018_scn_2019 | 关于翻译费支付 | 付款催办/发票号 |
| mail_gold_v2_1043_scn_2019 | 继续为您提供多业务支持 | 对帐明细清单/未付款 |
| mail_gold_v2_1044_scn_2020 | 继续为您提供多业务支持 | 对账单/预付款 |
| mail_gold_v2_1045_scn_2020 | 继续为您提供多业务支持 | 翻译清单/出具PO/付款 |
| mail_gold_v2_1055_scn_2018 | 翻译费用付款查询--363元 | 催付款 |
| mail_gold_v2_1061_scn_2018 | 与您分享可参考的综合服务场景 | 对帐明细清单核对 |
| mail_gold_v2_1064_scn_2018 | 事必达翻译(关于happybaby翻译费用) | 对帐明细/付款 |
| mail_gold_v2_1086_scn_2018 | 翻译制作服务结算单 | 未结算服务清单 |
| mail_gold_v2_1087_scn_2018 | 关于翻译服务费支付 | 对账/账单 |
| mail_gold_v2_1182_scn_2022 | 未清算账单报备 | 未结算清单/发票抬头 |
| mail_gold_v2_857_scn_2023 | 翻译费用付款日期查询 | 付款查询/PO/发票 |
| mail_gold_v2_963_scn_2022 | 翻译费用 | 合作清单/付款 |

## 结果
- `email_fragment_asset` 删除 **15** 条（仅 full_email + 未评审 + 纯操作类）；附带清理 effect_feedback 子行（如有）。
- full_email 总数：1277 → **1262**；未评审 1109 → **1094**；rejected 28 / approved 59 / needs_revision 81 **均未改动**（不认可保留）。
- **备份**：`logs/mail-full-email-unrev-nondev-delete-backup-20260615.json`（15 条完整行，含 content/source_snapshot，可一键回插恢复）。

## 产物
- 脚本：`scratch/flag_nondev_unreviewed.py`（默认 dry-run+备份，`--apply-delete` 才删）。
- dry-run/apply 报告：`logs/mail-full-email-unrev-nondev-dry-run-v3-20260615.json`、`...delete-apply-20260615.json`。

## 备注与下一步
- 本删除偏保守（高精度），未评审池里可能仍有少量未触发强信号的操作邮件；如需更彻底，建议人工抽检或用 LLM 逐封判定（当前 promo 分类器不可信，建议弃用其 is_promotional/selection_reason 作为判据）。
- `selection_reason` "宣传邮件…"模板对操作类是误标，作为独立问题待修（可重算或弃用该字段）。

# 邮件黄金库 full_email #301-#400 逐条复查清理记录

时间：2026-06-15 13:52 +08:00

## 处理范围

- 来源：`email_fragment_asset`
- 条件：`source_type = mail_gold_seed`、`function_fragment = full_email`
- 编号口径：前端黄金范例库第一列 `#`，即 `source_snapshot.candidate_rank`
- 目标编号：`#301` 到 `#400`
- 当前库内现存：47 条
- 已不存在：53 条

已不存在编号：

`304, 307, 309, 310, 311, 312, 313, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 332, 333, 334, 337, 338, 339, 341, 342, 343, 346, 348, 351, 352, 354, 356, 357, 361, 363, 364, 378, 379, 380, 381, 382, 383, 384, 385, 386, 388, 389, 390, 391, 394, 395, 396, 400`

## 修正内容

- 删除/泛化年份、节日、相对日期、蛇年谐音、去年/最近/下周等时效内容。
- 脱敏客户公司、品牌、联系人、销售名、部门名和项目名。
- 删除电话、邮箱、地址、微信/二维码、订单下载、质量评价、报价/PO 等事务或联系方式内容。
- 软化不可验证数字与夸张表达，如多年经验、大批量内容、多场会议服务经验等。
- 规范标题和正文段落，修复破损标题、重复 `[发件人]`、`SpeedAsia（SpeedAsia）` 等问题。
- 对清理后内容不足、不适合作为完整黄金邮件的条目，保留记录但关闭生成可用开关。

## 结果

- 写库修正：47 条。
- 最终 postcheck：`changed_count = 0`，`residual_count = 0`。
- 内容不足进入人工 hold：9 条。
- 9 条 hold 记录均已关闭 `publishable`、`allowed_for_generation`、`usable_for_reply`。

人工 hold 编号：

| 编号 | source_ref | 标题 | 原因 |
| --- | --- | --- | --- |
| #335 | mail_gold_v2_335_scn_2025 | 翻译印刷长期协议 | 清理后正文不足 |
| #336 | mail_gold_v2_336_scn_2025 | DEI同传会议翻译 | 清理后正文不足 |
| #345 | mail_gold_v2_345_scn_2025 | 某工业客户 产品宣传资料 | 清理后正文不足 |
| #350 | mail_gold_v2_350_scn_2025 | 继续为您提供多业务支持 | 清理后正文不足 |
| #362 | mail_gold_v2_362_scn_2025 | 某客户同传安全培训 | 清理后正文不足 |
| #369 | mail_gold_v2_369_scn_2025 | 与您分享可参考的综合服务场景 | 清理后正文不足 |
| #370 | mail_gold_v2_370_scn_2025 | 与您分享可参考的综合服务场景 | 清理后正文不足 |
| #397 | mail_gold_v2_397_scn_2025 | 企业会议同传 | 清理后正文不足 |
| #398 | mail_gold_v2_398_scn_2025 | 与您分享可参考的综合服务场景 | 清理后正文不足 |

## 报告文件

- 脚本：`scratch/cleanup_mail_full_email_rank_301_400.py`
- 最终写库：`logs/mail-full-email-rank-301-400-cleanup-apply-pass3-20260615.json`
- 最终复查：`logs/mail-full-email-rank-301-400-cleanup-postcheck-pass3-20260615.json`

## 验证

```powershell
python -m py_compile scratch/cleanup_mail_full_email_rank_301_400.py
$env:PYTHONIOENCODING='utf-8'; python scratch/cleanup_mail_full_email_rank_301_400.py --report logs/mail-full-email-rank-301-400-cleanup-postcheck-pass3-20260615.json
git diff --check -- scratch/cleanup_mail_full_email_rank_301_400.py PROGRESS.md TASK_HANDOFF.md logs/codex-run.log
```

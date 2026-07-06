# 邮件黄金范例库 full_email 人工点评问题汇总与修正记录

时间：2026-06-15

## 处理范围

- 切片类型：`full_email`
- 来源：`email_fragment_asset.source_type = mail_gold_seed`
- 评审范围：
  - `review_status = needs_revision`：65 条
  - 未评审 / 空状态：1253 条
- 合计目标：1318 条
- 本次不处理：`approved` 34 条、`rejected` 11 条
- 本次只改黄金库资产表的 `title/content/source_snapshot`，不改原始邮件表、不改 CRM、不改真实发信配置。
- 评审状态不自动改成 `approved`，保留人工复审入口。

## 先罗列：人工点评中的主要问题

从 65 条 `needs_revision + full_email` 的人工点评汇总出以下问题：

| 问题类型 | 数量 | 典型点评/表现 | 修正方式 |
|---|---:|---|---|
| 时间/节日信息 | 31 | 新年、马年、蛇年、端午、五一、2024/2025/2026、3月26日等 | 删除具体年份、节日问候、日期、季节寒暄、工作日交稿等时效句 |
| 未脱敏 | 24 | Tiffany、吴磊/Leo、Alice、徐杰、高仪、阿科玛、雅马哈、贝亲、贵行部门名等 | 替换为 `[发件人]`、`[客户称呼]`、`某行业客户`、`贵司/相关部门` |
| 格式/分段混乱 | 6 | 未分行、案例堆成一段、项目符号混乱 | 统一换行、项目符号、段落间距，删除孤立标点段 |
| 乱码/异常字符 | 4 | 孤立 `?`、异常符号、残留冒号行 | 删除异常符号和孤立标点行 |
| 主题问题 | 1 | 主题含时间或不适合作为黄金模板 | 改为通用业务型主题 |
| 其他短点评 | 10 | 只写人名、公司名、附件、无内容等 | 按脱敏、格式、时间、联系方式规则统一复查 |

额外发现：未评审 full_email 中大量邮件签名或正文残留“微信/二维码/加微信”等私域联系方式，已同步清理。

## 执行结果

- 首轮 dry-run：目标 1318 条，预计变更 1286 条。
- 多轮补强后最终 apply：
  - `logs/mail-full-email-cleanup-apply-pass6-20260615.json`
  - 本轮 pass6 变更 266 条，补清微信行、二维码行等残留。
- 最终 postcheck：
  - `logs/mail-full-email-cleanup-final-postcheck-pass6-20260615.json`
  - `changed_count = 0`
  - `residual_count = 0`
  - 目标范围内 `微信` 残留：0

## 验证命令

```powershell
python -m py_compile scratch/cleanup_mail_full_email_reviews.py
$env:PYTHONIOENCODING='utf-8'; python scratch/cleanup_mail_full_email_reviews.py --report logs/mail-full-email-cleanup-final-postcheck-pass6-20260615.json
git diff --check -- scratch/cleanup_mail_full_email_reviews.py logs/mail-full-email-cleanup-apply-pass6-20260615.json logs/mail-full-email-cleanup-final-postcheck-pass6-20260615.json
```

## 说明

- 所有被修改的资产均在 `source_snapshot.manual_cleanup` 写入了清理标记、清理时间、原评审状态和规则说明，便于追踪。
- 完整变更前后内容保存在 apply JSON 报告中，可用于回看和人工复审。
- 本轮没有把 `needs_revision` 自动改为 `approved`，因为内容清理不等于人工认可。


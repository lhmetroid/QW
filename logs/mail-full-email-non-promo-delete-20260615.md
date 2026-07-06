# 邮件黄金库 full_email 疑似非宣传邮件删除记录

时间：2026-06-15 12:10 +08:00

## 删除范围

- 来源：`logs/mail-full-email-promo-analysis-apply-20260615.json` 中的 `non_promotional` 清单。
- 目标：`email_fragment_asset.source_type = mail_gold_seed` 且 `function_fragment = full_email`。
- 目标编号数：77。
- 实际匹配并删除黄金库切片：77。
- 同步删除人工评审记录：1。

## 备份与报告

- 删除前备份：`logs/mail-full-email-non-promo-delete-backup-20260615.json`
- dry-run 报告：`logs/mail-full-email-non-promo-delete-dry-run-20260615.json`
- apply 报告：`logs/mail-full-email-non-promo-delete-apply-20260615.json`
- 删除脚本：`scratch/delete_non_promo_full_email_seeds.py`

## 删除后验证

- 77 个目标 `fragment_id` 在 `email_fragment_asset` 中剩余：0。
- 77 个目标 `fragment_id` 在 `mail_gold_seed_review` 中剩余：0。
- 当前 `mail_gold_seed + full_email` 剩余：1286。
- 当前剩余 `full_email` 中 `promo_analysis.is_promotional = false` 的记录：0。

## 验证命令

```bash
python -m py_compile scratch/delete_non_promo_full_email_seeds.py
python scratch/delete_non_promo_full_email_seeds.py --report logs/mail-full-email-non-promo-delete-dry-run-20260615.json
python scratch/delete_non_promo_full_email_seeds.py --apply --report logs/mail-full-email-non-promo-delete-apply-20260615.json
git diff --check -- scratch/delete_non_promo_full_email_seeds.py PROGRESS.md TASK_HANDOFF.md logs/codex-run.log
```

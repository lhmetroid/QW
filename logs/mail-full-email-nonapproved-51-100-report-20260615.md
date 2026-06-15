# 邮件黄金库 · 非认可合并集(needs_revision + rejected) full_email 第 51–100 条处理报告

时间：2026-06-15 · 范围：`email_fragment_asset`(`source_type=mail_gold_seed` + `function_fragment=full_email`) 中**非认可**(`review_status` ∈ {needs_revision, rejected})共 **109 条**，按 `source_ref` 排序取**第 51–100 条**(实取 50 条)。

## 处理口径（与 SOP 一致）
- **needs_revision(需修改)**：按点评仅改正文/标题（已在 v1.7.272/273 round2 完成）。本批落在区间内的 38 条**已清洗、幂等无新改动**。
- **rejected(不认可)**：人工已判不认可。原任务对"非认可"的动作是**逐行检查**（是否满足、是否开发类邮件），**不改正文**（与 round1 "本次不处理 rejected" 口径一致）。本批 12 条 rejected → 仅做开发类判定 + 脱敏残留核验 + 记录编号。

## 本批分布
- needs_revision：**38 条**（`mail_gold_v2_174`~`447` 区间，已 round2 清洗）。
- rejected：**12 条**。

## rejected 12 条逐行核验结论

### 非开发/操作类（11 条，应保持 rejected，不入库）

| 编号 | 点评 | 非开发原因 |
|---|---|---|
| `mail_gold_v2_256_scn_2026` | 有特殊性 | 人工标特殊/边缘案例 |
| `mail_gold_v2_257_scn_2026` | 有特殊性 | 人工标特殊/边缘案例 |
| `mail_gold_v2_267_scn_2026` | 项目跟进 | 项目跟进往来，非主动开发外联 |
| `mail_gold_v2_287_scn_2026` | 不特殊性 | 人工标边缘 |
| `mail_gold_v2_387_scn_2025` | 9-12点 静安教室 紧急安排同传老师 | 同传排期/调度（操作类） |
| `mail_gold_v2_409_scn_2025` | 下午增加1名同传翻译Shawn，4小时 | 项目沟通/调度（操作类） |
| `mail_gold_v2_415_scn_2025` | 请查收附件 | 附件交付（操作类） |
| `mail_gold_v2_416_scn_2025` | 附上200本笔记本定制的报价 | 报价单（交易类） |
| `mail_gold_v2_421_scn_2025` | 关于2日会议同传是否有变化…先回复邮件Book老师 | 会议确认/排期（操作类） |
| `mail_gold_v2_428_scn_2025` | 无内容 | 空内容 |
| `mail_gold_v2_434_scn_2025` | 若无问题，我们先安排打样 | 打样/生产（操作类） |

### 开发类但有残留真实实体（1 条，记录交人工确认）

| 编号 | 点评 | 残留疑似实体 | 建议 |
|---|---|---|---|
| `mail_gold_v2_290_scn_2026` | (空) | 中文公司 `信息科技发展有限公司` | 保持 rejected；如后续要复用需先泛化该公司名 |

> 另：rejected 中 `mail_gold_v2_256`(残留 `Sandy`)、`mail_gold_v2_257`(残留 `Eunice`) 含人名，因维持 rejected、不进 RAG 召回，风险低；如人工后续改判需复用，再补脱敏。

## 结论
- 本批 50 条：38 条 needs_revision 已清洗（幂等无新改动）；12 条 rejected 全部完成开发类判定与残留核验，**11 条确认非开发/操作类应保持 rejected**，1 条(290)记录真实公司残留待人工确认。
- **未对任何 rejected 条目改正文**（符合 SOP：人工已判不认可，仅检查不修改）。

## 产物
- 明细：`scratch/analyze_nonapproved_51_100.py` → `scratch/nonapproved_51_100.json`
- 本报告：`logs/mail-full-email-nonapproved-51-100-report-20260615.md`

# 邮件黄金范例库 · needs_revision(需修改) full_email 第二轮(更细脱敏)处理报告

时间：2026-06-15 · 范围：`email_fragment_asset` 中 `source_type=mail_gold_seed` + `function_fragment=full_email` + 评审状态 `needs_revision`，按 `source_ref` 取**前 50 条**(`mail_gold_v2_027` ~ `mail_gold_v2_212`)。
原则(邮件入库处理逻辑.md §10)：**按 review_comment 仅改 正文/标题，评审状态及其他字段不变**，写入 `source_snapshot.manual_cleanup.round2_*` 留痕。

## 一、数据盘点（full_email / mail_gold_seed 共 1277 条）

| 评审状态 | 条数 | 中文 | 本轮处理 |
|---|--:|---|---|
| needs_revision | 81 | 需修改 | **前 50 条**(本轮) |
| rejected | 28 | 不认可 | 不改正文(见 §四) |
| approved | 59 | 认可 | 不动 |
| (未评审) | 1109 | — | 不在本任务范围 |

## 二、人工点评汇总合并（前 50 条 needs_revision）

把 50 条人工点评归并为 6 类问题（一条点评可同时归多类）：

| 问题类别 | 命中数 | 典型点评 | 本轮修正方式 |
|---|--:|---|---|
| 时间/节日/年份 | 24 | "去掉时间信息，岁末将至…值此2025年收官、2026年启程之际"、"新年好！马年伊始，一马当先" | 删年份/节日/季节寒暄/开工大吉等时效句；**并把点评中人工逐字引用的时间短语作为精确删除目标** |
| 人名脱敏 | 21 | "Tiffany"、"吴磊（Leo）"、"何珺 Alice"、"徐杰徐杰" | 发件人名→`[发件人]`、客户称呼→`[客户称呼]`；英文名用 CJK 边界安全正则 `(?<![A-Za-z])…(?![A-Za-z])` 避免漏脱 |
| 客户公司/品牌脱敏 | 3+ | "去除客户公司信息，贵行16年来"、"贝亲"、"阿科玛"、"庄信万丰" | 真实客户/品牌→行业泛化(见 §三) |
| 格式/分段 | 1 | "格式分段没处理"、"案例排版没有分行" | 句末换行、项目符号统一、删孤立标点段 |
| 乱码/异常字符 | 1 | "有乱字符？"、"ü 乱码" | 删行首/句中孤立 `？`、花体符号 |
| 主题/其他泛指 | 3 | "主题"、"附件" | 主题含时间或不合适→改通用业务型主题 |

> 关键改进：**点评驱动的精确删除**——很多点评直接把要删的时间句"引用"了出来（如 v2_129："庆祝2025农历新年之际，在2025年，在2024年，过去的一年…值此新春佳节之际"），本轮把这些逐条作为字面删除目标，再叠加通用时间正则，做到"删人工点到的那句"。

## 三、脱敏再仔细点（本轮重点强化）

前序轮次仅维护了一份固定人名/公司表。本轮扫描前 50 条正文，**发现并补脱了大量此前漏掉的真实客户/品牌/银行/部门**：

- **英文品牌/客户**：Johnson & Johnson、Pfizer、Bayer、Medtronic、GE HealthCare、Boston Scientific、Fresenius Medical Care、Edwards Lifesciences、Coca-Cola、HSBC、Alstom、ExxonMobil、ABB、MBCC Group、Lutavit(露他维) → 各自行业泛化（某医疗器械客户/某制药客户/某银行客户/某快消客户…）。
- **中文客户/品牌**：广东电网、上海汽车工业、梅塞尔、空气化工、中鲨工业、法巴(法国巴黎银行)、欧莱雅、3M、广东德联、高仪、贝亲、阿科玛、雅马哈、庄信万丰 → 行业泛化。
- **银行/部门缩写**：CRM/CCIB/CPBB/FM/IOM/EHS→`相关部门`；PBOC/NFRA/CDF→`相关机构`（CJK 边界安全替换，修复了 `\b` 紧邻中文失效导致 `（CEO演讲`/`CPBB等` 漏替的坑）。
- **私域联系方式**：删除"微信/二维码/视频号/企业微信/抖音/小红书/扫码"等行与促销段。

## 四、逐行核验：状态为"非认可"是否满足 + 是否开发类邮件

### needs_revision(前 50 条)
- **是否满足**：50 条按点评清洗后，残留检测仅 **2 条**仍有存疑实体（见下），其余 48 条时间/人名/公司/格式问题均已消除（postcheck 复跑 `changed_count=0`，幂等已落库）。
- **是否开发类邮件**：50 条**全部为开发/营销外联邮件**（公司介绍/老客户激活/节日问候/业务介绍/合作回顾）。3 条曾命中"报价"关键词（v2_139/153/170）经核为营销话术（"专属报价/聊聊方案和报价/给出合适报价"），**非真实报价单，属开发类**。

### 需人工确认（不确定，记录编号）

| 编号 | 是否开发类 | 存疑点 | 说明 |
|---|---|---|---|
| `mail_gold_v2_142_mail_promo_recovered` | 是 | 正文项目清单含 `TripleS`、`阿巴扬锂矿`等专名 | TripleS 疑为客户产品线，能否泛化请人工确认 |
| `mail_gold_v2_148_mail_promo_recovered` | 是 | 开头 `APT~~APT~~` | APT 疑为客户简称/代号，含义不明请人工确认 |

### rejected(不认可) 28 条 —— 不改正文，仅记录开发类判定供人工核对
人工已判"不认可"，本轮不动正文。其中**明显非开发类/操作类**（应保持 rejected，不进黄金库）的编号：

| 编号 | 非开发类原因 |
|---|---|
| `mail_gold_v2_026` / `mail_gold_v2_030` | 人工点评"AI面试先不入" |
| `mail_gold_v2_029` | 客户回信线程（"收到，很可爱的笔记本，感谢"），含多段引用历史 |
| `mail_gold_v2_124` | Re: 报价/发票往来线程（含 Translation fee/Payment due/合同条款、[EXTERNAL-MAIL]） |
| `mail_gold_v2_387`/`409`/`416`/`421`/`434`/`474`/`475`/`477` | 同传排期/打样/报价/项目跟进等操作类 |

## 五、产物与验证

- dry-run：`logs/mail-full-email-nr-round2-dry-run-v3-20260615.json`
- apply（42 条实际变更，8 条前序已清洗无需改）：`logs/mail-full-email-nr-round2-apply-20260615.json`
- postcheck（幂等复跑 `changed_count=0`，残留 2）：`logs/mail-full-email-nr-round2-postcheck-20260615.json`
- 安全核查：新正文最短/旧长度比 0.86、均值 0.98，无 <120 字、无缩水 >40% 的条目（不存在过度删除）。
- 留痕：每条变更资产 `source_snapshot.manual_cleanup.round2_*` 写入清理时间/范围/原点评/规则；评审状态保留 `needs_revision`，不自动转 approved。

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m py_compile scratch/clean_needs_revision_round2.py
python scratch/clean_needs_revision_round2.py --report logs/mail-full-email-nr-round2-postcheck-20260615.json   # 复跑应 changed_count=0
```

## 六、下一步（人工配合）
1. 复核上表 2 条存疑实体（TripleS / APT）是否需进一步泛化。
2. 已满足的 needs_revision 由人工改判 `approved` 后，再放开 `allowed_for_generation` 进 RAG。
3. 其余 needs_revision 第 51–81 条（共 31 条）下一批按同脚本 `--limit` 续处理。

# 邮件黄金库 · 未评审 full_email round2 仅脱敏 · 全量收口报告（50 条一组）

时间：2026-06-15

## 一、范围与口径
未评审(`review_status` 空) full_email 共 **1109 条**：前 50 条已在 v1.7.275 处理；本轮按**50 条一组**扫描并处理**剩余 1059 条**（offset 50 起，共 22 组），至此**未评审 1109 条全部跑过 round2 脱敏**。

口径同前：**最小改动"仅脱敏"**——只跑实体替换词典（真实客户/品牌/银行/部门 + 称呼行），**不删时间、不重排段落**，纯实体替换（长度比≈1.0，无结构改动）。仅改 正文/标题，未评审状态不变；写 `source_snapshot.manual_cleanup.round2_*` 留痕。postcheck 幂等复跑 `changed_count=0`。

## 二、处理结果
| 指标 | 本轮(1059) | 含前50(1109) |
|---|--:|--:|
| 实际脱敏变更 | **613** | 645 |
| 记录交人工确认(残留) | **650** | 671 |

各组(22 组)变更数见 `logs/mail-full-email-unrev-sweep-apply-20260615.json` 的 `group_stats`。

## 三、本轮新增/补全的脱敏词典（高频复现真实客户）
- **中文**：罗氏/诺华/拜耳/惠氏/利乐/强生/卡瓦/三菱电梯/百事/汇丰/德意志银行/斯派莎克/亨斯迈/液化空气/船舶重工/科勒/伊顿/上海通用汽车/万华/梅赛尔/康宝来/龙灯瑞迪/上海国际招标/文广/时代华纳/亚美咨询/现代建设 等 → 行业泛化。
- **英文**：DSM/GSK → 行业泛化；ExxonMobil(含全大写)/Nexans/CeraVe/YSL 等。
- **复现发件人**：Shelly/Xue/Jennifer(x77)/Sunny(x37) → `[发件人]`（跨大量邮件复现，判为销售本人；称呼行 `Dear/Hi <名>` 已前置改 `[客户称呼]`，避免误判）。
- **误报排除**：`信息科技发展有限公司`(发件方自名)、软件/技术词(Photoshop/QuarkXpress/CorelDraw/XML/DevDB/Website/Manual 等)、`飞雕/Feidiao`(地址) 已加入残留白名单。

## 四、需人工确认（650 条，记录编号，未自动改）
正则到边际，剩余为**长尾真实客户**（每个仅出现数次）+ **模糊人名**，按"不确定记录编号由人工确认"处理。明细见 `logs/mail-full-email-unrev-sweep-apply-20260615.json` 的 `need_human`。建议人工批量补脱的高频残留：

- **真实公司（建议下批加入词典统一泛化）**：瑞典银行/美国银行/美洲银行/农业银行/巴黎百富勤银行/巴黎百富勤、利宝集团、庞巴迪(运输集团)、中国电工集团、古河电工、东方海外、百胜集团、杭州杭氧、辉瑞制药(Pfizer/Sanofi/赛诺菲)、力机车研究所、巴迪牵引/阿尔斯通(已部分覆盖)、国际酒店集团 等。
- **模糊人名（需判断是否[客户称呼]，避免误脱发件人）**：Sherry、Sheng、Jojo、Rain、Allen、Anny、Carol、Holly、Clare、Orianna、Amanda 等。
- **疑似产品/地址（人工核定保留或泛化）**：AIRIS/AIRISmat/APERTO/PRESTO/LuranaS/REX、Antwerpen/Opdorp/Truckwasstraat(比利时客户地址)、Cellasto/Armophe(产品)。
- 另含少量泛指噪声（"贸易有限公司""中国有限公司"等），可忽略。

## 五、产物
- 脚本：`scratch/sweep_unreviewed.py`（50 条一组扫描/应用，复用 `clean_needs_revision_round2.py` 脱敏词典）。
- JSON：`logs/mail-full-email-unrev-sweep-{apply,postcheck}-20260615.json`。

## 六、下一步
1. 人工确认/批量补脱上述长尾真实公司与人名（可把确认结果加入 `clean_needs_revision_round2.py` 词典后再跑一遍 sweep，幂等安全）。
2. full_email 全量(1277)评审/脱敏状态：needs_revision 81 已 round2 清洗、rejected 28 已检查、approved 59 未动、未评审 1109 已 round2 脱敏（known 实体）。

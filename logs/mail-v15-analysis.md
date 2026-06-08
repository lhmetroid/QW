# 邮件 V15 训练案例结果

时间：2026-06-08

## 结论

已按最新当前邮件案例与 v40 商用脚本模板生成 `mail_iteration_run` V15。

- run_id：`226aa34b-2d47-4115-9ee8-ab49bc6a302b`
- version_no：15
- run_label：`mail_v15_latest_cases_scripts`
- 状态：`success`
- 范围：当前 3 个邮件案例 × 4 个 Sequence Step = 12 封草稿
- 成功：12/12
- 失败：0/12
- LLM 成功：12/12
- fallback：0
- 平均分：94.50
- 最低分：90.00
- 最高分：96.00
- 平均耗时：8285 ms
- 使用模型：`deepseek-chat`
- 真实发信：未启用，仍为草稿与人工审核链路

说明：用户提到的“15 个邮件版本”本轮按数据库 `mail_iteration_run.version_no=15` 处理。当前迭代范围仍是产品指定的 3 个邮件案例，每个案例 4 封，共 12 封。V14 保留为历史结果，本轮未覆盖、删除或改写 V14。

## 本轮使用的当前邮件案例

- `KH15411-117`：老客户其他业务介绍
- `KH02659-011`：老客户激活
- `KH13770-006`：新客户开发介绍

## 12 封结果摘要

| 案例 | 场景 | Step | 状态 | 模型 | 分数 | Few-Shot | 主题 |
|---|---|---:|---|---|---:|---|---|
| 1 老客户其他业务介绍 | new_business_promotion | 1 | success | deepseek-chat | 96 | 40d95f74-f533-41ed-8e4a-6943db97d81f | 向您介绍我们近期新增的本地化与多语种服务能力 |
| 1 老客户其他业务介绍 | new_business_promotion | 2 | success | deepseek-chat | 96 | 40d95f74-f533-41ed-8e4a-6943db97d81f | 为您分享一个我们近期在相同行业完成的服务案例 |
| 1 老客户其他业务介绍 | new_business_promotion | 3 | success | deepseek-chat | 96 | d31d8d6b-8ec2-43c6-8790-3ca8260dd64c | 关于新服务包在贵司项目中的具体协作流程 |
| 1 老客户其他业务介绍 | new_business_promotion | 4 | success | deepseek-chat | 90 | f591bf6c-4dac-4258-ab29-3707a4515232 | 关于拓展多语言内容服务的建议 |
| 2 老客户激活 | re_activation | 1 | success | deepseek-chat | 90 | 0f727891-5712-4f1f-abd2-842942b934f1 | 好久不见，想跟您聊聊最近的项目动向 |
| 2 老客户激活 | re_activation | 2 | success | deepseek-chat | 96 | 40d95f74-f533-41ed-8e4a-6943db97d81f | 为您分享一个我们近期完成的同行业案例 |
| 2 老客户激活 | re_activation | 3 | success | deepseek-chat | 96 | d31d8d6b-8ec2-43c6-8790-3ca8260dd64c | 向您简要介绍我们目前采用的多流程质量把控机制 |
| 2 老客户激活 | re_activation | 4 | success | deepseek-chat | 96 | f591bf6c-4dac-4258-ab29-3707a4515232 | PENNY，为您准备的合作优选路径 |
| 3 新客户开发介绍 | new_contact_intro | 1 | success | deepseek-chat | 90 | 0f727891-5712-4f1f-abd2-842942b934f1 | 您好！我是您本次项目合作的新对接人 |
| 3 新客户开发介绍 | new_contact_intro | 2 | success | deepseek-chat | 96 | 40d95f74-f533-41ed-8e4a-6943db97d81f | 向您同步我们过往为贵司团队提供服务的一些背景 |
| 3 新客户开发介绍 | new_contact_intro | 3 | success | deepseek-chat | 96 | d31d8d6b-8ec2-43c6-8790-3ca8260dd64c | 为您说明未来项目协作中的文件提交与交付路径 |
| 3 新客户开发介绍 | new_contact_intro | 4 | success | deepseek-chat | 96 | f591bf6c-4dac-4258-ab29-3707a4515232 | 确认下一步协作切入点，助力贵司语言与内容服务需求 |

## 本轮修复

- 仅修改邮件链路：邮件当前案例/迭代后台遇到 `***EMAIL***` 或无效邮箱时归一为空邮箱，沿用既有“空邮箱只生成草稿模板、不做收件域名校验、不真实发信”逻辑。
- 邮件草稿 LLM 调用改为 `requests.Session()` 且 `trust_env=False`，避免本地代理环境劫持 DeepSeek 请求。
- 使用恢复脚本补齐同一个 V15 run 里的失败行，最终 V15 统计更新为 12/12 成功；未创建 V16，未改 V14。

## 查看方式

- 列表接口：`GET http://127.0.0.1:8071/api/v1/mail/iterations?limit=1`
- 详情接口：`GET http://127.0.0.1:8071/api/v1/mail/iterations/226aa34b-2d47-4115-9ee8-ab49bc6a302b`

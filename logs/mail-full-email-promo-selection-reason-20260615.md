# 邮件黄金库 full_email 宣传属性与选择理由分析

时间：2026-06-15

## 处理结论

- 范围：邮件质量诊断 -> 黄金范例库 -> 切片类型 `full_email`。
- 总数：1363 封。
- 已判断为宣传/推广型邮件：1286 封。
- 疑似不是宣传邮件、建议人工判断：77 封。
- 结果写入：`email_fragment_asset.source_snapshot.promo_analysis`。
- 前端展示：仅 `full_email` 显示“选择理由：XXX”；其他切片类型为空，不影响显示。
- 机器报告：`logs/mail-full-email-promo-analysis-apply-20260615.json`。

## 判定口径

优先识别服务能力介绍、案例/行业经验/合作背书、业务线推荐、低压力联系或转介绍动作、节日/问候式客户激活等推广信号。

若主题或正文更像交付、修改、报价、PO、发票、付款、合同、文件查收、job list、RFQ、项目沟通等事务邮件，则列入“疑似非宣传邮件”，由人工最终判断。

## 疑似非宣传邮件编号

| fragment_id | source_ref | 主题 |
| --- | --- | --- |
| d946eef0-ec09-4e2b-bf35-6da5ae54a754 | mail_gold_v2_1000_scn_2021 | INS视频修改，请在明天中午发我，谢谢！ |
| 716c783d-8ceb-4507-a6db-24274a0f57e5 | mail_gold_v2_1000_scn_2022 | Mandy！ |
| 9a3670b4-db60-4dac-8ffa-25e810756be7 | mail_gold_v2_1001_scn_2019 | POORD007800 |
| 66d54df4-099d-4bfb-9ac7-e743523a7a8a | mail_gold_v2_1003_scn_2020 | social media video 修改版 |
| d95c816f-05d3-45de-9bc0-6d67a28e0fb1 | mail_gold_v2_1005_scn_2018 | 感谢并祝福 |
| e0e906a4-b2c6-4624-93c5-5ba3114c34a3 | mail_gold_v2_1005_scn_2020 | Antwort: Re: Antwort: Re: Translation offer inquiry for Doerken - First draft of environmental assessment report |
| 1e35aafa-c984-4d72-a06b-dcc667ae0a05 | mail_gold_v2_1005_scn_2021 | B10 |
| a9b98b8b-eaa0-429b-8b2f-4845c9fc1310 | mail_gold_v2_1009_scn_2022 | Vera收到请回复哦 |
| 00d6ce77-62ff-4fd6-9ac4-f2a8a4434427 | mail_gold_v2_1011_scn_2020 | Combined Product list |
| 023385a8-991d-4399-bd42-53869b4a106f | mail_gold_v2_1011_scn_2022 | 陈部长，给您拜年啦！ |
| cdb1b4c8-fce8-42db-85ec-0dffae6e46cc | mail_gold_v2_1013_scn_2017 | US product changes_Communication_CI 3 and 4 h mixer |
| 2499a685-4a97-4a98-b436-27d152a74a48 | mail_gold_v2_1014_scn_2017 | 开票税号 |
| ac30afdd-e3ff-44fb-849c-c87164d3763e | mail_gold_v2_1016_scn_2022 | 高经理，！ |
| 36558528-9e14-4a07-875a-ddb7c506cfb8 | mail_gold_v2_1018_scn_2022 | 顾经理拜年啦 |
| 5a54523d-0747-443b-8233-05d0b0c9c827 | mail_gold_v2_1019_scn_2022 | 顾经理！ |
| 0b8f0ccc-3645-4aff-8ac3-2c03d3084511 | mail_gold_v2_1021_scn_2018 | Re[2]: Please quote |
| 805b4dc2-a7fe-4745-99eb-db9ec4f4895a | mail_gold_v2_1023_scn_2017 | 圣诞主题 |
| 46a339d9-35fd-4111-8d52-38e71c364325 | mail_gold_v2_1029_scn_2019 | Kalmar and The Port of Virginia_ continue long-standing cooperation with repeat order for hybrid shuttle carriers |
| ec709caf-f267-4ce7-9143-b19b0d53ccb4 | mail_gold_v2_1031_scn_2017 | 稿件回访 |
| d5a841f0-6023-484f-8fec-1dd3fbdeb677 | mail_gold_v2_1031_scn_2019 | Translation delivery： (SHL15 Bypass function LMRGBPS v3) |
| 5703dab7-099c-4631-a881-bc887a03cac6 | mail_gold_v2_1033_scn_2017 | 公司简介完整译稿 |
| 617bde9a-f547-4d70-932c-b547dea0e7bd | mail_gold_v2_1034_scn_2017 | 目录上传无响应 |
| e7ed1c21-20d3-4ca1-aade-b7e940776de0 | mail_gold_v2_1034_scn_2021 | Job List From Speed Tech (Nov-Dec) |
| dbea2640-4e21-4acf-8ef3-7eb62a2b8859 | mail_gold_v2_1035_scn_2020 | VPN登陆失败 |
| da53cf9c-d84c-4938-b192-3e09ffe0571c | mail_gold_v2_1036_scn_2021 | Q758译文修改 |
| 69c9b2fb-4050-4282-af24-22686d56dda1 | mail_gold_v2_1037_scn_2021 | Speed Tech job list from Oct to Dec |
| 32e900ad-666c-4c3a-b169-5fbeee852d12 | mail_gold_v2_1039_scn_2017 | 事必达台历样本 |
| 58cd5682-c54c-4fa9-bf77-83b81c976d9c | mail_gold_v2_1039_scn_2019 | [LCS develop by 31th JAN ]P-198043 BRAUN MPG - 007 DB CC CN-POA002 |
| 9cb30836-65fe-4299-8501-0045972f0e72 | mail_gold_v2_1040_scn_2019 | [LCS develop by Mar 14th]P-198043 BRAUN MPG - 007 DB CC CN POA001 |
| b253d223-48a5-4d26-983b-bc734eae3505 | mail_gold_v2_1041_scn_2022 | 廖小姐，事必达 |
| 0df6b0ef-41fc-4cb5-8add-14117041909e | mail_gold_v2_1042_scn_2017 | 邮件已收到 |
| 35aa7baa-1e93-430c-ac24-5503ae17b64d | mail_gold_v2_1042_scn_2020 | NDA-Jiasai |
| e19522eb-81d6-4607-86aa-35cf823ec2c6 | mail_gold_v2_1043_scn_2020 | Speed Tech Job list |
| 83db2488-657b-4810-895b-bf1e7ee63fcc | mail_gold_v2_1044_scn_2019 | 关于《工业机器人课程（FR系列基础）》PPT校对修改 |
| fbc09881-890b-4e8c-93b2-a1336c57981a | mail_gold_v2_1045_scn_2021 | 公司简介 |
| 1fe5f0e2-7cdf-460e-84c9-b5f8b937de81 | mail_gold_v2_1046_scn_2021 | 软件翻译 |
| 4d2aa16e-213d-4a74-92bb-7595d1cf514c | mail_gold_v2_1051_scn_2017 | 建筑行业的成功案例 |
| 29b20895-86c6-4902-ac2d-b88403114ab4 | mail_gold_v2_1051_scn_2018 | MF-C300 500 说明书--修改已完成,请从连接下载,谢谢 |
| fe7bbea9-2e0e-46ac-9686-987383413be6 | mail_gold_v2_1051_scn_2019 | 词汇单 |
| 204ff73d-08e8-4c50-8a8f-15949c40668b | mail_gold_v2_1051_scn_2021 | 英文公司简介 |
| 0e3c8a88-2f70-4ab6-af5a-a712dad5a94e | mail_gold_v2_1054_scn_2018 | 翻译费用PO申请 |
| 43ba9138-cd5b-4a29-a050-0849be30eba8 | mail_gold_v2_1056_scn_2020 | 事必达翻译印刷--[发件人] |
| 28b9ecfe-179a-4ec1-b5c1-16acc95d1c4b | mail_gold_v2_1058_scn_2020 | 事必达-[发件人] |
| 93c911e1-1703-4d92-85ce-6ca0bd6a013b | mail_gold_v2_1060_scn_2020 | DAGE Assure - Translation Software Interface--部分翻译完成稿 |
| 39ca3836-03e5-4031-89ee-71786c7a1067 | mail_gold_v2_1062_scn_2018 | speed tech job list from April to Sept |
| d0bb6e52-20c5-47ea-8ed3-108803dc3ac2 | mail_gold_v2_1066_scn_2018 | Translation Job list from Dec to now of Speed Tech.（the third party） |
| 3d3ae9b4-5241-4c9e-b0d9-ad947bbf530c | mail_gold_v2_1068_scn_2018 | 翻译完成稿 |
| 667a2d09-9547-482a-8581-75a6d801b3a7 | mail_gold_v2_1071_scn_2018 | 整理的文件 |
| 6db5532c-75b6-491e-89e1-1d1ad8659f53 | mail_gold_v2_1075_scn_2018 | 修改文件 |
| fc583836-a716-4c9d-8319-372dc5a478a4 | mail_gold_v2_1085_scn_2022 | 吴小姐十年的老朋友啦~ |
| c69d6447-0f9a-47da-bb07-bec1a5a68da2 | mail_gold_v2_1092_scn_2022 | 元宵节快乐 |
| 58845c9d-c4ba-4430-9f90-7c3b5b3b2563 | mail_gold_v2_1100_scn_2018 | Ariba 目录，请帮忙修改 |
| 1fa461fb-83da-44c8-b4b8-53ccb326b04c | mail_gold_v2_1100_scn_2022 | 来自事必达翻译率吕春雨--新春问候 |
| a3b9069c-19b9-434f-afeb-b559c73c1bd5 | mail_gold_v2_1113_scn_2022 | 修改稿件 |
| 1752f774-9e8a-4d26-984b-6ccfa4776495 | mail_gold_v2_1114_scn_2022 | PO沟通 |
| f008c990-b295-45c6-b52b-309dca496747 | mail_gold_v2_1184_scn_2022 | 修改版文件 |
| 65eb4b0a-30d5-4435-8512-8c6f31586090 | mail_gold_v2_1185_scn_2022 | 修改稿 |
| 0e78969f-fbce-4253-a69e-e27cffd77b3e | mail_gold_v2_122_mail_promo_cooperation_history | Re: Simplified Chinese Translation request - contract notes, |
| f3166a40-fe14-4c03-a497-e4672f22a6be | mail_gold_v2_405_scn_2025 | 翻译文件发送 |
| b9965153-a2cf-4e9d-8b94-c2716f1daf4b | mail_gold_v2_432_scn_2025 | Payment inquiry from SH Jiasai |
| 9a8343da-d53d-46ff-a69c-251e8e429c80 | mail_gold_v2_449_scn_2025 | 事必达[发件人] |
| 5b424da7-9b31-4a86-b544-6d384e95eb42 | mail_gold_v2_550_scn_2024 | From SPEED JOYCE |
| ef7d0dea-3930-4fba-a6a8-c6c1a5d4403a | mail_gold_v2_608_scn_2024 | Payment query |
| 567cb5f9-ec89-4059-8f17-4ea672e51049 | mail_gold_v2_827_scn_2023 | 视频修改 |
| a4be1197-2be4-474d-bb84-fabf57ddfc0e | mail_gold_v2_840_scn_2023 | Project 177481,177335,177492,177493 |
| 49a00d12-dbad-4b20-a4cc-7948ffc26e8c | mail_gold_v2_849_scn_2023 | 上海嘉赛SPEED放假日期调整 |
| bebe14a9-3245-4675-acb0-aa858e8898b9 | mail_gold_v2_858_scn_2023 | 翻译开票抬头 |
| 67ac4580-d97a-483b-b380-4104b4dbf09a | mail_gold_v2_863_scn_2023 | 3 ppt translate from CN to EN |
| 5635db23-f9b6-47c7-b2e9-07621ec190e4 | mail_gold_v2_867_scn_2023 | Wechat pic and Speed Tech Job List |
| 27340420-181d-48ad-8c3e-5d6d2168763b | mail_gold_v2_875_scn_2023 | 长期协议 |
| 559ac849-8ab6-405a-bc15-f52f7310ad94 | mail_gold_v2_934_scn_2023 | 天气炎热注意防暑 |
| 22fdb8a2-18a9-4ada-9a31-917b6979999c | mail_gold_v2_946_scn_2022 | RFQ - Advantage+Elite Slides translation |
| f5b99d69-f63a-4dbe-91ee-72722123d9e4 | mail_gold_v2_949_scn_2022 | 来自嘉赛[发件人]的问候 |
| 0d0c4679-ecb9-41da-8770-d932b55d6a58 | mail_gold_v2_971_scn_2022 | 公司简介修改版 |
| 0dcb2092-b3ae-4ac5-872e-2bad6fb90bb6 | mail_gold_v2_974_scn_2022 | 葡萄牙语翻译 |
| 5edbe490-8a35-4d4e-abd7-52d5c9c6da4d | mail_gold_v2_986_scn_2022 | ，虎年大吉 |
| db1cbbb0-754b-46a5-b9a9-e4981c598235 | mail_gold_v2_994_scn_2022 | Eva收到请回复 |

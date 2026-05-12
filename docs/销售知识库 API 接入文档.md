# 销售知识库 API 接入文档 (v0.1.0)

本 API 旨在为外部系统（如机器人、工作台、客服系统）提供基于销售邮件沉淀的知识检索与问答能力。

## 1. 基础信息 

- **Base URL**: `http://192.168.31.124:8100` (开发环境)
- **Content-Type**: `application/json`
- **认证**: 目前为 MVP 阶段，内网访问暂无需 Token，后续将支持 API-Key 校验。

------

## 2. 核心接口

### 2.1 智能知识检索

通过语义搜索知识库中的切片（Slices）。支持混合检索（向量+关键词）。

- **Endpoint**: `GET /kb-units/search`

- **请求参数**:

  | 参数名           | 类型   | 必选 | 说明                                                    |
  | :--------------- | :----- | :--- | :------------------------------------------------------ |
  | `query`          | string | 是   | 搜索词/客户问题 (不少于1个字符)                         |
  | `limit`          | int    | 否   | 返回数量，默认 20，最大 100                             |
  | `status`         | string | 否   | 过滤状态：`auto_generated`, `needs_review`, `confirmed` |
  | `published_only` | bool   | 否   | 是否仅搜索已发布到企微的内容，默认 `false`              |

- **响应示例**:

```
json





[

  {

    "kb_unit": {

      "id": 5415,

      "title": "DP276密码器盒子发货通知",

      "unit_type": "shipment",

      "summary": "2100份DP276盒子已通过物流发出...",

      "seller_response_text": "今天已用物流发送...",

      "confidence": 0.85

    },

    "rank_score": 0.92,

    "hit_reason": "语义匹配: 物流发送"

  }

]
```

------

### 2.2 自动化 Q&A 问答

输入客户问题，直接获取最匹配的“我方销售回复”文本，适用于聊天机器人快速响应。

- **Endpoint**: `POST /kb-units/qa-retrieve`
- **请求体**:

```
json





{

  "question": "那批密码器的盒子发货了吗？"

}
```

- **响应示例**:

```
json





{

  "answers": [

    {

      "kb_unit_id": 5415,

      "title": "DP276密码器盒子发货通知",

      "seller_response_text": "2100份-DP276密码器盒子已全部完成，共计153箱，今天已用物流发送。",

      "score": 0.915

    }

  ]

}
```

------

### 2.3 获取会话详情 (溯源)

通过 Thread ID 获取完整的邮件沟通链路，用于还原业务背景。

- **Endpoint**: `GET /threads/{thread_id}/mails`
- **请求参数**:
  - `thread_id`: 路径参数，会话 ID。
- **响应示例**:

```
json





[

  {

    "mail_uid": "20fb0c80...",

    "direction": "outbound",

    "subject": "Re: 采购需求",

    "body_main_text": "已用物流发送...",

    "sent_at": "2026-03-25T08:39:24Z"

  }

]
```

------

## 3. 常规枚举值说明

### 切片类型 (`unit_type`)

- `customer_profile`: 客户画像
- `product_intent`: 产品意向
- `quotation`: 报价信息
- `order`: 订单/PO
- `shipment`: 发货/物流
- `after_sales`: 售后问题

### 审核状态 (`status`)

- `auto_generated`: 系统自动生成（置信度高）
- `needs_review`: 待人工复核（置信度中）
- `confirmed`: 人工已确认

------

## 4. 调试建议

您可以直接在浏览器访问 `http://<server-ip>:8000/docs`。这是系统自带的 **Swagger UI**，可以在线测试所有接口并查看完整的字段定义。
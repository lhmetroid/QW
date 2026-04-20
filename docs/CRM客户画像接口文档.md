# CRM 客户画像接口文档

**版本**: 1.0  
**更新日期**: 2026-04-15  
**作者**: Claude Code Assistant

---

## 1. 接口概述

本接口用于从 CRM 系统中根据外部用户ID（external_userid）获取客户的完整画像信息，包括客户基本信息、近期商机、执行中的合同、最近跟进记录以及客户生命周期阶段。

该接口支持 AI 系统进行以下判断：
- 确定与客户的沟通语气和深度
- 判断客户优惠权限和等级
- 理解客户业务阶段和优先级

---

## 2. 接口地址

```
GET /api/crm/profile/{external_userid}
```

---

## 3. 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| external_userid | string | 是 | 外部用户ID，来自企业微信、钉钉等外部系统，对应 CRM 中的 WebChartID | `zhangsan_123` |

### 请求头

| 参数名 | 说明 |
|--------|------|
| Content-Type | application/json |

### 请求示例

**使用 cURL：**
```bash
curl -X GET "http://localhost:8000/api/crm/profile/zhangsan_123" \
  -H "Content-Type: application/json"
```

**使用 Python：**
```python
import requests

external_userid = "zhangsan_123"
response = requests.get(f"http://localhost:8000/api/crm/profile/{external_userid}")

if response.status_code == 200:
    profile = response.json()
    print(profile)
else:
    print(f"Error: {response.status_code} - {response.text}")
```

**使用 JavaScript：**
```javascript
const externalUserId = "zhangsan_123";
const response = await fetch(`/api/crm/profile/${externalUserId}`);

if (response.ok) {
    const profile = await response.json();
    console.log(profile);
} else {
    console.error(`Error: ${response.status}`);
}
```

---

## 4. 响应格式

### 4.1 成功响应 (200 OK)

```json
{
  "crm_contact_name": "张经理",
  "company_name": "某翻译技术公司",
  "recent_opportunities": "12345-同声传译|负责人:李总|用于4月份国际会议",
  "ongoing_contracts": "CT-2024-001-业务类型:翻译服务|AI字幕翻译系统|负责人:王经理|24年框架协议",
  "contact_recent_followup": "1天前以下具体时间点发生：\n09:30，电话，内容为：讨论项目进度，对方表示下周反馈方案\n14:15，邮件，内容为：发送会议记录和后续任务清单",
  "customer_lifecycle_stage": "熟联系人"
}
```

### 4.2 字段说明

| 字段名 | 类型 | 说明 | 可为null |
|--------|------|------|---------|
| crm_contact_name | string | 客户真名 | 否 |
| company_name | string | 客户所属企业主体名称 | 否 |
| recent_opportunities | string | 该客户名下近期处于跟进中的商机，包含商机编号、产品、负责人、业务描述 | 是 |
| ongoing_contracts | string | 该客户名下正在执行中的合同，包含合同编号、业务类型、产品、负责人、合同描述 | 是 |
| contact_recent_followup | string | 本联系人近期在 CRM 中的手动跟进概要，包含日期、时间、跟进方式和内容 | 是 |
| customer_lifecycle_stage | string | 客户业务生命周期状态，用于指示 AI 说话语气底色和权限判断，取值：`老联系人`、`熟联系人`、`新联系人` | 是 |

### 4.3 字段详解

#### crm_contact_name
- 客户的真实姓名
- 来自 `usrCustomerContact.ContactName`

#### company_name
- 客户所属企业名称
- 来自 `usrCustomer.CompanyName`

#### recent_opportunities
- **格式**: `商机编号-产品|负责人:姓名|业务描述`
- **示例**: `Q-2024-0521-同声传译|负责人:李总|4月国际会议同传需求`
- **说明**: 
  - 只返回最新的、状态为"Working"（跟进中）的报价
  - 来自 `usrQuotation` 表
  - 为 NULL 表示该客户没有跟进中的商机

#### ongoing_contracts
- **格式**: `合同编号-业务类型:类型|产品名称|负责人:姓名|合同描述`
- **示例**: `CT-2024-001-业务类型:翻译服务|AI字幕翻译系统|负责人:王经理|全年框架协议`
- **说明**:
  - 只返回最新的执行中合同（EndTime不为空）
  - 查询范围：最近1年内签订的合同
  - 来自 `usrContract` 表
  - 为 NULL 表示该客户没有执行中的合同

#### contact_recent_followup
- **格式**: 
  ```
  日期标签（当天或X天前）：
  HH:MM，跟进方式，内容为：跟进概要
  ──────────────────────
  HH:MM，跟进方式，内容为：跟进概要
  ```
- **示例**:
  ```
  1天前以下具体时间点发生：
  09:30，电话，内容为：讨论项目进度
  ──────────────────────
  14:15，邮件，内容为：发送会议记录
  ```
- **说明**:
  - 返回最近一个活跃天（有跟进记录）的所有跟进记录
  - 只统计状态为"成功"的跟进记录
  - 来自 `usrCustomerFollowUpRecord` 表
  - 为 NULL 表示该联系人没有跟进记录

#### customer_lifecycle_stage
- **可能值**: 
  - `老联系人` - 与我方有较长的合作历史，有成熟的合同和报价记录
  - `熟联系人` - 与我方有中等程度的合作，有一定的合同和报价基础
  - `新联系人` - 与我方接触较少，处于早期合作阶段
  - `null` - 无法判断或数据不足
- **说明**:
  - 基于 `crmContactYeWuSetting` 配置的业务规则计算
  - 比较指定时间范围内的合同数和报价单数
  - 逐级判断：老联系人 > 熟联系人 > 新联系人

---

## 5. 错误响应

### 5.1 未找到客户 (404 Not Found)

```json
{
  "detail": "未找到 external_userid: zhangsan_456 的客户信息"
}
```

**原因**:
- 提供的 external_userid 不存在
- 客户已被删除（Deleter 字段不为 NULL）
- WebChartID 与 external_userid 没有正确映射

### 5.2 数据库错误 (500 Internal Server Error)

```json
{
  "detail": "查询CRM数据库出错: [具体错误信息]"
}
```

**可能原因**:
- CRM 数据库连接失败
- SQL 查询语法错误
- 权限不足
- 数据库字段不存在或结构不符

### 5.3 参数错误 (422 Unprocessable Entity)

```json
{
  "detail": "参数验证失败"
}
```

---

## 6. 响应状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功，返回客户画像信息 |
| 404 | 未找到指定 external_userid 的客户 |
| 500 | 服务器错误，通常是数据库连接或查询问题 |
| 422 | 请求参数验证失败 |

---

## 7. 数据来源说明

### 表结构映射

| 响应字段 | 来源表 | 关键字段 |
|---------|--------|---------|
| crm_contact_name | usrCustomerContact | ContactName |
| company_name | usrCustomer | CompanyName |
| recent_opportunities | usrQuotation | QuotationId, Product, StaffName, BusinessDescription, Result |
| ongoing_contracts | usrContract | ContractId, BusinessType, ProductNameAll, InChargeName, ContractDescription, EndTime |
| contact_recent_followup | usrCustomerFollowUpRecord | FollowUpTime, FollowUpMethod, ai_summary, CustomerRemark, IfSuccess |
| customer_lifecycle_stage | crmContactYeWuSetting, usrContract, usrQuotation | 见计算规则 |

### 关键表关联

```
external_userid (WebChartID)
    ↓
usrCustomerContactWebChartList (b)
    ↓ external_userid
usrCustomerContactWebChartIDRelate (a)
    ↓ WebChartID
    ↓ ContactId
usrCustomerContact (c)
    ↓ CustomerId
usrCustomer (d)

同时关联：
usrQuotation (a) ← ContactId/CustomerId
usrContract (a) ← ContactId/CustomerId
usrCustomerFollowUpRecord (a) ← ContactId
```

---

## 8. 业务规则

### 8.1 近期商机 (recent_opportunities)

- **查询条件**:
  - `a.Result = 'Working'` （状态为跟进中）
  - `a.Deleter IS NULL` （未删除）
- **返回策略**: TOP 1（最新的）
- **时间限制**: 无

### 8.2 执行中合同 (ongoing_contracts)

- **查询条件**:
  - `a.EndTime IS NOT NULL` （有结束时间）
  - `a.Deleter IS NULL` （未删除）
  - `a.InputTime > DATEADD(YEAR, -1, CURRENT_TIMESTAMP)` （最近1年内签订）
- **返回策略**: TOP 1（最新的）

### 8.3 最近跟进记录 (contact_recent_followup)

- **查询条件**:
  - `ISNULL(IfSuccess, 0) = 1` （跟进成功）
  - `FollowUpTime <= CURRENT_TIMESTAMP` （时间不超过现在）
- **返回策略**:
  1. 找到最新的有跟进记录的日期
  2. 返回该日期的所有跟进记录
  3. 按时间排序显示

### 8.4 客户生命周期阶段 (customer_lifecycle_stage)

判断逻辑基于 `crmContactYeWuSetting` 表的配置：

1. **获取配置**:
   - 时间范围（TimeFrom, TimeTo）
   - 合同计数标准（OldContractNumber, NewContractNumber, QZContractNumber）
   - 报价计数标准（OldQuotationNumber, NewQuotationNumberFrom/To, QZQuotationNumberFrom/To）
   - 合并关系（AND/OR）

2. **计算数量**:
   - 在指定时间范围内的合同数
   - 在指定时间范围内的报价数

3. **逐级判断**:
   - 如果满足"老联系人"条件，返回 `老联系人`
   - 否则如果满足"熟联系人"条件，返回 `熟联系人`
   - 否则如果满足"新联系人"条件，返回 `新联系人`
   - 否则返回 `null`

---

## 9. 性能考虑

### 9.1 查询优化建议

为了提高接口响应速度，建议在以下字段上创建索引：

```sql
-- usrCustomerContactWebChartList
CREATE INDEX idx_external_userid ON usrCustomerContactWebChartList(external_userid);

-- usrCustomerContactWebChartIDRelate
CREATE INDEX idx_WebChartID ON usrCustomerContactWebChartIDRelate(WebChartID);
CREATE INDEX idx_ContactId ON usrCustomerContactWebChartIDRelate(ContactId);

-- usrCustomerContact
CREATE INDEX idx_ContactId ON usrCustomerContact(ContactId);
CREATE INDEX idx_CustomerId ON usrCustomerContact(CustomerId);

-- usrCustomer
CREATE INDEX idx_CustomerId ON usrCustomer(CustomerId);

-- usrQuotation
CREATE INDEX idx_CustomerId_Result ON usrQuotation(CustomerId, Result) INCLUDE (QuotationId, Product, StaffName, BusinessDescription);

-- usrContract
CREATE INDEX idx_CustomerId_EndTime ON usrContract(CustomerId, EndTime) INCLUDE (ContractId, BusinessType, ProductNameAll, InChargeName);

-- usrCustomerFollowUpRecord
CREATE INDEX idx_ContactId_IfSuccess ON usrCustomerFollowUpRecord(ContactId, IfSuccess) INCLUDE (FollowUpTime, FollowUpMethod, ai_summary);
```

### 9.2 缓存建议

由于客户画像信息变化频率较低，可以考虑实现缓存策略：
- 缓存有效期：30 分钟
- 缓存键：`crm_profile:{external_userid}`
- 触发失效：当有新的合同、报价或跟进记录时更新缓存

---

## 10. 常见问题 (FAQ)

### Q1: 为什么返回的某些字段为 null？

**A**: 这是正常现象，表示该客户在对应的业务环节中没有相关数据。例如：
- `recent_opportunities` 为 null：该客户没有跟进中的报价
- `ongoing_contracts` 为 null：该客户没有执行中的合同
- `contact_recent_followup` 为 null：该联系人没有跟进记录

### Q2: 如何处理连接超时错误？

**A**: 
1. 检查 MSSQL Server 是否在线
2. 验证 config.dat 中的数据库连接信息是否正确
3. 确保客户端已安装 ODBC Driver 18 for SQL Server
4. 检查网络连接和防火墙设置

### Q3: 为什么某些客户的生命周期阶段显示为 null？

**A**: 可能原因：
1. `crmContactYeWuSetting` 表未配置或配置不完整
2. 查询时间范围内的合同和报价数都为 0
3. 客户数据不符合任何定义的阈值条件

### Q4: 近期商机和执行中合同的时间范围是多久？

**A**:
- 近期商机：无时间限制，只要状态为"Working"就显示
- 执行中合同：最近1年内签订的，且 EndTime 不为空

### Q5: 跟进记录是否包括所有跟进方式？

**A**: 是的，包括所有方式（电话、邮件、QQ、微信等），但只包括状态为"成功"（IfSuccess = 1）的记录。

---

## 11. 集成示例

### 11.1 在 AI 对话系统中使用

```python
def get_customer_context(external_userid: str) -> dict:
    """获取客户上下文用于AI对话"""
    response = requests.get(f"http://crm-api:8000/api/crm/profile/{external_userid}")
    
    if response.status_code != 200:
        return {"error": "无法获取客户信息"}
    
    profile = response.json()
    
    # 构建系统提示词
    context_prompt = f"""
    客户信息：
    - 姓名：{profile['crm_contact_name']}
    - 公司：{profile['company_name']}
    - 阶段：{profile.get('customer_lifecycle_stage', '未知')}
    
    业务状态：
    - 商机：{profile.get('recent_opportunities', '暂无')}
    - 合同：{profile.get('ongoing_contracts', '暂无')}
    
    最近沟通：
    {profile.get('contact_recent_followup', '无记录')}
    """
    
    return {"prompt": context_prompt, "profile": profile}
```

### 11.2 在客户管理系统中使用

```javascript
async function loadCustomerProfile(externalUserId) {
    try {
        const response = await fetch(`/api/crm/profile/${externalUserId}`);
        
        if (response.ok) {
            const profile = await response.json();
            
            // 更新 UI
            document.getElementById('contact-name').textContent = profile.crm_contact_name;
            document.getElementById('company-name').textContent = profile.company_name;
            document.getElementById('stage').textContent = profile.customer_lifecycle_stage || '未知';
            document.getElementById('opportunities').textContent = profile.recent_opportunities || '暂无';
            document.getElementById('contracts').textContent = profile.ongoing_contracts || '暂无';
            document.getElementById('followup').textContent = profile.contact_recent_followup || '无记录';
        } else {
            console.error(`Failed to load profile: ${response.status}`);
        }
    } catch (error) {
        console.error('Error loading customer profile:', error);
    }
}
```

---

## 12. 配置说明

### 12.1 数据库配置文件

编辑 `config.dat` 文件，确保包含以下 CRM 数据库配置：

```ini
CRM_DBHost=10.0.0.209
CRM_DBPort=1433
CRM_DBName=DbCenterNew2
CRM_DBUserId=shjsdsshfdgjds
CRM_DBPassword=zjsphsymgswr
```

### 12.2 系统要求

- **Python**: 3.8+
- **SQLAlchemy**: 2.0+
- **FastAPI**: 0.111.0+
- **pyodbc**: 5.1.0+
- **ODBC Driver**: ODBC Driver 18 for SQL Server
- **SQL Server**: 2012+

---

## 13. 支持与反馈

如有问题或建议，请联系：
- 邮箱: speedasia@gmail.com
- 文档版本: 1.0
- 最后更新: 2026-04-15

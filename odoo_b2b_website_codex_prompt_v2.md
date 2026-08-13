# B2B 商品展示与客户服务平台 — Odoo 19 / Odoo.sh 开发总 Prompt（V2）

**版本：V2 — 顶层 B2B Management App 架构**

你是一名资深 Odoo 19 架构师、Python/Odoo 开发工程师、Web 前端工程师和应用安全工程师。

请帮助我设计并开发一个部署于 **Odoo.sh** 的企业级 B2B 商品展示与客户服务网站。

这个项目不是普通 B2C 商城，也不是重新开发一套 ERP。

项目的基本原则是：

**Odoo 负责后台业务、商品、客户、价格、附件、审核、订单及运营管理；客户看到的 Website 前端按照我们的 UI/UX 设计完全自定义。**

不要重新开发 Odoo 已经成熟提供的 Product、Partner、Pricelist、Attachment、Website、Portal、Sale 等基础能力。优先通过继承和扩展 Odoo 标准模型、Controller、QWeb Template 和 Website 机制实现。

## 顶层交付形态

最终交付给业务管理员时，应当表现为 **一个可安装的 Odoo 自定义应用：`B2B Management`**。

代码层面可以拆成多个模块，但管理员不需要逐个安装。请创建顶层模块：

```text
b2b_management
```

该模块在 `__manifest__.py` 中设置：

```python
"application": True
```

并通过 `depends` 依赖其他 B2B 子模块，使管理员在 Odoo Apps 中安装一次 **B2B Management** 后，Odoo 自动安装所需的全部 B2B 功能模块。

顶层 App 负责：

- App 名称与图标
- B2B 根菜单
- Dashboard 入口
- 聚合各子模块菜单
- 声明对子模块的依赖
- 作为整个项目对运营人员的统一入口

不要把 6~7 个技术子模块都暴露成独立业务 App。


---

# 一、技术基线

使用：

- Odoo 19
- Odoo Enterprise / Odoo.sh
- Odoo Website
- Odoo eCommerce 能力作为产品和价格基础
- Python
- Odoo ORM
- Odoo Web Controllers
- QWeb
- SCSS
- JavaScript
- Owl：仅用于确实需要复杂前端状态管理的交互
- PostgreSQL：由 Odoo/Odoo.sh 管理
- GitHub + Odoo.sh
- Odoo.sh Development / Staging / Production

第一阶段不要建立：

- 独立 Next.js 服务
- 独立 React SPA
- 独立 Node.js 后端
- 独立商品数据库
- 独立客户数据库
- 独立价格数据库

整个网站应优先作为 **Odoo Custom Addons + Website Theme** 部署在 Odoo.sh。

严禁修改 Odoo Core 源码。

所有功能必须通过自定义模块、继承、XPath、Controller、ORM、ACL 和 Record Rules 实现。

---

# 二、开发前必须阅读的 Odoo 官方文档

开发前先阅读并遵守以下 Odoo 19 官方文档。

## Odoo 开发框架

[Odoo 19 Developer Reference](https://www.odoo.com/documentation/19.0/developer/reference/)

[Building a Module](https://www.odoo.com/documentation/19.0/developer/tutorials/backend.html)

[Module Manifests](https://www.odoo.com/documentation/19.0/developer/reference/backend/module.html)

[ORM API](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html)

[Web Controllers](https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html)

[Security in Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html)

[Restrict access to data](https://www.odoo.com/documentation/19.0/developer/tutorials/restrict_data_access.html)

## 前端开发

[Odoo Web Framework](https://www.odoo.com/documentation/19.0/developer/reference/frontend.html)

[QWeb Templates](https://www.odoo.com/documentation/19.0/developer/reference/frontend/qweb.html)

[Assets](https://www.odoo.com/documentation/19.0/developer/reference/frontend/assets.html)

[Framework Overview](https://www.odoo.com/documentation/19.0/developer/reference/frontend/framework_overview.html)

[Build a Website Theme](https://www.odoo.com/documentation/19.0/developer/tutorials/website_theme.html)

[Website Themes](https://www.odoo.com/documentation/19.0/developer/howtos/website_themes.html)

[Website Layout](https://www.odoo.com/documentation/19.0/developer/howtos/website_themes/layout.html)

## Website / B2B / 商品

[Odoo Website](https://www.odoo.com/documentation/19.0/applications/websites/website.html)

[Odoo eCommerce](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce.html)

[eCommerce Configuration](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration.html)

[Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html)

[Prices / Pricelists](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/prices.html)

[Customer Accounts](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/customer_accounts.html)

[B2B and B2C](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/b2b_b2c.html)

[Product Page](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/ecommerce_design/product_page.html)

## 测试与性能

[Testing Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html)

[JavaScript Unit Testing](https://www.odoo.com/documentation/19.0/developer/reference/frontend/unit_testing.html)

[Performance](https://www.odoo.com/documentation/19.0/developer/reference/backend/performance.html)

[Actions / Scheduled Actions](https://www.odoo.com/documentation/19.0/developer/reference/backend/actions.html)

## Odoo.sh

[Odoo.sh](https://www.odoo.com/documentation/19.0/administration/odoo_sh.html)

[Odoo.sh Getting Started](https://www.odoo.com/documentation/19.0/administration/odoo_sh/getting_started.html)

[Odoo.sh Branches](https://www.odoo.com/documentation/19.0/administration/odoo_sh/getting_started/branches.html)

[Odoo.sh Builds](https://www.odoo.com/documentation/19.0/administration/odoo_sh/getting_started/builds.html)

## 未来外部 AI / LangGraph 集成

[Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)

新的外部系统集成优先考虑 Odoo 19 JSON-2 API 或专门设计的安全 Controller/API，不要为新系统建立在旧 XML-RPC / JSON-RPC 外部 RPC 接口之上。

---

# 三、项目定位

这是一个企业级 B2B 商品展示、样品申请、售后服务和订单查询平台。

主要用户可能包括：

- 经销商
- 工程商
- 系统集成商
- 顾问
- 设计院
- 售后服务商
- 其他未来定义的合作伙伴

这些用户不是 Odoo 内部 Employee。

它们原则上属于：

- Portal User
- Customer / Partner

运营人员和管理员属于 Odoo Internal User。

---

# 四、总体架构

目标架构：

```text
                        B2B Customer
                              │
                              ▼
                    Custom Odoo Website
                QWeb + SCSS + JS + Owl
                              │
                              ▼
                     Website Controller
                              │
                              ▼
                       Service Layer
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        Product Service  Customer Service  Order Service
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                         Odoo ORM
                              │
       ┌──────────────────────┼───────────────────────┐
       ▼                      ▼                       ▼
 res.partner           product.template          sale.order
 Pricelist             Attachments              Custom Models
       │                      │                       │
       └──────────────────────┼───────────────────────┘
                              │
                              ▼
                        ERP Connector
                              │
                              ▼
                         Existing ERP
```

核心原则：

Controller 不承担复杂业务逻辑。

Template 不承担权限判断。

JavaScript 不决定最终权限和最终价格。

复杂业务逻辑统一放在 Model / Service Layer。

---

# 五、建议的 Odoo 自定义模块

不要把整个项目塞进一个巨大模块。

建议拆分为：

```text
custom_addons/

b2b_management/      # 顶层可安装 App
b2b_core/
b2b_website/
b2b_sample/
b2b_service/
b2b_resource/
b2b_erp_connector/
```

其中 `b2b_management` 是面向管理员的顶层 App。

其 `__manifest__.py` 应类似：

```python
{
    "name": "B2B Management",
    "version": "19.0.1.0.0",
    "category": "Sales/B2B",
    "depends": [
        "b2b_core",
        "b2b_website",
        "b2b_resource",
        "b2b_sample",
        "b2b_service",
        "b2b_erp_connector",
    ],
    "data": [
        "views/b2b_management_menus.xml",
        "views/b2b_dashboard_views.xml",
    ],
    "application": True,
    "installable": True,
}
```

管理员预期安装流程：

```text
Apps
↓
Update Apps List
↓
搜索 B2B Management
↓
Install
↓
自动安装所有依赖模块
```

职责如下。

## b2b_management

负责：

- 顶层 App
- App Icon
- B2B Root Menu
- Dashboard
- 聚合各子模块菜单
- 声明所有 B2B 子模块依赖
- 提供统一业务入口

它本身不要重复实现 Product、Sample、Service 等业务逻辑。

业务逻辑继续放在对应子模块中。

## b2b_core

负责：

- B2B 客户标签
- 客户等级
- 商品可见性规则
- Pricelist 映射
- 通用业务 Service
- 公共安全规则

## b2b_website

负责：

- Website Theme
- Header
- Footer
- Homepage
- Product Catalog
- Product Detail
- Search
- Filter
- Customer Portal 页面
- 前端公共组件
- 网站 Controller

## b2b_sample

负责：

- 样品申请
- 审核
- 状态
- 后台菜单
- ERP 推送触发

## b2b_service

负责：

- 维修申请
- 换货申请
- 售后审核
- 附件
- 状态流程

## b2b_resource

负责：

- 产品资料
- 图片
- 视频
- Datasheet
- Manual
- Certificate
- Download 权限

## b2b_erp_connector

负责：

- ERP API Client
- Authentication
- Request / Response Mapping
- Queue
- Retry
- Idempotency
- Integration Log
- Order Status Query

模块之间保持低耦合。

建议依赖关系：

```text
                    b2b_management
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   b2b_website        b2b_sample         b2b_service
        │                  │                  │
        └──────────┬───────┴──────────┬───────┘
                   ▼                  ▼
             b2b_resource      b2b_erp_connector
                   │                  │
                   └──────────┬───────┘
                              ▼
                          b2b_core
                              │
                              ▼
                    Odoo Standard Modules
             contacts / product / website / sale /
                    portal / mail / pricelist
```

`b2b_management` 只做聚合与入口，不形成反向依赖。

---

# 六、客户标签与客户分类

创建模型：

```text
b2b.customer.segment
```

示例数据：

```text
Dealer
Contractor
System Integrator
Consultant
Design Institute
Service Provider
VIP Dealer
OEM
```

运营人员必须可以通过 Odoo 后台自己创建、修改、启停客户标签。

不要把标签写死在 Python Selection 中。

扩展：

```text
res.partner
```

增加：

```text
b2b_segment_ids
b2b_approved
```

客户可以拥有多个标签。

---

# 七、B2B 价格体系

首先复用 Odoo：

```text
product.pricelist
```

不要重新开发一个独立价格引擎。

不同：

- 客户
- 客户公司
- 客户类型

可以映射到不同 Pricelist。

支持：

```text
Dealer Price
Integrator Price
Consultant Price
VIP Price
Default B2B Price
```

最终页面价格必须由 Odoo 服务端计算。

前端不得接收所有价格后自行判断显示哪一个。

禁止：

```javascript
if (userType === "dealer") {
    showDealerPrice();
}
```

正确流程：

```text
当前 User
↓
res.partner / commercial_partner
↓
客户 Segment
↓
客户 Pricelist
↓
Odoo 后端计算
↓
只返回最终允许显示的价格
```

必须定义确定性的价格优先级。

建议：

```text
客户专属 Pricelist
>
客户公司 Pricelist
>
Segment 映射 Pricelist
>
网站 Default Pricelist
```

如果多个 Segment 产生冲突，不允许随机选择。

必须通过 priority 明确决定。

---

# 八、商品可见性

商品继续使用：

```text
product.template
product.product
```

不要重新创建商品主表。

运营人员继续在 Odoo Product 后台：

- 创建商品
- 修改商品
- 上架
- 下架
- 修改名称
- 修改 SKU
- 修改描述
- 修改价格
- 修改图片
- 修改分类

在 `product.template` 增加 B2B 可见性配置。

建议字段：

```text
b2b_visibility_mode

all
approved_users
segments
hidden
```

以及：

```text
b2b_visible_segment_ids
```

如果 Odoo 标准字段已经提供相同能力，优先复用，不重复创建。

商品是否允许客户查看必须在后端 Domain / Service 层过滤。

**没有权限的商品不能进入返回给浏览器的数据。**

不能：

```text
返回全部商品
↓
JavaScript 隐藏
```

---

# 九、商品目录页面

创建自定义 Product Catalog。

推荐 Route：

```text
/products
```

支持：

- 搜索
- Product Category
- Brand
- Tag
- 应用场景
- 可扩展 Filters
- Pagination
- Responsive Layout

产品 Card 包括：

- 图片
- Product Name
- SKU / Model
- 简短描述
- 客户最终价格
- 查看详情

如果客户没有价格查看权限：

不要泄露实际价格。

可以显示：

```text
Contact Us
Request Quote
Login to View Price
```

具体行为必须可以配置。

---

# 十、产品详情页面

推荐：

```text
/products/<product-slug>
```

页面数据：

- Product Name
- Model / SKU
- Brand
- Category
- Main Image
- Gallery
- Video
- Description
- Technical Information
- Customer Price
- Sample Request
- Resources

结构示例：

```text
Product Name

[Gallery]       Model
                SKU
                Your Price

                [Request Sample]


Overview

Specifications

Resources

Related Products
```

前端视觉必须允许完全按照我们的设计稿实现，不使用默认 Odoo eCommerce 外观作为最终设计。

但是业务数据继续来自 Odoo。

---

# 十一、样品申请

产品详情页面必须存在：

```text
Request Sample
```

按钮。

点击后进入样品申请流程。

建议模型：

```text
b2b.sample.request
b2b.sample.request.line
```

虽然第一版从单个商品发起，但数据模型使用 Line 设计，为未来一次申请多个样品留出扩展能力。

字段至少包括：

```text
name
partner_id
commercial_partner_id
contact_name
email
phone
shipping_address
request_line_ids
reason
notes
state
reviewer_id
review_date
erp_sync_state
erp_order_no
erp_last_error
```

Line：

```text
product_id
quantity
uom_id
notes
```

编号使用 Sequence，例如：

```text
SAM-2026-000001
```

状态：

```text
draft
submitted
under_review
approved
rejected
erp_pending
erp_syncing
erp_synced
erp_failed
cancelled
```

---

# 十二、样品审核流程

客户：

```text
提交样品申请
```

后：

```text
Submitted
↓
运营人员审核
↓
Approved / Rejected
```

运营人员必须在 Odoo Backend 有专门菜单：

```text
B2B
└── Sample Requests
```

后台支持：

- List View
- Form View
- Search
- Filter
- Group By
- Status
- Reviewer
- Date
- Customer

审核通过后：

**不要在按钮请求中直接同步等待 ERP。**

正确方式：

```text
Approve
↓
创建 ERP Integration Job
↓
状态 ERP Pending
↓
Scheduled Action / Worker Logic
↓
调用 ERP
↓
成功
ERP Synced

失败
ERP Failed
↓
自动 Retry / 人工 Retry
```

这样 ERP 临时不可用不会导致 Odoo 审核页面卡死。

---

# 十三、售后服务

建立：

```text
b2b.service.request
```

用户可以选择：

```text
Repair
Replacement
```

必须支持：

- Product
- Model
- Serial Number
- Order Number
- Contact Name
- Company
- Email
- Phone
- Request Type
- Problem Description
- Attachments
- Submitted Time

编号例如：

```text
SRV-2026-000001
```

状态：

```text
submitted
under_review
need_information
approved
rejected
processing
completed
cancelled
```

运营后台：

```text
B2B
└── Service Requests
```

运营人员可以：

- 查看
- 审核
- 修改状态
- 写内部备注
- 联系客户
- 上传附件

建议使用 Odoo：

```text
mail.thread
mail.activity.mixin
```

记录：

- 状态变化
- 审核历史
- 内部操作

---

# 十四、售后页面

Route：

```text
/service
```

登录用户：

自动读取：

```text
Name
Company
Email
```

允许用户修改联系邮箱。

产品选择优先展示：

- 客户历史相关商品
- 或允许该客户访问的商品

如果允许 Guest 提交售后申请：

必须额外加入：

- CAPTCHA
- Email 验证
- Rate Limit
- 输入校验

避免垃圾请求和自动化攻击。

---

# 十五、产品资源下载系统

资源不能简单做成一个公开 URL 字段。

建立：

```text
b2b.product.resource
```

引用 Odoo：

```text
ir.attachment
```

字段建议：

```text
name
product_id
resource_type
attachment_id
external_url
version
language
description
is_published
sequence
visible_segment_ids
```

resource_type：

```text
datasheet
manual
certificate
image
video
software
drawing
other
```

支持：

- PDF
- Image
- Video
- ZIP
- CAD
- Certificate
- URL

文件统一由 Odoo 后台管理。

运营人员应该：

```text
Products
↓
Product A
↓
Resources
↓
Upload
```

前端自动呈现。

不需要程序员每上传一个 PDF 就修改网站代码。

---

# 十六、Resources 前端

产品详情增加：

```text
Resources
```

示例：

```text
Documents

Datasheet
Version 2.1
PDF · 2.4 MB
[Download]

Installation Manual
Version 1.4
PDF · 6.8 MB
[Download]

Certificate
PDF
[Download]
```

Video：

```text
Product Introduction
[Watch Video]
```

Resource 权限必须服务端判断。

例如：

```text
Public Datasheet
→ 所有人

Dealer Manual
→ Dealer

Service Manual
→ Service Provider

Internal Document
→ Internal User
```

用户没有权限时：

**不能只隐藏 Download Button。**

下载 Controller 本身必须再次验证权限。

---

# 十七、文件安全

所有下载必须经过服务端权限检查。

不能认为：

```text
知道 attachment URL
=
允许访问文件
```

必须验证：

```text
当前 User
↓
Partner
↓
Segment
↓
Product Visibility
↓
Resource Visibility
↓
允许 Download
```

Private Attachment 不应因为猜到 ID 就能下载。

上传文件需要：

- MIME Type 校验
- Extension 校验
- Size Limit
- Filename 安全处理

不要信任用户提供的文件名或 MIME Header。

---

# 十八、订单查询

Website 建立：

```text
/order-tracking
```

但是：

**生产环境禁止只凭 Order Number 返回完整订单数据。**

默认设计：

用户必须登录。

查询：

```text
Order Number
```

后：

```text
Current Partner
↓
Commercial Partner
↓
ERP Query Service
↓
验证订单所属 Customer
↓
返回状态
```

不能让 Customer A 查询 Customer B 的订单。

---

# 十九、如果未来业务要求未登录查询订单

必须使用至少：

```text
Order Number
+
Email
```

或者：

```text
Order Number
+
Email OTP
```

同时：

- CAPTCHA
- Rate Limit
- Failed Attempt Limit
- 不返回敏感信息

不要仅靠订单编号。

---

# 二十、ERP Order Status

ERP 是订单真实进度的数据源。

Odoo 调用：

```text
ERP Adapter
```

接口抽象：

```python
get_order_status(order_number, customer_context)
```

输出统一 DTO，例如：

```json
{
  "order_number": "...",
  "customer_reference": "...",
  "status": "...",
  "current_stage": "...",
  "updated_at": "...",
  "timeline": [],
  "tracking_number": null
}
```

前端不得直接访问 ERP。

只能：

```text
Browser
↓
Odoo
↓
ERP
```

ERP URL、Token、Secret 绝对不能发送到浏览器。

---

# 二十一、ERP Connector 架构

建立统一 Adapter。

建议接口：

```python
class ERPAdapter:

    def push_sample_request(self, sample_request):
        ...

    def push_service_request(self, service_request):
        ...

    def get_order_status(self, order_number, customer_context):
        ...
```

不要让：

```text
Sample Module
Service Module
Order Controller
```

各自复制 ERP HTTP 代码。

统一通过：

```text
b2b_erp_connector
```

调用。

---

# 二十二、ERP 接口暂时未知时的处理

如果真实 ERP API 文档尚未提供：

**禁止虚构 ERP API。**

先创建：

```text
ERPAdapter
MockERPAdapter
```

以及接口配置。

把以下内容做成可配置：

```text
Base URL
Authentication Method
API Version
Timeout
Retry Count
Connection Enabled
```

等实际 ERP 文档提供后再实现：

```text
RealERPAdapter
```

不得因为 ERP 接口暂缺而阻止其他模块开发。

---

# 二十三、ERP 同步可靠性

任何需要写 ERP 的操作必须考虑：

- Timeout
- Retry
- Exponential Backoff
- Idempotency
- Duplicate Prevention
- Error Logging
- Manual Retry
- Audit
- Response Validation

样品申请 Idempotency Key 示例：

```text
sample_request:<odoo_request_uuid>
```

ERP 即使收到同一个请求两次，也应该能够识别。

Odoo 侧至少保证不会把相同成功任务无限重复提交。

---

# 二十四、Integration Job

建立：

```text
b2b.integration.job
```

字段：

```text
job_type
reference_model
reference_id
idempotency_key
state
attempt_count
next_retry_at
request_summary
response_summary
last_error
created_at
completed_at
```

状态：

```text
pending
processing
success
failed
dead
```

使用：

```text
ir.cron
```

批量处理 Pending Job。

避免每条记录逐条 N+1 查询。

遵守 Odoo Performance 官方指南。

---

# 二十五、ERP 日志安全

日志中不得保存：

- Password
- API Secret
- Bearer Token
- Session Token
- Authorization Header

ERP Error 返回给前端时：

不能直接显示：

```text
Traceback
Internal URL
Database ID
Secret
ERP raw response
```

用户只看到安全的业务错误。

详细错误只给管理员。

---

# 二十六、Odoo 后台 App 与菜单

Odoo 首页 / Apps 中应该出现统一业务应用：

```text
B2B Management
```

进入后看到：

```text
B2B Management
│
├── Dashboard
│
├── Sample Requests
│
├── Service Requests
│
├── Resources
│
├── ERP Jobs
│
├── ERP Logs
│
└── Configuration
    ├── Customer Segments
    ├── Price Mapping
    └── ERP Settings
```

不要让运营人员看到多个彼此割裂的 `B2B Sample`、`B2B Resource`、`B2B ERP` App。

它们是内部技术模块，不是最终业务入口。

同时扩展：

```text
Contacts
Products
```

而不是复制新的客户和商品管理后台。

---

# 二十七、Portal

客户登录后建立统一 My Account。

例如：

```text
My Account

My Sample Requests
My Service Requests
My Orders
Downloads
Profile
```

客户只能查看：

```text
自己
或
自己所属 commercial_partner
```

的数据。

必须通过 ACL + Record Rules 实现。

不能只通过 Controller Domain 隐藏。

---

# 二十八、安全总体要求

本系统涉及：

- 客户价格
- 客户身份
- ERP 订单
- 售后数据
- 文件
- 联系方式

因此按照安全优先开发。

必须遵守以下要求。

## ORM

业务数据访问优先使用：

```text
Odoo ORM
```

不要直接访问 PostgreSQL。

避免 raw SQL。

如果确实必须 raw SQL：

必须解释原因，并使用安全参数绑定。

---

# 二十九、ACL 与 Record Rules

每个 Custom Model 必须定义：

```text
ir.model.access.csv
```

以及必要：

```text
ir.rule
```

至少区分：

```text
Public
Portal User
Internal B2B Operator
B2B Manager
Administrator
```

建议创建：

```text
group_b2b_operator
group_b2b_manager
```

权限遵循最小权限原则。

---

# 三十、禁止滥用 sudo()

不能为了方便大量使用：

```python
sudo()
```

每一次 `sudo()` 都必须有明确理由。

如果确实需要：

- Scope 尽可能小
- 输入先验证
- 结果再次过滤
- 添加代码注释解释原因

特别注意 Portal / Public Controller。

---

# 三十一、Controller 安全

按照 Odoo 19 Controller 官方文档。

明确：

```text
auth='user'
auth='public'
auth='bearer'
```

使用场景。

涉及修改数据的普通 HTTP Form 保持 CSRF 防护。

不要为了“方便”全局：

```text
csrf=False
```

Public Form 应考虑：

```text
captcha
```

订单查询、售后提交等容易被攻击的入口应增加：

- CAPTCHA
- Rate Limit
- Validation

---

# 三十二、输入安全

所有用户输入进行：

- Length Validation
- Type Validation
- Required Validation
- Enumeration Validation

不要相信：

```text
product_id
partner_id
attachment_id
order_id
```

是合法的。

每次必须验证：

```text
记录存在
+
当前用户有权限访问
```

---

# 三十三、XSS

QWeb 默认转义机制优先。

不要对用户输入轻易使用未经安全处理的：

```text
t-raw
Markup
innerHTML
```

富文本字段需要明确来源和权限。

---

# 三十四、前端技术原则

前端不是“使用默认 Odoo 页面换 Logo”。

需要按照独立设计系统开发。

使用：

```text
QWeb
SCSS
JS
Owl when needed
Bootstrap utilities when appropriate
```

创建：

```text
Design Tokens

Typography
Spacing
Buttons
Forms
Cards
Modal
Toast
Table
Product Card
Resource Card
Status Badge
```

避免每个页面自行复制 CSS。

---

# 三十五、Assets

所有公共 Website JS / SCSS 正确加入：

```text
web.assets_frontend
```

不要随意塞入：

```text
web.assets_backend
```

公共网站资源和 Backend 资源分开。

---

# 三十六、Responsive

网站必须至少适配：

```text
Desktop
Tablet
Mobile
```

重点：

- Header
- Product Grid
- Product Detail
- Form
- Resource List
- Order Status Timeline

---

# 三十七、性能

Product Catalog 必须：

- Pagination
- 合理 Domain
- 避免 N+1
- 避免循环 search()
- 使用 ORM Prefetch
- Batch Operations
- 合理 Index

不要一次返回全部产品。

Product List 不加载不需要的大尺寸附件。

---

# 三十八、媒体策略

图片：

使用适合 Website 的尺寸与缩略图。

Video 支持两种方式：

```text
Odoo Attachment
External Video URL
```

对于大型公开视频，允许使用配置的企业 CDN / 视频平台，避免无必要把巨大视频全部放入 Odoo 数据备份。

对于私有视频必须继续做权限控制。

---

# 三十九、SEO

公开商品页面支持：

- SEO Title
- Meta Description
- Canonical URL
- Semantic HTML
- Image Alt
- Clean URL

私有客户页面：

```text
noindex
```

Portal：

```text
noindex
```

订单查询结果：

```text
noindex
```

---

# 四十、未来 LangGraph / AI Agent 扩展

第一阶段不需要真正实现 AI。

但是架构必须为未来 AI 留接口。

禁止未来 AI：

```text
直接连接 PostgreSQL
```

禁止：

```text
Agent 获得 Odoo Admin 权限
```

未来架构：

```text
LangGraph / AI Agent
        │
        ▼
Secure Service/API Layer
        │
        ▼
Odoo Business Service
        │
        ▼
Odoo ORM
```

未来 AI 可能实现：

- 查询产品
- 查询说明书
- 产品选型
- 查询订单
- 帮客户填写样品申请
- 创建售后申请
- 推荐产品
- 生成报价
- 查询技术资料

因此当前项目要把业务逻辑放入可复用 Service。

例如：

```python
ProductService.get_visible_products(...)
ProductService.get_customer_price(...)
ResourceService.get_allowed_resources(...)
SampleService.create_request(...)
OrderService.get_status(...)
```

Controller 只是调用这些 Service。

这样未来：

```text
Website Controller
```

和：

```text
AI Controller
```

可以复用同一套业务规则。

---

# 四十一、未来 AI API

如果未来 LangGraph 部署在外部系统：

优先研究：

```text
Odoo 19 JSON-2 API
```

或者开发：

```text
/b2b/api/v1/*
```

安全 API。

使用：

```text
Bearer Token
Dedicated Service Account
Least Privilege
Audit Log
Rate Limit
```

不要使用 Administrator Token。

AI 调用也必须继续经过：

- Customer Permission
- Product Visibility
- Pricelist
- Resource Visibility
- Audit

AI 不能绕过普通用户权限。

---

# 四十二、建议事件扩展点

为以下业务动作保留可扩展 Hook / Service Method：

```text
customer.approved

sample.submitted
sample.approved
sample.erp_synced

service.submitted
service.approved

resource.downloaded

order.status_queried
```

第一版不一定需要 Kafka / Message Queue。

不要过度设计。

但业务逻辑不要写死到 Controller 内部，使未来可以加入：

```text
LangGraph
Workflow
Agent
Webhook
Analytics
Notification
```

---

# 四十三、审计

重要操作必须能够追踪：

- 谁审批了 Sample
- 谁拒绝了 Sample
- ERP 何时同步
- ERP 是否失败
- 谁审核售后
- 状态何时修改

优先使用 Odoo Chatter / Tracking。

ERP Integration 另外保留技术日志。

---

# 四十四、测试要求

必须写自动化测试。

至少包括 Python：

```text
TransactionCase
HttpCase
```

必要前端使用：

```text
HOOT
Tours
```

---

# 四十五、必须覆盖的安全测试

必须测试：

```text
Dealer A
不能看到
Dealer B 的私有价格
```

必须测试：

```text
Customer A
不能查看
Customer B 的 Sample Request
```

必须测试：

```text
Customer A
不能查看
Customer B 的 Service Request
```

必须测试：

```text
Customer A
不能下载
无权限 Resource
```

必须测试：

```text
Customer A
不能通过修改 URL 中 ID
访问 Customer B 数据
```

必须测试：

```text
Public User
不能调用
Internal Approve Method
```

必须测试：

```text
无权限用户
无法查询其他客户订单
```

---

# 四十六、ERP 测试

模拟：

```text
ERP Success
ERP 400
ERP 401
ERP 403
ERP 404
ERP 429
ERP 500
ERP Timeout
Invalid JSON
Duplicate Request
```

验证：

- Retry
- Idempotency
- State Transition
- Error Log
- Manual Retry

---

# 四十七、业务测试

完整测试：

## Product

```text
运营创建 Product
↓
Publish
↓
前端出现
```

## Price

```text
Dealer 登录
↓
Dealer Price

Integrator 登录
↓
Integrator Price
```

## Sample

```text
Product
↓
Request Sample
↓
Submit
↓
Odoo Backend
↓
Approve
↓
ERP Job
↓
ERP Synced
```

## Service

```text
Customer
↓
Repair
↓
Submit
↓
Backend Review
```

## Resource

```text
Upload Manual
↓
Publish
↓
Product Page
↓
Download
```

## Order

```text
Customer Login
↓
Order Number
↓
Odoo
↓
ERP
↓
Verify Customer
↓
Status
```

---

# 四十八、开发与部署流程

Git Branch：

```text
feature/*
develop
staging
production
```

结合 Odoo.sh：

```text
Development
↓
Staging
↓
Production
```

功能首先在 Development 测试。

再进入 Staging。

禁止直接在 Production 开发。

## Odoo.sh 首次安装流程

第一次部署新的 B2B 应用时：

```text
GitHub Push
↓
Odoo.sh Development Build
↓
进入 Development 数据库
↓
Apps
↓
Update Apps List
↓
搜索 B2B Management
↓
Install
```

安装 `b2b_management` 时，其 `depends` 自动安装所有 B2B 子模块。

不要要求管理员逐个安装：

```text
b2b_core
b2b_website
b2b_resource
b2b_sample
b2b_service
b2b_erp_connector
```

## 后续代码升级流程

代码修改以后：

```text
Codex / Developer
↓
Git Commit
↓
Git Push
↓
Odoo.sh Build
↓
Upgrade 对应 Module
↓
Run Tests
↓
Staging
↓
Production
```

如果修改：

- Python Models
- XML Views
- Security
- Data
- Manifest
- Assets

必须判断是否需要升级模块。

开发文档中要明确区分：

```text
Restart / Rebuild
```

与：

```text
Module Upgrade
```

不要把“代码已部署”误认为“数据库结构已经自动升级”。

---

# 四十九、Odoo.sh 数据原则

Production：

真实客户数据。

Staging：

用于发布前测试。

Development：

开发测试。

不能把 Production：

- Customer Email
- ERP Token
- Secret

随意输出到 Debug Log。

---

# 五十、项目目录建议

最终大概应该类似：

```text
custom_addons/
│
├── b2b_management/
│   ├── __init__.py
│   ├── __manifest__.py
│   ├── static/
│   │   └── description/
│   │       └── icon.png
│   └── views/
│       ├── b2b_management_menus.xml
│       └── b2b_dashboard_views.xml
│
├── b2b_core/
│   ├── models/
│   ├── security/
│   ├── services/
│   ├── views/
│   ├── data/
│   └── tests/
│
├── b2b_website/
│   ├── controllers/
│   ├── views/
│   ├── static/
│   │   └── src/
│   │       ├── js/
│   │       ├── scss/
│   │       ├── xml/
│   │       └── img/
│   └── tests/
│
├── b2b_sample/
│   ├── models/
│   ├── services/
│   ├── views/
│   ├── security/
│   └── tests/
│
├── b2b_service/
│
├── b2b_resource/
│
└── b2b_erp_connector/
    ├── models/
    ├── services/
    ├── adapters/
    ├── data/
    ├── views/
    └── tests/
```

根据实际依赖可以适当调整，但保持职责分离。

---

# 五十一、代码质量要求

要求：

- Python 类型和命名清晰
- 方法保持小而单一职责
- 不复制业务逻辑
- 不 Hardcode Secret
- 不 Hardcode Customer Type
- 不 Hardcode ERP URL
- 不 Hardcode Pricelist ID
- 不 Hardcode Database ID
- 使用 XML ID
- 使用 Odoo ORM
- 保持 Upgrade Friendly
- 不修改 Core
- 注释解释 Why，不解释明显的 What

---

# 五十二、配置原则

管理员可以在 Odoo 后台配置：

- Customer Segments
- Price Mapping
- Product Visibility
- Resource Visibility
- ERP Base URL
- ERP Enabled
- Timeout
- Retry Policy

凭证不得写进 Git。

使用 Odoo/Odoo.sh 适合的安全配置机制保存。

如果采用 `ir.config_parameter`，限制配置界面的访问权限，并在技术文档中明确说明敏感信息如何保护、备份和轮换。

---

# 五十三、异常处理

客户不应看到：

```text
Python Traceback
SQL Error
ERP Raw Error
Internal Host
Token
Database ID
```

统一业务错误：

```text
We could not process your request.
Please try again later.
```

运营后台可以看到详细错误。

---

# 五十四、状态机

不要允许非法状态跳转。

例如 Sample：

```text
submitted
→ approved
```

允许。

但：

```text
rejected
→ erp_synced
```

不允许。

状态变化通过业务方法控制，例如：

```python
action_submit()
action_approve()
action_reject()
action_retry_erp()
```

不要让所有用户随便写：

```text
state
```

---

# 五十五、第一阶段不做的功能

除非实现基础架构必须，否则第一阶段不要擅自增加：

- AI Agent
- LangGraph
- Recommendation AI
- Chatbot
- Online Payment
- Complex Checkout
- Marketplace
- Kubernetes
- Kafka
- Microservices
- Elasticsearch
- 独立 React 系统

保持系统简单。

但代码结构要能支持未来扩展。

---

# 五十六、最终验收目标

首先，系统管理员应该能够：

```text
Apps
↓
搜索 B2B Management
↓
Install
```

然后自动安装整个 B2B 应用所需的子模块。

安装完成后，Odoo 首页 / 后台应出现一个统一的：

```text
B2B Management
```

应用入口。

最终运营人员应该能够：

```text
登录 Odoo Backend
↓
创建 Product
↓
上传图片
↓
填写描述
↓
上传 Datasheet / Manual / Video
↓
配置哪些客户能看
↓
配置价格
↓
Publish
```

之后：

**无需修改代码，网站自动呈现新产品。**

运营人员应该能够：

```text
Sample Request
↓
Review
↓
Approve
↓
自动推送 ERP
```

运营人员应该能够：

```text
Service Request
↓
Review
↓
Process
```

客户应该能够：

```text
Login
↓
看到符合自己身份的商品
↓
看到自己的价格
↓
查看 Product
↓
下载有权限的资料
↓
Request Sample
↓
提交 Service Request
↓
查询自己的 ERP Order Status
```

---

# 五十七、需要生成的项目文档

代码完成过程中同时维护：

```text
README.md
ARCHITECTURE.md
SECURITY.md
ODOO_MODELS.md
ERP_INTEGRATION.md
DEPLOYMENT.md
TESTING.md
```

`README.md` 写清：

- 如何安装
- Module Dependencies
- Odoo Version
- 如何升级模块
- 如何测试

`ARCHITECTURE.md`：

- 模块关系
- Request Flow
- ERP Flow
- Future AI Architecture

`SECURITY.md`：

- Groups
- ACL
- Record Rules
- Public Routes
- Portal Routes
- File Security
- ERP Secret Handling
- Threat Model

`ERP_INTEGRATION.md`：

- Adapter Interface
- DTO
- Mapping
- Authentication
- Timeout
- Retry
- Idempotency
- Error Handling

---

# 五十八、Codex 的执行方式

现在开始开发时，请按照以下顺序进行。

## Step 1

首先检查当前 Repository。

确认：

- Odoo 版本
- 当前 addons
- manifest
- dependencies
- repository structure

不要假设仓库为空。

## Step 2

阅读上述 Odoo 官方文档。

特别是：

```text
ORM
Controllers
Security
QWeb
Assets
Website Theme
Pricelist
Products
Testing
Odoo.sh
```

## Step 3

先输出：

```text
Architecture Plan
Module Dependency Graph
Data Model
Security Model
Routes
ERP Integration Design
File Tree
```

不要一上来写所有代码。

## Step 4

先建立顶层 App：

```text
b2b_management
```

要求：

- `application=True`
- `installable=True`
- App Icon
- B2B Root Menu
- Dashboard Placeholder
- 暂时只依赖已经实际创建完成的模块，随着后续模块完成逐步补齐依赖

然后建立基础模块：

```text
b2b_core
```

先完成：

- Customer Segments
- Partner Extension
- Product Visibility
- Pricelist Mapping
- Security

## Step 5

完成：

```text
b2b_website
```

包括：

- Layout
- Product Catalog
- Product Detail
- Customer Price
- Product Visibility

## Step 6

完成：

```text
b2b_resource
```

## Step 7

完成：

```text
b2b_sample
```

## Step 8

完成：

```text
b2b_service
```

## Step 9

完成：

```text
b2b_erp_connector
```

真实 ERP 文档没有提供时使用 Mock Adapter。

## Step 10

完成自动化测试。

## Step 11

完成安全检查。

重点检查：

```text
ACL
Record Rule
sudo
Public Controller
CSRF
CAPTCHA
Attachment
IDOR
Price Leakage
ERP Secret Leakage
Order Enumeration
```

## Step 12

提供 Staging 部署说明。

---

# 五十九、遇到不明确要求时

不要为了小问题停止整个开发流程。

采用：

```text
Secure Default
+
Configurable Design
+
Document Assumption
```

例如 ERP API 未提供：

不要虚构。

建立 Adapter。

例如 UI Design 尚未提供：

建立语义清晰、组件化的基础 Theme 和 Placeholder Layout，使后续设计稿可以替换，而不重写业务逻辑。

---

# 六十、最重要的设计原则

始终遵守以下原则：

**1. Odoo 是业务 Source of Truth，ERP 是其负责领域的数据 Source of Truth。**

**2. 前端只是业务能力的展示层，不成为权限层。**

**3. 价格必须服务端计算。**

**4. 商品可见性必须服务端判断。**

**5. 文件下载必须服务端授权。**

**6. 订单不能只凭订单号任意查询。**

**7. ERP 写入异步、可重试、幂等。**

**8. 不修改 Odoo Core。**

**9. 尽量复用 Odoo 标准模型。**

**10. 所有自定义功能通过 Addons 扩展。**

**11. Controller 保持轻量。**

**12. 业务逻辑设计成可复用 Service，为未来 LangGraph / AI Agent 使用。**

**13. AI 永远不直接访问数据库，也不获得管理员级无限权限。**

**14. Security、Maintainability、Extensibility 优先于短期 Hack。**

**15. 最终交付必须表现为一个 `B2B Management` 顶层可安装 App，技术子模块通过依赖自动安装，不要把每个子模块都做成独立业务 App。**

**16. GitHub 是代码 Source of Truth；Odoo.sh 负责 Build/Deploy；Odoo 数据库中的 Module Install/Upgrade 必须作为部署流程的一部分明确管理。**

现在从 Repository Inspection 和 Architecture Plan 开始。

# Partner Hub 运营人员操作手册

版本：V4.6（2026-09-03 注册与公司审核流程修订）
适用系统：Odoo 19 Enterprise + Partner Hub
适用对象：管理员、B2B Manager、Sales、Product、Marketing、PMC、After-sales、Integration Manager

## 1. 使用原则

Partner Hub 前台用于客户注册、登录、浏览商品、查看客户价、申请样品、支付、查看订单、提交售后和联系团队；Odoo 后台用于客户审批、权限、产品主数据、价格表、内容、样品审核、Helpdesk 和 ERP 集成管理。

运营时遵循以下原则：

1. 公司、联系人、登录用户、权限组分别维护，不把所有资料都堆在用户账号上。
2. 产品、客户、报价、订单、支付、Helpdesk、Repair、附件尽量使用 Odoo 原生模型和流程。
3. 先确认客户和公司，再确认权限，最后修改业务数据。
4. 价格、库存、订单、客户审批和 ERP 重试均属于敏感操作。
5. 不在网站模板、图片或公开文档中写死 SKU、价格、库存或客户隐私。

## 2. 后台入口与角色

登录 Odoo 后进入 `B2B Management`。

常用入口：

- `Dashboard`：显示当前账号有权处理的运营指标和快捷入口。
- `Operations → Sample Requests`：样品申请。
- `Operations → Contact Requests`：联系请求。
- `Operations → ERP Jobs`：仅 Integration Manager 可见。
- `Business Data → Customers`：Odoo 原生联系人和公司。
- `Business Data → Products`：Odoo 原生产品主数据。
- `Business Data → Product Media`：Marketing/Product 人员维护原生产品图片和视频 URL。
- `Configuration`：仅 B2B Manager 可见，包含分群、品牌、应用、首页商品、FAQ 和设置。

### 2.1 B2B 权限组

| 权限组 | 主要职责 |
|---|---|
| B2B Operator | B2B 基础查看和日常处理；其他 B2B 角色通常包含它 |
| B2B Manager | 客户审批、样品批准/拒绝、分群及 Partner Hub 配置 |
| B2B Special Price Manager | 特殊价格表、客户专属价和敏感价格规则 |
| B2B Product Manager | 产品、品牌、应用、可见范围及商品内容 |
| B2B Marketing Media | 产品图片、视频 URL、说明书、证书和展示资源 |
| B2B PMC | 供应链、计划及 ERP 供货协作 |
| B2B After-sales | Helpdesk、维修、更换和售后跟进 |
| B2B Integration Manager | ERP 队列、接口日志、异常和受控重试 |

权限继承关系：

```text
B2B Operator
├── B2B Manager
├── B2B Special Price Manager
├── B2B Product Manager
├── B2B Marketing Media
├── B2B PMC
├── B2B After-sales
└── B2B Integration Manager
```

以上 B2B 角色均使用 Odoo 原生 `res.groups` 权限机制，不是另一套独立权限系统。统一在 `Settings → Users & Companies → Users` 中分配；普通内部用户不会自动获得 B2B Operator。

为减少重复配置，岗位稳定需要的原生权限已经包含在 B2B 角色中：

| B2B 角色 | 自动包含的原生权限 | 不会自动包含 |
|---|---|---|
| B2B Operator | Internal User | 客户审批、联系人编辑、价格、产品、Helpdesk、库存管理 |
| B2B Manager | Contacts 管理 | Special Price、产品、Helpdesk、库存、ERP 管理 |
| B2B Special Price Manager | Contacts 管理、敏感价格维护授权 | 客户审批、客户分群、产品和库存管理 |
| B2B Product Manager | Product Manager | 特殊价格、客户审批、库存管理 |
| B2B Marketing Media | 仅产品图片和文档资源维护 | 产品模板、价格、库存、客户审批 |
| B2B PMC | Inventory User | Purchase、Inventory Manager、客户审批 |
| B2B After-sales | Helpdesk User | Helpdesk Manager、Repair/Inventory、客户审批 |
| B2B Integration Manager | ERP 队列管理 | 客户审批、价格、产品和库存管理 |

仍按实际岗位单独增加以下高权限：

- Sales：报价单和销售订单。
- PMC：确实需要创建采购单时增加 Purchase User；Inventory Manager 单独审批。
- After-sales：需要创建维修单或操作库存时增加 Inventory/Repair；Helpdesk Manager 单独审批。
- Marketing：Website/Marketing；只有确需创建产品时才加产品创建权限。
- ERP/IT：不应顺带授予无关业务权限。

Odoo 原生 Sales Manager 会获得特殊价格维护权限，但不会因此获得 B2B Manager 或客户审批权限。Settings Administrator 也不会自动获得任何 B2B 业务角色；如管理员同时承担业务审批，需要明确分配 B2B Manager。

客户审批、撤销审批、Customer Segments 和 ERP 客户资料仅允许 B2B Manager 修改；客户 Pricelist 仅允许 B2B Manager 或 B2B Special Price Manager 分配。限制同时作用于页面、导入和 API，不要使用导入或直接修改字段绕过审批按钮。

纯 `B2B Marketing Media` 可以通过 `Product Media` 和产品的 `Documents` 维护媒体资源，但产品模板仍保持只读，不能修改价格、库存或产品主数据。

## 3. 客户、公司与登录账号

### 3.1 数据结构

- 公司：`Contacts` 中 `Company` 类型的商业伙伴。
- 联系人：归属公司，可有多个。
- 登录用户：通过邀请或注册绑定到联系人。
- Partner Hub 审批、Customer Segments、Pricelist 和 ERP 客户号维护在公司层级。

避免重复创建同名公司。发现重复记录时先核对邮箱、地址、税号和商业伙伴关系，再由管理员合并。

### 3.2 前台注册与合作申请

普通客户在注册页一次性填写姓名、职位、待审核公司名称、国家、Business Email、Mobile/WhatsApp、Business Type、密码，以及可选的公司电话、公司网站和 Products of Interest。

注册后的状态流转为：

```text
Verify Email → Partner Review → Access Activated
```

提交注册时只创建未激活的 Portal 用户和注册申请，客户填写的公司名称不会立即创建正式公司。客户验证邮箱后账号激活，申请进入 `Partner Review`，B2B Management Dashboard 才显示 Pending Registration。B2B Manager 审核时选择关联已有公司或创建新公司；批准后系统把个人联系人归入公司并批准公司 Partner Hub 权限。

待审核客户可以登录 My 页面查看 `Partner registration under review`，但在公司正式关联并审批前不会获得完整 B2B 价格、受限商品和业务权限。

详细字段、邮箱验证、审核、拒绝及异常处理参见 [Partner Hub 注册与审核流程操作手册](PARTNER_HUB_注册与审核流程操作手册.md)。

旧的 `Request Company Setup` / Company Change 流程继续用于历史账号、人工邀请账号以及审核后需要调整公司归属的客户，不再是新客户注册的必经步骤。

客户可通过 `/partner-application` 填写：

- Legal company name
- Country / region
- Company website
- Business type
- Full name、Role / title、Business email、Phone
- Markets, channels and project types
- 信息确认勾选项

提交只产生审核请求，不会自动获得 Partner Hub 权限。

### 3.3 邀请联系人登录

1. 进入 `Contacts`。
2. 打开或新建联系人，并确认其归属公司。
3. 填写唯一且正确的邮箱。
4. 使用 Odoo 原生门户访问授权/邀请功能发送邀请。
5. 客户完成密码设置后成为 Portal 用户。

用户已存在时不要重复邀请，应先检查邮箱对应的联系人和公司层级。

### 3.4 审批公司

前提：操作账号必须有效拥有 `B2B Manager`。Sales Manager、Special Price Manager、Product Manager、PMC、After-sales、Marketing 和普通内部用户都不能审批客户。

新注册客户按以下流程审批：

1. 进入 `B2B Management → Dashboard → Pending Registrations`，或 `Operations → Pending Registrations`。
2. 检查客户姓名、职位、邮箱、公司名称、国家、电话、网站、Business Type 和 Products of Interest。
3. 在 Contacts 搜索公司名称、域名和电话，确认是否已有正式公司。
4. 已有公司：选择 `Link Existing Company` 和正确的 `Resolved Company`；现有公司资料不会被注册资料覆盖，只补充原本为空的字段。
5. 没有公司：选择 `Create New Company`，系统使用审核后的资料创建正式公司。
6. 点击 `Approve & Activate`。系统自动关联个人联系人、批准公司并发送通过邮件。
7. 进入公司记录检查 Customer Type、Customer Segments、基础价格表、公司专属价格覆盖和 ERP 客户信息。

人工邀请、历史账号或 Company Change 请求仍可在公司记录中由 B2B Manager 点击 `Approve Partner Hub Access`。

取消权限时点击 `Revoke Partner Hub Access`。撤销后，客户不应继续看到受保护价格、受限商品或付费样品入口。

### 3.5 公司和公司用户变更

客户不能直接改变商业伙伴归属。公司资料或公司成员调整通过 Company Profile 的申请入口或 `/contact` 提交：

- `Company Change`
- `Company User Change`

处理尚未关联公司的 `Company Change` 请求时：

1. 在 `Operations → Contact Requests` 核对申请人、公司名称、域名、地址、税号和申请理由。
2. 搜索 Contacts，确认目标公司是否已经存在，避免创建同名公司。
3. 已有公司：核实申请人身份后，将个人联系人关联到该公司。
4. 没有公司：先创建 `Company` 类型联系人，再把申请人关联到新公司。
5. 在公司记录维护 Customer Segments、Pricelist 和 ERP 客户号；确认资料后由 B2B Manager 审批公司。
6. 在请求 Chatter 记录核验依据和处理结果，再 Resolve/Close。

Partner Hub 审批、Customer Segments、Pricelist 和 ERP 客户号以公司为唯一业务来源。同一公司下所有登录联系人共享这些配置；个人联系人页面只显示公司的有效值，不应再单独编辑或审批。把已有个人联系人关联到公司时，系统会清除其历史遗留的个人审批、分群和 ERP 客户号，避免新旧配置冲突；Pricelist 使用 Odoo 原生商业伙伴继承机制。

重要变更在 Chatter 留痕。若历史数据中已有重复未完成申请，先核对后关闭重复项；新版本会阻止同一客户再次创建重复的未完成公司申请。

## 4. Customer Segments、商品可见性和价格

### 4.1 创建分群

1. 进入 `B2B Management → Configuration → Customer Segments`。
2. 点击 `New`，填写 Name、Priority、Active。
3. 需要填写业务含义时，点击行末的打开表单按钮，填写 Description。
4. 使用 Sequence 手柄调整顺序；数字越小越靠前。

Priority 用于多个分群同时存在时的业务优先级；Description 应写清适用客户和可见范围，不写价格规则本身。

### 4.2 给公司分配分群和价格表

Customer Segments 只能由 B2B Manager 修改；Pricelist 可以由 B2B Manager 或 B2B Special Price Manager 分配。

1. 打开客户公司。
2. 在 `Partner Hub` 中选择一个或多个 Customer Segments。
3. 分配正确的 Pricelist。
4. 检查是否已审批并保存。

客户属于多个分群时，商品只要允许其中任意一个分群即可显示；实际价格仍由客户公司当前 Pricelist 决定。

### 4.3 产品可见范围

打开 `Business Data → Products → 产品 → Partner Hub`，设置：

- `All Visitors`：公开访问者可见。
- `Approved Partners`：仅已审批公司可见。
- `Segments`：仅指定分群可见，并填写 Visible Segments。
- `Hidden`：前台下架或内部测试。

受限商品使用直接 URL 也应不可访问。发布前分别使用游客、未审批客户和不同分群客户验证。

### 4.4 价格表

价格使用 Odoo 原生 Pricelist：

1. 进入 Sales 的 Pricelists。
2. 设置名称、币种、适用公司和价格规则。
3. 规则可按商品、模板或分类设置固定价、折扣、最小数量和有效期。
4. 将 Pricelist 分配到客户公司。

未审批客户显示报价提示；已审批客户按公司价格表显示价格。Marketing 和 Product 人员不应修改销售价格，价格由 Special Price Manager、Sales Manager 或管理员维护。

### 4.5 默认 MOQ 与客户覆盖

上架产品时，在产品 `Partner Hub → Catalog → Default B2B MOQ` 填写默认最小订购数量。该值必须大于零，未特别维护时默认为 1。

前台最终 MOQ 按以下优先级计算：

1. 客户公司当前 Pricelist 中存在适用于该商品的原生 `Minimum Quantity` 规则时，使用该客户级 MOQ。
2. 价格表没有适用的数量规则时，使用产品的 `Default B2B MOQ`。
3. 前台商品卡片、商品详情、默认购买数量及购物车服务端校验使用同一个最终 MOQ。

因此，大多数商品只需在上架时维护一次默认 MOQ；只有客户存在特殊起订量时，才在其公司价格表中设置 `Minimum Quantity`。MOQ 不控制商品可见性，也不替代价格规则。

## 5. 产品主数据、分类、品牌与媒体

### 5.1 创建或维护产品

进入 `B2B Management → Business Data → Products`。填写并复核：

- Product Name、Internal Reference/SKU、Can be Sold
- Odoo 内部 Product Category
- Website Published
- Sales Description、Ecommerce Description
- Brand、Model Number、Applications
- Default B2B MOQ、Lead Time、Warranty
- Website Categories
- Visibility Mode 和 Visible Segments
- 技术规格和 Partner Hub 内容

产品主数据只在 Odoo 产品记录维护。

### 5.2 内部分类与网站分类

产品顶部的 `Product Category` 用于库存、成本、会计和内部报表；`Website Categories` 使用 Odoo 原生 eCommerce Categories，控制首页分类、产品筛选和品牌页导航。两者不能互相替代。

创建多层网站类目：

1. 进入 `Website / eCommerce → Products → eCommerce Categories`。
2. 从顶层到末级逐级创建并设置 Parent Category。
3. 建议为顶层类目上传统一比例 Cover Image。
4. 在产品 `Partner Hub → Catalog → Website Categories` 中选择最具体的末级类目。

例如：

```text
Microphones
└── Wireless Microphones
    └── Direct Bluetooth
        └── Handheld
```

只选 `Handheld` 即可形成完整前台路径。一个商品可以多选末级类目，但没有明确需求时只选一个主要路径，避免重复展示。

类目不显示时检查：Can be Sold、网站发布、Website Categories、B2B Visibility、网站归属，以及分支下是否存在当前用户可见商品。空分支会自动隐藏。

### 5.3 Product Applications

进入 `Configuration → Product Applications` 创建应用标签，设置 Name、Sequence、Active，并在产品 Partner Hub 区域关联。应用用于产品筛选和场景说明，不替代 Website Categories。

### 5.4 Product Brands

进入 `Configuration → Product Brands`。B2B Manager 或 Product Manager 可新建，Operator 只读。

字段：

- Name：品牌正式名称，不重复。
- Tagline：首页品牌卡片和品牌页副标题。
- Sequence：数字越小越靠前；首页最多取前 6 个有效品牌。
- Active：停用后前台隐藏但不删除商品关系。
- Website Published：是否发布。
- Logo：品牌详情页标识，建议透明 PNG；系统最大处理 512×512。
- Cover Image：首页品牌卡片，建议统一横向比例；系统最大处理 1920×1080。
- Website Description：品牌历史、定位、能力、产品和服务区域。
- Product Focus：每行一项，前台显示为标签。
- Advantages：每行一项，前台显示为优势列表。
- Internal Notes：仅内部可见。

在产品 `Partner Hub → Catalog → Brand` 关联品牌。品牌只有在 Active、Website Published 且至少关联一个当前用户可见商品时才在前台出现。

品牌页自动包含 Logo/名称/Tagline、该品牌类目、前 4 个可见商品、介绍、Product Focus、Advantages 和查看全部商品入口。

### 5.5 图片和视频 URL

Marketing 推荐使用：

`B2B Management → Business Data → Product Media`

1. 点击 New。
2. 选择 Product Template；仅变体专用素材时再选 Product Variant。
3. 填写 Name、Sequence。
4. 上传图片，或填写受支持的完整 Video URL。
5. 保存后用有权限的客户账号检查产品详情。

Product Manager 也可在产品的 Sales/eCommerce Media 区域使用 Odoo 原生 Add Media。

图片命名建议：`SKU_用途_序号.jpg`。视频不要包含客户隐私、内部价格或未公开工程资料。

### 5.6 说明书、证书和资源

1. 打开产品，点击顶部 `Documents`。
2. 点击 Upload 或新增文档。
3. 上传 PDF、规格书、安装手册、测试报告或证书，或使用 URL 类型。
4. 设置资源类型、版本、语言、网站显示和 Partner Hub 可见范围。
5. 变体文档需要在 Partner Hub 发布时使用 `Publish Variant Document in Partner Hub`。

受限文档必须用无权限账号测试直接 URL，不能只检查页面是否隐藏。

## 6. 首页内容

### 6.1 Featured Products

进入 `Configuration → Homepage Featured Products`，设置 Section、Product、Sequence、Website、Active。

- Recommended：无行为客户使用默认池；有浏览/购买记录时优先使用 Odoo 原生 Optional Products，不足再补默认池。
- Special Offers：人工促销/阶段主推，不在此处修改价格。
- Best Sellers：当前为人工选定，并非按订单销量自动排名。

每个栏目最多读取 10 个有效商品。同商品不能在同网站同栏目重复，但可进入不同栏目。使用 10、20、30 的 Sequence，临时下线关闭 Active，不必删除。

未发布、不可销售或对当前客户不可见的商品不会显示。Recommended 无配置时有普通商品兜底；其他栏目无配置时显示空状态。

### 6.2 Our Brands

首页最多展示 Sequence 最靠前的 6 个有效品牌，卡片优先使用 Cover Image。缺图时显示品牌名称。排查顺序：Active、Website Published、关联商品、商品发布、Website Categories、Visibility、Sequence。

## 7. FAQ

仅 B2B Manager/管理员维护：

- `Configuration → FAQ Categories`
- `Configuration → Frequently Asked Questions`

分类字段：Name、Website、Sequence、Active。问题字段：Question、Category、Sequence、Published、Active、Answer、Action Label、Action URL。

常用 Action URL：

| 功能 | URL |
|---|---|
| 联系销售 | `/contact` |
| 订单 | `/my/orders` |
| 样品申请 | `/my/sample-requests` |
| 联系会话 | `/my/inquiries` |
| 下载资源 | `/resources` |
| 项目支持介绍 | `/repair-service` |
| 新建售后申请 | `/service` |
| 配送说明 | `/shipping` |
| 产品列表 | `/products` |

分类和问题分别用 Sequence 排序。临时下线优先取消 Published；取消 Active 会让后台默认列表也可能隐藏。前台 `/faq` 支持分类筛选、搜索、展开答案和业务按钮。

## 8. 付费样品申请

### 8.1 客户提交

前提：公司已审批，产品对客户可见且有有效价格。

客户从商品详情的 `Request Sample`，或 `Sample Center → New Sample Request` 进入，填写 Product、Quantity、Reason / Project Use、联系人、公司、邮箱、电话、Shipping Address 和可选备注，然后提交。

系统防止连续点击重复创建。客户在 `My Account → Sample Requests` 查看编号、日期、产品、状态、运营回复、报价、金额、支付入口和 ERP 状态。

### 8.2 后台审核

进入 `Operations → Sample Requests`：

1. 检查客户公司、联系方式、地址、产品变体、数量、用途和权限。
2. B2B Operator 点击 `Start Review`，状态进入 Under Review。
3. 公开消息会显示给客户；内部说明使用 Note。
4. B2B Manager 点击 `Approve & Create Quotation`。

批准后系统使用 Odoo 原生 Sales：创建唯一报价单、写入商品数量、按客户 Pricelist 计算币种/税费/单位、关联客户和地址，并要求全额付款。价格为零时阻止批准。

不符合要求时填写原因并点击 Reject。常见原因包括不提供样品、数量过多、地址不完整、项目资料不足或地区不支持配送。

### 8.3 客户付款

客户在样品详情点击 `Review & Pay`，进入 Odoo 原生报价单，核对商品、数量、单价、税费、配送、币种和总额，再使用已配置的支付提供商付款。

- 成功：支付交易成功，报价单确认，样品进入 Order Confirmed 或 ERP Pending。
- Pending：保留报价和申请，不进入 ERP。
- Error/Cancelled：保留报价和申请，可重新付款，未成功前不履约。

样品状态：Submitted、Under Review、Awaiting Payment、Order Confirmed、ERP Pending、ERP Synced、ERP Failed、Rejected、Cancelled。

不要在付款前手工发货或触发 ERP；不要为同一申请重建第二张报价。修改报价优先使用 Odoo 原生报价功能。ERP 关闭时付款后显示 Order Confirmed；ERP Failed 仅 Integration Manager 执行 Retry ERP。

## 9. 售后与维修

### 9.1 配置

如果前台提示 `Partner service is not configured yet`：

1. 在 `Helpdesk → Configuration → Helpdesk Teams` 创建或确认 Partner Hub Support 团队。
2. 添加负责人和成员并启用团队。
3. 在 Partner Hub 设置中绑定该 Helpdesk Team。
4. 团队 Visibility 使用允许受邀 Portal 用户和内部人员访问的配置。

### 9.2 客户提交

前提是客户存在 Confirmed/Sale 或完成状态的订单。没有合格订单时显示 `No eligible orders`，属于正常限制。

客户进入 `Service Center → New Service Request` 或 `/service`，填写：

- Repair 或 Replacement
- 已确认订单
- 该订单中的产品
- Model number、可选 Serial number
- Problem description
- 联系人、公司、邮箱、电话
- 最多 5 个附件，每个 10 MB；支持 PDF、PNG、JPG/JPEG、ZIP

当前表单没有单独的“故障数量”和“现场情况”字段；相关内容写入 Problem description。当前不直接上传视频，需要时把材料整理为 ZIP，或在后续 Helpdesk 会话中按公司政策提供。

提交会创建 Helpdesk Ticket，不会直接创建 Repair Order。客户在 `Service Center` 或 `My Account → Service Tickets` 查看和回复。

### 9.3 售后人员处理

1. 进入 Helpdesk 的 All Tickets 或 Unassigned Tickets；不要只看 My Tickets。
2. 清除不必要的 My Tickets/Open 筛选，按编号、客户或时间搜索。
3. 检查订单、商品、型号、序列号、描述、附件和保修范围。
4. 分配负责人，使用内部 Note 记录内部判断，公开消息回复客户。
5. 需要实体维修时使用 Odoo 原生 Repair 创建或关联 Repair Order。
6. Replacement 按库存、退回旧件和发出新件的原生流程处理。
7. 更新 Helpdesk 阶段，完成后填写解决说明并关闭。

未分配的新工单不会出现在某员工的 My Tickets；关闭工单也可能被 Open 筛选隐藏。不要直接修改原订单金额或客户价；退款、换货和库存调整使用对应 Odoo 原生流程。

## 10. Contact Request 闭环

### 10.1 请求类型

`/contact` 支持 Sales Inquiry、Technical Support、Sample Request、Partnership、Company Change、Company User Change、Other。

这些类型用于分类、筛选和显示，不会自动路由到不同部门：

| 条件 | 自动分配 |
|---|---|
| Website Salesperson 是有效 B2B Operator | 分配给该 Salesperson |
| 未配置 Salesperson | 分配给第一个有效 B2B Operator |
| Salesperson 不是 B2B Operator | 忽略并选择有效 B2B Operator |
| 运营人员点击 Start | 改为当前操作人员 |

Technical Support 不会自动创建 Helpdesk；Sample Request 不会自动创建正式付费样品。故障维修引导至 Project Support/Service Center，正式样品引导至商品详情或 Sample Center。

### 10.2 后台处理

进入 `Operations → Contact Requests`：

1. New：核对类型、主题、公司、联系人、正文和负责人。
2. 点击 Start：进入 In Progress，并由当前人员接手。
3. 使用 Send Message 对客户公开回复；内部讨论使用 Note。
4. 问题明确处理后点击 Resolve。
5. 客户确认、长期未回复、重复/无效或已转正式业务流程时点击 Close。

状态为 `New → In Progress → Resolved → Closed`。关闭前建议在 Chatter 写明原因。客户在 `My Account → My Inquiries` 查看请求和回复。

### 10.3 各类型后续

- Sales Inquiry：使用 Odoo 原生报价单和客户 Pricelist。
- Technical Support：一般咨询在 Contact 中回复；实体故障转 Helpdesk 售后。
- Sample Request：解释政策后引导正式付费样品。
- Partnership：审核资料后维护公司/联系人并执行审批。
- Company Change/User Change：核实身份后在 Contacts 修改并留痕。

## 11. 订单、支付与 ERP

客户在 `My Account → Orders` 查看编号、日期、状态、金额，进入详情查看商品、数量、价格和地址。已确认订单可使用 `Track ERP Fulfilment`。

运营人员在 Odoo 原生 Sales Orders 中按订单号、客户或日期核对。ERP Jobs 仅 Integration Manager 可见；不要因同步失败手工重复创建订单，应先检查幂等键、引用编号、状态和错误，再执行 Retry。

客户只能看到自己商业伙伴范围内的订单，不要把一个客户的订单、截图、价格或地址发送给另一个客户。

## 12. 日常检查与故障排查

每日检查：

1. 待审批客户。
2. 待审核样品。
3. 新 Contact Requests。
4. 有权限时检查 Helpdesk、ERP Pending/Failed。
5. 新增或变更的商品、品牌、FAQ 和资源。

发布前检查：

- 名称、SKU、品牌、型号、类目和主图正确。
- 描述和资源不含内部备注、客户隐私或写死价格。
- Visibility、Segments、Pricelist 和 MOQ 正确。
- 图片、视频 URL、说明书和证书可打开。
- 受限商品和文档的直接 URL 已用无权限账号测试。
- 游客、未审批、不同分群客户看到的商品和价格符合预期。

发现以下情况立即暂停发布并通知管理员：

- 客户看到不属于自己的价格、订单或地址。
- 未审批客户看到正式价格。
- 受限商品或文档可通过直接 URL 打开。
- Marketing 可以修改价格、库存或产品主数据。
- 订单、样品或 ERP 同步重复生成。
- 样品、售后或 Contact 无法关联正确客户。

常见排查顺序：

1. 公司是否重复、联系人归属是否正确。
2. 登录用户是否绑定正确联系人。
3. 公司是否审批，Segments 和 Pricelist 是否正确。
4. 商品是否发布、可销售、分类和 Visibility 是否正确。
5. Helpdesk Team、Visibility、负责人和默认筛选是否正确。
6. 内部员工的 B2B 组和 Odoo 原生应用权限是否匹配。
7. 网站公司邮箱、电话、地址和社交链接是否为最新。

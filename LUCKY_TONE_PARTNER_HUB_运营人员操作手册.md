# Lucky Tone Partner Hub 运营人员操作手册

版本：V4.1  
适用系统：Odoo 19 + Lucky Tone Partner Hub  
适用对象：管理员、B2B Manager、Sales、Product、Marketing、After-sales

## 一、先了解系统中的角色分工

Partner Hub 前台负责客户注册、登录、查看商品、样品申请、购物车、订单和售后入口；Odoo 后台负责客户审批、产品主数据、客户标签、样品审核和运营数据管理。

常用后台入口：

1. 登录 Odoo 后台。
2. 点击应用菜单，进入 **B2B Management**。
3. 常用菜单包括：
   - Dashboard：查看待处理运营事项。
   - Operations → Sample Requests：处理客户样品申请。
   - Operations → ERP Jobs：查看需要 ERP 同步的任务。
   - Business Data → Customers：查看客户和客户审批状态。
   - Business Data → Products：进入 Odoo 原生产品主数据。
   - Configuration → Customer Segments：维护客户人群标签。

产品、客户、销售订单仍然使用 Odoo 原生数据，不要在系统外另建一套产品或客户台账。

## 二、客户注册后的基本流程

### 2.1 普通客户的操作

1. 客户打开 Partner Hub，点击注册。
2. 填写姓名、邮箱、密码和公司信息。
3. 注册成功后登录网站。
4. 客户可以浏览允许公开展示的商品，但在公司审批前通常看不到正式价格。
5. 客户可进入 **My Account → Company Profile** 查看审批状态。

审批状态有两种：

- `Approval pending`：公司资料等待运营人员审核。
- `Partner Hub Approved`：客户已经获得 Partner Hub 价格和服务权限。

### 2.2 运营人员审批客户

1. 后台进入 **Contacts**，搜索客户公司或注册邮箱。
2. 打开客户的公司联系人记录，不要只打开个人联系人记录。
3. 检查公司名称、邮箱、电话、国家、地址和客户类型。
4. 在 Partner Hub 相关区域检查：
   - B2B Approved：是否已审批。
   - Customer Segments：客户所属人群标签。
   - Pricelist：客户对应的价格表。
5. 确认资料无误后，点击 **Approve Partner Hub Access**。
6. 给客户分配一个或多个 Customer Segment。
7. 保存记录。
8. 通知客户退出后重新登录，或刷新页面确认价格已经生效。

如果需要取消权限，打开客户记录后点击 **Revoke Partner Hub Access**。取消后，客户不应继续看到受保护价格或受限商品。

## 三、使用人群标签展示不同商品和价格

### 3.1 价格控制的基本原则

系统通过三个条件决定客户是否可以看到价格：

1. 客户公司是否已经 B2B Approved。
2. 客户公司属于哪个 Customer Segment。
3. 产品使用哪个 Pricelist，以及该价格表中的价格规则。

客户没有审批时，前台通常显示 **Request a quote for pricing**。  
客户审批后，系统按照客户所属公司的价格表显示价格。  
系统不会因为客户修改浏览器页面内容而改变 Odoo 服务器中的实际价格。

### 3.2 创建或维护人群标签

1. 后台进入 **B2B Management → Configuration → Customer Segments**。
2. 点击 **New**。
3. 填写标签名称，例如：
   - Dealer
   - Integrator
   - Strategic Partner
   - Regional Distributor
4. 填写说明，说明该标签对应的客户类型和适用范围。
5. 保存。

建议标签按业务规则命名，不要使用客户姓名、邮箱或临时测试名称。

### 3.3 给客户分配标签

1. 进入 **Contacts**。
2. 搜索并打开客户公司的商业伙伴记录。
3. 找到 **Customer Segments** 字段。
4. 选择一个或多个标签。
5. 检查客户的 Pricelist 是否正确。
6. 保存。

如果客户属于多个标签，产品只要允许其中任意一个标签即可展示。价格仍由客户实际使用的 Pricelist 决定。

### 3.4 给产品配置人群可见范围

1. 进入 **B2B Management → Business Data → Products**，或进入 Odoo 原生 **Sales → Products → Products**。
2. 搜索并打开产品。
3. 确认产品已勾选 **Sales / Can be Sold**，并已配置网站发布状态。
4. 找到 Partner Hub 相关字段 **Visibility Mode**。
5. 根据业务选择：
   - `All`：所有允许浏览的客户都可看到。
   - `Approved`：只有已审批客户可看到。
   - `Segments`：只有指定 Customer Segments 可看到。
   - `Hidden`：前台不展示，适合下架或内部测试。
6. 如果选择 `Segments`，在 **Visible Segments** 中选择允许访问的标签。
7. 保存。

### 3.5 给不同人群配置不同价格

价格应在 Odoo 原生 Pricelist 中维护：

1. 进入 **Sales → Products → Pricelists**。
2. 打开对应价格表，或点击 **New** 新建价格表。
3. 填写价格表名称、币种和适用客户范围。
4. 在价格规则中添加产品、产品分类或产品模板。
5. 设置固定价格、折扣、最小数量和有效期。
6. 保存。
7. 回到客户公司记录，把该 Pricelist 分配给客户。

示例：

| 客户人群 | 客户标签 | 价格表 | 产品价格 |
|---|---|---|---:|
| Dealer A | Dealer | UAT Dealer Pricelist | 100 |
| Integrator B | Integrator | UAT Integrator Pricelist | 80 |

### 3.6 配置后的检查方法

运营人员必须用实际客户账号检查：

1. Dealer A 登录后查看产品列表和产品详情。
2. 确认价格与 Dealer A Pricelist 一致。
3. Integrator B 登录后确认显示另一套价格。
4. 未审批账号登录，确认只显示报价提示。
5. 访客访问产品页面，确认页面源码和页面文本中没有实际价格。
6. 隐藏产品使用直接链接访问，应返回不可访问或 404。

## 四、普通注册用户申请样品

### 4.1 客户前台操作

1. 客户登录 Partner Hub。
2. 进入 **Samples**，或在产品详情点击 **Request a Sample**。
3. 在 Product 中选择产品或产品变体。
4. 填写 Quantity。
5. 填写 Reason / Project Use，说明项目用途和测试目的。
6. 检查 Contact Name、Company、Email、Phone。
7. 填写 Shipping Address。
8. 如有需要，填写 Additional Notes。
9. 点击 **Submit Sample Request**。
10. 系统跳转到样品详情页，并生成类似 `SAM-2026-000008` 的申请编号。

客户可以在 **My Account → Samples** 中查看申请状态和申请详情。

### 4.2 样品申请状态

| 状态 | 含义 | 客户下一步 |
|---|---|---|
| Submitted | 已提交，等待审核 | 等待运营人员处理 |
| Under Review | 运营人员正在审核 | 等待结果或补充资料 |
| Approved | 审核通过 | 等待发样或 ERP 同步 |
| Rejected | 审核未通过 | 查看原因，必要时重新申请 |
| ERP Pending | 已进入 ERP 同步队列 | 等待 ERP 处理 |
| ERP Synced | ERP 已接收 | 按系统提供的物流或履约信息跟进 |

### 4.3 运营人员审核样品

1. 后台进入 **B2B Management → Operations → Sample Requests**。
2. 按 Created、State 或客户名称查找申请。
3. 打开申请，检查：
   - 客户是否为已审批客户。
   - 产品是否属于客户允许访问的范围。
   - 数量是否合理。
   - 申请用途是否清晰。
   - 联系人和收货地址是否完整。
4. 点击 **Start Review**，状态变为 `Under Review`。
5. 如果需要补充信息，通过 Odoo 的消息区联系客户或内部负责人。
6. 审核通过点击 **Approve**。
7. 审核不通过时，填写 Rejection Reason，然后执行拒绝操作。
8. 审批通过后，系统会生成 ERP Jobs 或进入 ERP Pending 状态。
9. 在申请详情的 ERP 区域查看同步状态和错误信息。

不要直接修改状态字段来代替审批按钮。审批按钮会同时记录审核人、审核时间和业务状态。

## 五、已购买客户申请售后

售后流程必须基于客户已经确认的销售订单。没有确认订单时，前台会显示 **No eligible orders**，这是正常的业务限制。

### 5.1 客户前台操作

1. 客户登录 Partner Hub。
2. 进入 **My Account → Orders**，确认订单已经是 Confirmed / Sale 状态。
3. 进入 **Service Center**，点击 **New Service Request**。
4. 选择关联订单和订单行。
5. 选择服务类型：
   - Repair：维修。
   - Replacement：更换。
6. 填写问题描述、产品序列号、故障数量和现场情况。
7. 上传必要的照片、检测报告或视频证据。
8. 填写联系人和联系方式。
9. 点击提交。
10. 客户在 **My Account → Service** 中查看工单进度。

### 5.2 售后运营人员操作

1. 后台进入 **Repairs** 或 After-sales 相关菜单。
2. 查找客户提交的 Repair / Replacement 请求。
3. 检查关联销售订单、产品、数量和序列号。
4. 检查是否仍在保修或售后服务范围内。
5. 确认问题类型和处理责任人。
6. 分配负责人，并补充内部备注。
7. 需要维修时，创建或关联 Repair Order。
8. 需要更换时，确认库存、退回旧件和发出新件的处理方式。
9. 更新工单状态并在消息区记录处理过程。
10. 完成处理后关闭工单，填写解决方案和完成日期。

售后人员不要直接修改原销售订单金额或客户价格。退款、换货和库存调整应通过 Odoo 对应的原生流程完成。

## 六、运营人员上传商品链接、图片、视频和说明书资源

### 6.1 创建或维护商品

1. 后台进入 **B2B Management → Business Data → Products**。
2. 点击 **New** 创建产品，或搜索并打开已有产品。
3. 使用 Odoo 原生产品字段维护：
   - Product Name
   - Internal Reference / SKU
   - Product Type
   - Sales Price
   - Product Category
   - Sales / Can be Sold
   - Website Published
4. 在 Partner Hub 字段中维护：
   - Model Number
   - Brand
   - Application
   - Product Tags
   - Short Description
   - Technical Specifications
   - Visibility Mode
5. 保存产品。

产品主数据只在 Odoo 产品记录维护，不要在网站页面里写死 SKU、价格或库存。

### 6.2 上传产品图片

1. 打开产品记录。
2. 在产品图片区域点击添加图片。
3. 上传主图，建议使用清晰的正方形或横向产品图片。
4. 添加其他图片作为图库图片，例如包装、接口、安装效果或尺寸图。
5. 调整第一张图片为主图。
6. 保存。
7. 打开前台产品详情页，确认主图、图库和缩略图均能显示。

图片命名建议：

`SKU_用途_序号.jpg`，例如 `UAT-P2_front_01.jpg`。

### 6.3 上传视频或视频链接

1. 打开产品记录的媒体或营销内容区域。
2. 如果系统提供视频链接字段，填写完整的视频 URL。
3. 如果系统提供附件上传区域，上传经过压缩的视频文件。
4. 填写视频标题和说明。
5. 保存。
6. 以客户账号打开产品详情页，确认视频只在允许的客户范围内展示。

视频不要上传包含客户隐私、内部价格或未公开工程资料的内容。

### 6.4 上传说明书、证书和其他资源

1. 打开产品记录。
2. 在 Documents / Product Documents 区域点击添加文档。
3. 上传 PDF、规格书、安装手册、测试报告或认证证书。
4. 填写资源类型，例如：
   - Manual
   - Datasheet
   - Certificate
   - Installation Guide
   - Compliance Document
5. 设置版本号和语言。
6. 设置显示范围：
   - `Product`：所有能看到该产品的客户可访问。
   - `Segments`：只允许指定 Customer Segments 访问。
7. 如果是受限资源，选择对应的 Visible Segments。
8. 保存。
9. 使用访客、普通客户和目标客户账号分别测试下载权限。

### 6.5 发布前检查清单

- 产品名称、SKU、品牌和型号正确。
- 主图清晰，图片没有错位或拉伸。
- 产品描述没有内部备注。
- 价格没有写进图片或公开说明书。
- 产品 Visibility Mode 正确。
- Pricelist 规则已经配置。
- 说明书、证书和视频链接可以打开。
- 受限文档不能通过直接 URL 被无权限客户访问。
- 产品前台页面、搜索和详情页均可正常显示。

## 七、客户购买后查看订单进度

### 7.1 客户前台查看订单

1. 客户登录 Partner Hub。
2. 点击右上角账户菜单，进入 **My Account**。
3. 点击 **Orders**。
4. 在订单列表查看：
   - 订单编号。
   - 下单日期。
   - 订单状态。
   - 订单金额。
5. 点击订单编号进入详情。
6. 在订单详情查看产品、数量、价格、地址和订单状态。
7. 对已经确认的订单，可以点击 **Track ERP Fulfilment** 查看 ERP 履约状态。

### 7.2 订单状态说明

| 状态 | 含义 |
|---|---|
| Quotation / Sent | 报价或待确认订单，尚未成为正式销售订单 |
| Confirmed / Sale | Odoo 已确认销售订单 |
| Locked / Done | 订单已锁定或流程完成 |
| ERP Pending | 等待 ERP 同步 |
| ERP Synced | ERP 已接收订单 |
| Preparing | ERP 或仓库准备中 |
| Shipped | 已发货 |
| Delivered | 已交付 |
| Exception | 同步或履约发生异常 |

ERP 履约状态需要 ERP 接口可用时才会实时更新。接口不可用时，客户仍可查看 Odoo 中已经确认的订单信息，但 ERP tracking 可能显示暂不可用。

### 7.3 运营人员协助查询订单

1. 后台进入 **Sales → Orders → Orders**。
2. 按订单编号、客户名称或日期搜索。
3. 打开订单，检查客户、订单行、金额和确认状态。
4. 如果需要查看客户前台能看到的内容，使用对应客户账号进行验证。
5. ERP 相关状态可在订单上的 **ERP Jobs** 或 **Track ERP Fulfilment** 区域查看。
6. 订单同步失败时记录错误信息，不要重复手工创建同一订单。
7. 先确认幂等键、订单编号和 ERP Job 状态，再执行重试。

客户只能看到与自己所属商业伙伴相关的订单。运营人员不要把一个客户的订单截图、价格或地址发送给另一个客户。

## 八、日常运营建议

每天登录 B2B Management Dashboard，依次检查：

1. 待审批客户。
2. 待审核样品。
3. ERP Pending 或 Exception 任务。
4. 新增或变更的产品资料。
5. 需要跟进的售后请求。

发现以下情况时先暂停发布并联系管理员：

- 客户能看到不属于自己的价格。
- 未审批客户能看到正式价格。
- 受限产品或文档可以通过直接 URL 打开。
- Marketing 账号可以修改销售价格或库存。
- 订单同步重复生成。
- 样品或售后记录无法关联客户和订单。

所有运营人员都应遵循“先确认客户、再确认权限、最后修改业务数据”的顺序。价格、库存、订单和客户审批属于敏感业务数据，修改前必须确认记录和操作目的。

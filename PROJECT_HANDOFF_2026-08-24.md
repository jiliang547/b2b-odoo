# POWER & GRACE Partner Hub 项目交接记录

更新时间：2026-08-25（Asia/Shanghai）

本文档用于把当前开发上下文交给新的 Codex 开发窗口。开始工作前，应先阅读本文档，再按任务需要阅读仓库内的架构、部署和测试文档。文档不包含任何管理员密码、数据库密码、GitHub Token 或 ERP Token。

## 1. 项目目标与开发原则

项目是基于 Odoo 19 Enterprise 的 B2B Partner Hub，当前品牌为 **POWER & GRACE**。网站为客户提供产品目录、客户价格、购物车与结账、订单、样品申请、售后服务、询盘消息、资源下载和公司账户功能；后台通过独立的 **B2B Management** 应用提供运营入口。

项目必须继续遵守 V4.1 的 **Odoo Native First** 原则：

- 产品与变体使用 `product.template` / `product.product`。
- 客户与公司使用 `res.partner`，账户使用 Odoo Portal。
- 价格使用 Odoo Pricelist，不在前端或自定义表中复制价格引擎。
- 购物车、结账和订单使用 `website_sale` / `sale.order`。
- 售后工单使用原生 Helpdesk，维修使用 Repair。
- 商品图片和视频使用 Odoo eCommerce media。
- 商品资料使用 `product.document` / `ir.attachment`。
- 自定义代码只放在仓库的 `custom_addons` 中。
- 优先继承原生 QWeb、Controller、ORM、ACL 和业务方法；只有原生确实缺失时才增加自定义模型。
- 所有权限和价格判断必须在服务端完成，不能只靠隐藏按钮。

## 2. 关键需求文档

最终开发基线 Prompt：

`D:\Desktop\lucky_tone_partner_hub_codex_prompt_v4_1_final.md`

UAT 测试文档：

`D:\Desktop\Lucky_Tone_Partner_Hub_V4.1_UAT_测试文档.md`

仓库内的重要说明：

- `README.md`：项目入口和模块说明。
- `ARCHITECTURE.md`：Native / Extension / Custom 架构边界。
- `DATA_OWNERSHIP.md`：数据归属。
- `RBAC_MATRIX.md`：权限矩阵。
- `SECURITY.md`：安全约束。
- `DEPLOYMENT.md`：Odoo.sh 部署流程。
- `TESTING.md`：自动化和验收测试。
- `FUNCTIONAL_COVERAGE_MATRIX.md`：功能覆盖。
- `V4_1_COMPLIANCE_REVIEW.md`：V4.1 逻辑复检。
- `LUCKY_TONE_PARTNER_HUB_运营人员操作手册.md`：现有运营手册。

历史 V2 Prompt 也保存在仓库根目录，但后续需求以 V4.1 Final 为准：

`odoo_b2b_website_codex_prompt_v2.md`

## 3. GitHub 与分支状态

GitHub 仓库：

`https://github.com/jiliang547/b2b-odoo`

本地仓库：

`C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo`

当前长期开发分支：

`agent/figma-b2b-redesign`

截至 2026-08-25：

- 当前分支 HEAD：`8a484a7 Complete partner portal content and sample workflow`
- 远端开发分支 HEAD：`8a484a7`
- 远端 `main`：`b3886a7 Merge pull request #10 from jiliang547/agent/figma-b2b-redesign`
- PR #10 已把 `8a484a7` 合并到 `main`；`origin/main` 与 `origin/agent/figma-b2b-redesign` 的代码树完全一致。
- 本交接文档已包含在 `8a484a7` 中；2026-08-25 本次只是继续更新交接内容。

目前采用的协作方式：Codex 在 `agent/figma-b2b-redesign` 上提交并推送，用户在 GitHub 上把该分支合并到 `main`，随后由 Odoo.sh 构建 `main`。不要未经用户要求直接在 `main` 开发或推送。

每次开始开发先执行：

```powershell
cd 'C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo'
git status --short
git branch --show-current
git fetch origin
git rev-list --left-right --count HEAD...origin/agent/figma-b2b-redesign
```

提交时只暂存本次确认过的文件，不要使用 `git add .` 或 `git add -A`。运行日志、数据库、密钥和临时文件不能提交到 GitHub。

## 4. Figma 设计来源

当前最终 UI 来源是 Figma Make：

`https://www.figma.com/make/CEJSGAT1ncfFp6Pcc3Aebj/B2B-%E4%BC%81%E4%B8%9A%E9%97%A8%E6%88%B7%E7%BD%91%E7%AB%99%E8%AE%BE%E8%AE%A1`

设计中的具体页面通过 `preview-route` 查看，例如：

- 首页：`/`
- 产品列表：`/products`
- 产品详情：`/products/p4`（设计示例路由）
- Portal 首页：`/my`
- 资源：`/resources`

较早的 Figma Design 文件：

`https://www.figma.com/design/BJw4sv23Q0kXYdzfIDRcsy/B2B`

该 Design 文件是早期版本，当前视觉调整以 Figma Make 文件为准。之前已通过远程 Figma MCP 读取设计，不需要连接本地 Figma MCP。

设计适配原则：

- 视觉尽量还原 Figma，但业务状态必须映射 Odoo 实际数据。
- 只修改 `custom_addons`。
- My、订单、购物车、结账等页面继续复用原生逻辑，仅覆盖 QWeb/SCSS/JS。
- 不为设计稿中的假数据创建第二套业务模型。

## 5. 本地 Odoo 环境

Odoo 安装目录：

`C:\Program Files\Odoo 19.0e.20260805`

关键文件：

```text
Python:   C:\Program Files\Odoo 19.0e.20260805\python\python.exe
odoo-bin: C:\Program Files\Odoo 19.0e.20260805\server\odoo-bin
Config:   C:\Program Files\Odoo 19.0e.20260805\server\odoo.conf
Native addons: C:\Program Files\Odoo 19.0e.20260805\server\odoo\addons
Custom addons: C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\custom_addons
Database: b2b_v41_test_20260817
```

端口说明：

- `http://127.0.0.1:8070`：本项目实际测试实例，明确加载工作区 `custom_addons`。
- `http://127.0.0.1:8069`：Odoo Windows 默认服务；不要把它误认为当前项目测试实例，也不要无故停止。

截至 2026-08-25 本次交接检查时，`8070` **未启动**。这是进程状态，不代表模块损坏；新窗口如需本地测试，应先按第 7 节启动。进程 PID 会变化，不要在脚本中写死 PID。`8069` 是 Windows 默认实例，操作前必须重新核对，不要无故停止。

常用日志位于仓库根目录，例如：

- `odoo-logo-runtime.log`
- `odoo-b2b-core-upgrade.log`
- `odoo-b2b-core-tests.log`
- `odoo-product-policy-test.log`
- `odoo-quantity-test.log`

这些日志是本地运行产物，不应提交 GitHub。

## 6. 本地模块升级方法

修改 Python、XML、权限 CSV、manifest 或数据库模型后，仅重启 Odoo 不够，必须执行模块升级。

升级全部 Partner Hub 模块的 PowerShell 示例：

```powershell
$odooPython = 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe'
$odooBin = 'C:\Program Files\Odoo 19.0e.20260805\server\odoo-bin'
$odooConfig = 'C:\Program Files\Odoo 19.0e.20260805\server\odoo.conf'
$customAddons = 'C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\custom_addons'
$allAddons = "C:\Program Files\Odoo 19.0e.20260805\server\odoo\addons,$customAddons"

& $odooPython $odooBin `
  -c $odooConfig `
  --addons-path=$allAddons `
  -d b2b_v41_test_20260817 `
  -u b2b_core,b2b_erp_connector,b2b_sample,b2b_website,b2b_management `
  --stop-after-init `
  --http-port=8071 `
  --logfile='C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\odoo-upgrade-handoff.log'
```

按修改范围可只升级单个模块：

- 核心字段、权限、品牌、类目、价格策略：`-u b2b_core`
- 网站模板、Controller、前端资源：首页和 Portal：`-u b2b_website`
- 后台应用菜单或 Dashboard：`-u b2b_management`
- 样品流程：`-u b2b_sample`
- ERP 队列：`-u b2b_erp_connector`

升级日志必须检查 `ERROR`、`CRITICAL`、`Traceback`，并确认最后出现 `Modules loaded` 和正常退出。

## 7. 重启本地 8070

先解析 8070 当前监听进程，再只停止该 PID：

```powershell
$listener = Get-NetTCPConnection -State Listen -LocalPort 8070 -ErrorAction SilentlyContinue
if ($listener) {
    Stop-Process -Id $listener.OwningProcess -Force
}
```

然后用工作区 addons 路径启动 Odoo：

```powershell
& 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe' `
  'C:\Program Files\Odoo 19.0e.20260805\server\odoo-bin' `
  -c 'C:\Program Files\Odoo 19.0e.20260805\server\odoo.conf' `
  --addons-path='C:\Program Files\Odoo 19.0e.20260805\server\odoo\addons,C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\custom_addons' `
  -d b2b_v41_test_20260817 `
  --http-port=8070 `
  --logfile='C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\odoo-logo-runtime.log'
```

在 Codex 中直接运行时，该命令会保持一个长期执行会话，这是正常现象。启动后验证：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8070
(Invoke-WebRequest -Uri 'http://127.0.0.1:8070/web/login' -UseBasicParsing -TimeoutSec 15).StatusCode
```

## 8. Odoo.sh 部署流程

1. Codex 在开发分支完成修改、模块升级、自动化测试和本地 UI 测试。
2. 推送 `agent/figma-b2b-redesign`。
3. 用户在 GitHub 合并该分支到 `main`。
4. Odoo.sh 从 `main` 构建。
5. 在 Odoo.sh 对受影响模块执行 Upgrade；仅有新 Git commit 和 Build Success 不代表数据库视图/ACL 已更新。
6. 在 Odoo.sh Development/Staging 先验证，再发布 Production。

Odoo.sh 上安装入口模块为：

`Lucky Tone B2B Management`（技术名 `b2b_management`）

它会拉起网站、核心、样品和 ERP 连接器依赖。环境还必须安装/提供 Website、eCommerce、Sales、Portal、Helpdesk、Helpdesk Sale 和 Repair 等 Enterprise 模块。

发布前不要把本地数据库、管理员密码、ERP Token 或 Odoo 配置文件提交到仓库。生产 ERP 在正式接口契约确认前保持关闭。

## 9. 自定义模块清单

| 模块 | 当前版本 | 作用 |
|---|---:|---|
| `b2b_core` | `19.0.1.1.2` | 客户审批、人群标签、产品可见性、价格状态、品牌/应用分类、产品资源策略 |
| `b2b_erp_connector` | `19.0.1.0.0` | 幂等 ERP Job、重试、适配器边界、订单状态 DTO |
| `b2b_sample` | `19.0.1.2.0` | 付费样品申请、报价、Portal 隔离、支付后 ERP 交接 |
| `b2b_website` | `19.0.1.7.1` | 首页、产品、Portal、订单、询盘、售后、FAQ、Shipping、资源和 Figma UI |
| `b2b_management` | `19.0.1.2.1` | 后台 B2B Management 应用、FAQ 和运营导航 |
| `b2b_payment_demo_fix` | `19.0.1.0.0` | Odoo Demo Payment 状态兼容；安装 `payment_demo` 时自动安装 |

## 10. 当前核心业务逻辑

### 10.1 客户、审批、人群标签与价格

- 客户主数据仍是 `res.partner`。
- B2B 审批状态和人群标签扩展在客户/公司上。
- 产品可见模式支持公开、已审批、人群标签和隐藏。
- 价格通过 Odoo 原生 Pricelist 计算。
- 未获授权的访客/客户只得到价格状态，不向 HTML/JSON 输出数值价格。
- 管理员已加入可查看价格的特殊判定。
- Products 列表和详情页已经统一使用客户实际 Pricelist，修复过“列表价与详情价不同”的问题。

### 10.2 商品分类：两套分类的边界

Odoo 原生有两套分类，必须保留各自用途：

- `Product Category` / `product.category`：库存、会计、成本和内部报表。
- `Website Categories` / `product.public.category`：首页多层分类、网站产品筛选和品牌页面分类。

商品表单 `Partner Hub → Catalog` 已直接展示原生 `Website Categories` 字段。运营人员应建立多层 eCommerce Categories，并在商品上只选择最具体的叶子类目；网站使用 `child_of` 自动显示完整父级路径。

类目卡片优先使用 eCommerce Category 的 `cover_image`，没有封面时回退到该类目下代表商品的图片。没有任何当前访客可见商品的空分类会被自动隐藏。

### 10.3 首页 Featured Products

后台入口：

`B2B Management → Configuration → Homepage Featured Products`

三组人工配置：

- `Recommended`
- `Special Offers`
- `Best Sellers`

每组最多读取 10 个有效商品，按 `sequence` 排序。Special Offers 和 Best Sellers 完全人工配置。Recommended 有人工默认池；登录客户有浏览或已确认订单行为时，系统优先读取相关商品的 Odoo 原生 `Optional Products`，不足时再用默认池补齐。

### 10.4 Our Brands

后台入口：

`B2B Management → Configuration → Product Brands`

品牌为自定义缺口模型 `b2b.product.brand`。字段用途：

- `Logo`：品牌详情页顶部 Logo。
- `Cover Image`：首页 Our Brands 卡片图片。
- `Tagline`：首页卡片和详情页简短文案。
- `Website Description`：品牌详情页 About 内容。
- `Product Focus`：每行一项，前台显示标签。
- `Advantages`：每行一项，前台显示优势列表。
- `Sequence`：首页品牌顺序。
- `Website Published` + `Active`：控制前台可见。

商品必须在 `Partner Hub → Catalog → Brand` 关联品牌。首页只显示排序最前的 6 个“已启用、已发布、且至少包含一个当前访客可见商品”的品牌。

品牌详情页的产品分类来自该品牌商品的 `Website Categories`，品牌页默认展示按网站顺序排列的前 4 个可见商品。

最后一次修复为品牌列表增加 `open_form_view="1"`：点击 Name 仍然行内编辑名称；完整编辑 Logo/介绍时，点击该行最右侧的“打开表单”图标。

### 10.5 产品详情与购物

- 支持原生商品变体选择。
- Overview / Specifications / Resources 已改为 Figma 设计中的 Tab 切换，而不是无效锚点滚动。
- MOQ 映射原生 Pricelist 的数量阶梯；没有额外创建 MOQ 字段。
- 数量输入已修复为整数显示与按 1 增减，避免 1.0 和 0.01 步进。
- 已移除详情页 `In Stock` 文案和 `Selected configuration is available.`。
- 产品列表 Add to Cart 采用加入后留在当前页的方式，便于继续选购。
- 加购反馈移到 Quantity 加号右侧。
- 购物车徽标在支付完成后会刷新，避免空购物车仍显示旧数量。

### 10.6 支付与订单

- 继续使用原生 Odoo Payment、Cart、Checkout、Sale Order。
- `b2b_payment_demo_fix` 只修复 Demo Payment 与原生真实支付状态语义不一致的问题，主流程仍围绕标准支付交易设计。
- `/payment/status` 已覆盖 Partner Hub 等待 UI，并提供动态等待反馈和状态闭环。
- Pending、Error、Cancelled 等状态保留订单/报价可见性和继续支付路径。
- Confirmation 页面与购物车状态已做一致性处理。
- 真实支付仍需在 Odoo.sh 配置实际 Payment Provider 后验收。

### 10.7 样品申请

- 样品不是免费审批后直接发货；当前闭环已经调整为 **原生 Odoo 付费报价流程**。
- 已审批且允许样品申请的 Portal 用户可从商品页或 Sample Center 提交申请，并填写/选择交付地址。
- 后台在 `B2B Management → Operations → Sample Requests` 审批，按钮为 `Approve & Create Quotation`。
- 审批会幂等创建且只创建一张原生 `sale.order` 报价单；报价要求 100% 付款，产品价格、税费、币种、地址和支付全部复用 Odoo 原生逻辑。
- 客户在 `My Account → Sample Requests` 打开记录，通过 `Review & Pay` 查看报价并付款。
- 只有原生报价确认后，样品申请才进入 Order Confirmed / ERP Pending 等履约状态；未付款不会进入 ERP 履约。
- 拒绝申请会取消仍处于 Draft/Sent 的关联报价，避免留下可支付的无效报价。
- Portal 只能访问自己商业公司范围内的申请。
- 确认订单后可生成幂等 ERP Job；真实 ERP 未接入时使用关闭或开发 Mock 状态。

### 10.8 售后服务

- `/service` 创建原生 `helpdesk.ticket`，并关联客户、订单、商品和附件。
- 必须在 Odoo Website/Partner Hub 设置中配置 `B2B Helpdesk Team`，否则前台会提示 `Partner service is not configured yet`。
- 后台实际记录应在原生 Helpdesk 对应 Team 中查看；维修/换货继续使用 Helpdesk、Repair 和库存原生流程。
- 所有提交型按钮已增加前端处理中锁定和服务端幂等保护，避免网络卡顿时重复生成工单。

### 10.9 Contact 与 My Inquiries

- 游客和登录用户的 Contact 页面使用自定义闭环，不再跳到无权限的 Contacts 后台模型。
- Contact 提交生成 B2B Contact Request。
- 运营人员可在后台 Contact Requests 中处理并通过 chatter 回复。
- 客户在 `My Account → My Inquiries` 查看询盘和消息。
- 网站顶部搜索与购物车之间已有通知铃铛，显示 My Inquiries 未读数量。

### 10.10 Company Profile

- 未审批用户的 Company Profile 操作通过申请流程处理，不直接向 Portal 暴露 Contacts 写权限。
- 多个账户是否显示在 Company Users，取决于这些联系人的 `commercial_partner_id` 是否真正归属于同一个公司，以及对应 Portal 账户记录是否正确关联。

### 10.11 FAQ、Shipping 与页脚入口

- `/faq` 是可运营维护的 FAQ 页面，分类和问题来自自定义缺口模型 `b2b.faq.category` / `b2b.faq.item`。
- 后台入口：`B2B Management → Configuration → Frequently Asked Questions`；分类入口为同级 `FAQ Categories`。
- FAQ 支持分类、排序、发布状态、富文本答案和可选操作链接。
- `/shipping` 是按当前 Figma 写死的 Shipping Costs and Delivery Times 静态说明页；页面中的时间是规划参考，最终费用和交期以报价/订单为准。
- 页脚 Products 栏当前为 All Products、Downloads、Frequently asked questions、Shipping and Delivery。

### 10.12 网站 Logo 与社交平台配置

- 顶部和底部网站 Logo 现在读取 Odoo 原生 `website.logo`，不再引用写死的图片地址。
- TikTok、Facebook、LinkedIn 使用 Odoo 原生 `website.social_tiktok`、`website.social_facebook`、`website.social_linkedin` 和 `/website/social/...` 跳转路由。
- 运营入口：`B2B Management → Configuration → Settings → Partner Hub`。
- `Partner Hub branding → Partner Hub Logo`：配置网站顶部和底部 Logo。
- `Partner Hub social links`：填写 TikTok、Facebook、LinkedIn 完整公开 URL。
- 未配置的平台显示灰色禁用图标，不产生错误跳转。
- 注意不要把“网站 Logo”和 Our Brands 的商品品牌 Logo 混淆；后者仍在 `Product Brands` 对应品牌表单中配置。

## 11. B2B Management 与权限

`b2b_management` 是 `application=True` 的独立后台应用。根菜单要求 `B2B Operator`，Configuration 要求 `B2B Manager`。

主要自定义组：

- B2B Operator
- B2B Manager
- B2B Special Price Manager
- B2B Product Manager
- B2B Marketing Media
- B2B PMC
- B2B After-sales
- ERP Integration Manager

这些组只补充 Partner Hub 权限，内部员工仍需配置对应 Odoo 原生 Sales、Website/eCommerce、Inventory、Helpdesk、Repair 等权限。

近期权限修复：

- B2B Manager 现在对 Product Brands 和 Product Applications 有完整 CRUD。
- B2B Product Manager 也保留完整品牌/应用维护权限。
- 普通 B2B Operator 只读，不能新建或删除品牌。

如果后台看到应用但主页没有可点击图标，或菜单缺失，先检查用户是否拥有 B2B Operator/B2B Manager，并确认 `b2b_management` 已升级；隐藏菜单不能代替 ACL，权限应同时从 Access Rights 验证。

## 12. 已完成的重要 UI 与逻辑修改

按 Git 历史概括：

- `c8015e3`：V4.1 五模块主体实现。
- `5d5a057`：Odoo 19 本地部署兼容修复。
- `7ca53b9`：Figma B2B Partner Hub 全站 UI 重构。
- `9837572`：UI、运营手册和基础流程收尾。
- `104fa39`：支付、订单、重复提交和工作流加固。
- `e8c05eb`：Contact/Inquiry 闭环和 Portal 通知。
- `9e2315f`：可配置首页、多层类目、Featured Products、Brands、目录/价格/UI 细节。
- `8e938fd`：商品 Website Categories 上架入口和品牌/应用权限修复。
- `f7c18ba`：品牌列表完整表单入口。
- `8a484a7`：付费样品报价闭环、FAQ/Shipping、My 页面统一、Contact/Partner Application 文案、社交链接和可配置网站 Logo。

当前首页包含：

- POWER & GRACE 正式 Logo。
- Hero Banner。
- 动态多层 Product Categories。
- Recommended / Special Offers / Best Sellers 三个 Tab。
- Our Brands（最多 6 个）。
- Project Support 和 Warranty Policy 静态入口。
- 语言与币种选择，数据来自 Odoo 网站配置。

最近一轮公共站点还完成：

- 首页三个板块副标题移除。
- My 页面全部面包屑补齐 `Home / Overview / ...`，左侧导航默认折叠并支持展开。
- My 页面面包屑、标题、副标题使用统一高度，切换子页面时减少上下跳动。
- 登录、注册和重置密码页统一显示 `POWER & GRACE PARTNER HUB`。
- 顶部 Logo、通知、购物车、账户等交互元素不再在 Hover 时出现文字下划线。
- Contact 页面和 Partner Application 页面使用最新确认文案。

## 13. 测试状态

已经完成过两轮基于 V4.1 UAT 文档的本地功能测试，创建了 Dealer、Sales、Product、After-sales 等测试角色。权限补齐后，原先 4 个因权限导致的 FAIL 已复测通过。用户已确认非 ERP 主流程通过，剩余问题不影响主流程。

最近一次 `b2b_core` 升级后运行了 8 项自动化测试：

```text
0 failed, 0 errors
```

其中包含：

- 产品可见性与价格策略。
- 管理员价格权限。
- Pricelist/MOQ 价格。
- B2B Manager 可维护品牌和应用。
- B2B Operator 不可创建品牌。

完整自动化测试命令参考：

```powershell
& 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe' `
  'C:\Program Files\Odoo 19.0e.20260805\server\odoo-bin' `
  -c 'C:\Program Files\Odoo 19.0e.20260805\server\odoo.conf' `
  --addons-path='C:\Program Files\Odoo 19.0e.20260805\server\odoo\addons,C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\custom_addons' `
  -d b2b_v41_test_20260817 `
  -u b2b_core,b2b_erp_connector,b2b_sample,b2b_website `
  --test-enable `
  --test-tags='/b2b_core,/b2b_erp_connector,/b2b_sample,/b2b_website' `
  --stop-after-init `
  --http-port=8071
```

修改前端后还应实际用浏览器测试访客、未审批 Portal、已审批客户和管理员四类会话，不能只做 XML 解析。

`8a484a7` 提交前还完成以下本地验证：

- `b2b_website` 在数据库 `b2b_v41_test_20260817` 升级成功，日志正常出现 `Modules loaded`。
- XML 共 17 个视图文件解析通过；Python compileall、JavaScript `node --check` 和 `git diff --check` 通过。
- `/`、`/contact`、`/contactus`、`/partner-application`、`/web/login` 返回 HTTP 200，最新文案和动态 Logo 生效。
- 动态 Logo `/web/image/website/1/logo` 返回 HTTP 200；三组原生社交路由已渲染。
- 使用临时 Portal 账号检查 `/my`、Orders、Quotes、Sample Requests、Inquiries、Company、Company Users、Personal Profile、Addresses，均返回 HTTP 200，并包含 Home/Overview 面包屑、统一 heading 和默认折叠侧栏；测试账号随后已删除。

## 14. 环境配置要点

Odoo 后台 Website / Partner Hub 设置中需要确认：

- Price Display Mode。
- Guest Price State。
- No-price State。
- 是否要求审批后 Checkout。
- 是否要求审批后 Sample。
- B2B Helpdesk Team。
- Partner Hub Logo。
- TikTok、Facebook、LinkedIn 完整 URL。

商品配置要确认：

- Can be Sold / Published。
- Website Categories。
- Brand。
- Visibility Mode / Segments。
- 原生 Pricelist 规则和数量阶梯。
- Optional Products（Recommended 个性化来源）。
- eCommerce 图片/视频。
- Product Documents 与对应商品关联。

客户配置要确认：

- Portal User 与 Contact/Company 关系。
- B2B Approved。
- Customer Segments。
- 原生 Pricelist。

Odoo.sh 售后测试前必须配置 Helpdesk Team；支付测试前必须配置 Payment Provider。Demo Payment 仅用于模拟状态和验收，不代表生产支付配置已经完成。

## 15. 已知外部依赖与暂缓项

以下不是当前代码可以凭空完成的内容：

1. 真实 ERP Endpoint、认证、字段 Schema 和状态字典尚未提供；生产 ERP Connector 应保持禁用。
2. Odoo.sh 的 Payment Provider、Helpdesk Team、邮件服务器、语言、币种和网站域名属于环境配置。
3. Odoo Enterprise 小版本或 Odoo.sh Build 可能导致原生 XML ID/字段差异；只做兼容性薄补丁，不复制 Helpdesk、Repair、Return 等原生引擎。
4. 跨公司无权访问目前可能返回 403 或 404，权限隔离有效，用户已同意暂不为状态码差异改动。
5. 支付状态期间后台打印行为被用户明确要求暂不处理。
6. Odoo.sh 必须在合并代码后执行模块 Upgrade；若只重新 Build 而没有升级模块，最新菜单、ACL 和 QWeb 视图可能不生效。
7. `8a484a7` 已合并到 GitHub `main`，但本文档无法确认用户是否已在 Odoo.sh 对数据库执行最新模块 Upgrade；新窗口处理线上问题时要先核对 Build 和模块版本。

## 16. 开发时不要做的事情

- 不要直接修改 `C:\Program Files\Odoo...\addons` 中的 Odoo 原生源码。
- 不要把本地调试代码写成只适配 Demo Payment 的生产逻辑。
- 不要自建第二套客户、订单、商品、价格、Helpdesk、Repair 或资源主数据。
- 不要相信浏览器提交的价格、客户 ID、公司 ID、订单 ID 或商品可见性。
- 不要用菜单隐藏代替 ACL/Record Rule。
- 不要把重启服务当成模块升级。
- 不要提交日志、数据库、配置文件或密钥。
- 不要删除或覆盖用户未确认的工作区改动。

## 17. 新开发窗口建议的第一段指令

可以把下面内容直接发送给新的 Codex 窗口：

```text
请先完整阅读：
C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\PROJECT_HANDOFF_2026-08-24.md

再按任务需要阅读仓库内 README.md、ARCHITECTURE.md、DEPLOYMENT.md、TESTING.md，最终需求基线是：
D:\Desktop\lucky_tone_partner_hub_codex_prompt_v4_1_final.md

仓库位置：
C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo

当前开发分支：agent/figma-b2b-redesign
GitHub：https://github.com/jiliang547/b2b-odoo
本地测试地址：http://127.0.0.1:8070
本地数据库：b2b_v41_test_20260817
Odoo：C:\Program Files\Odoo 19.0e.20260805

当前 UI 设计以 Figma Make 文件为准：
https://www.figma.com/make/CEJSGAT1ncfFp6Pcc3Aebj/B2B-%E4%BC%81%E4%B8%9A%E9%97%A8%E6%88%B7%E7%BD%91%E7%AB%99%E8%AE%BE%E8%AE%A1

继续遵守 Odoo Native First，只修改 custom_addons。开始任何修改前先检查 git status、远端分支、本地 8070 服务和相关模块当前数据库版本；修改后执行模块升级、自动化测试和浏览器回归，不要直接推 main。
```

## 18. 当前交接结论

截至 2026-08-25，开发分支 `8a484a7` 已由 PR #10 合并到 GitHub `main`（merge commit `b3886a7`），两者代码树一致。最新版本包含付费样品报价闭环、FAQ/Shipping、My 页面布局统一、Contact/Partner Application 新文案、三组社交链接和可配置网站 Logo。当前本地 8070 未启动，继续本地开发前先启动服务并确认数据库模块版本。新窗口应先 `git fetch`，再检查用户是否在切换窗口期间产生了新的合并或 Odoo.sh 部署。

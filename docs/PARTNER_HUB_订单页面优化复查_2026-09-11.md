# Partner Hub 订单页面优化复查

## 后续补充：样品连线与优惠码入口（19.0.1.15.4）

- 样品流程改为桌面居中的四个节点，节点之间有连续横线；小屏采用纵向节点和竖线。
- 使用原生可选 Promo Code 视图的 active 开关隐藏共享购物车/结算优惠码入口，不删除优惠码数据、不改变折扣计算。
- 修复品牌隐藏视图的升级兼容性：保留原生模板继承节点，仅隐藏推广容器，避免 Planning 等原生布局找不到继承节点。
- 6 项展示回归测试通过；再次执行模块升级成功。日志：odoo-sample-cart-presentation-final.log、odoo-sample-cart-repeat-upgrade.log。
- 以下原记录中的版本和 21 项结果对应前一轮；本次未推送 GitHub。

日期：2026-09-11。环境：本地 8070，b2b_v41_test_20260817。
版本：b2b_website 19.0.1.15.3。未推送 GitHub，未在 Odoo.sh 部署验证。

## 本次完成

1. 样品申请标题下增加四步说明：Submit Request → Review & Quotation → Pay Sample Fee → Order Confirmed。审核通过已经创建报价单，因此末步表示付款后的订单确认。
2. Orders 与 Quotations 共用标题和标签组件，标签固定为 Orders & Payments / Quotations，报价表格沿用网站卡片样式。
3. 报价行右侧增加 View Details，保留编号链接、有效期和过期状态，继续使用原生详情地址及权限。
4. 单改详情的申请理由增加正文容器、保留换行；确认提示与操作区增加内边距；完成、退款、拒绝等状态提示统一留白。
5. 默认示例销售条款不再出现在订单详情。仅识别链接式占位备注，不改写订单数据库备注；其他人工约定及 Payment terms 保留。
6. /terms 不再展示原生示例文本。没有正式内容时返回网站风格的说明页（404、noindex），可点击 Contact us；正式内容继续复用原生公司条款字段，不另建条款管理系统。
7. 移除公共单据侧栏 Powered by Logo、订单软件推广按钮及弹窗，移除网站原生页脚推广调用。没有修改 Odoo 原生源码。

## 浏览器实际验证

- 点击 Orders & Payments / Quotations 往返切换。最终两页标题顶部均为 120px，标签栏顶部 197px，表格顶部 256.5px（当前桌面视口）。
- 实测发现旧 clearfix 伪元素参与 Grid 排列，导致短列表出现约 4.34px 空行；已在门户 Grid 容器范围禁用这些伪元素。
- 点击 S00680 的 View Details，成功进入对应报价详情。
- 订单 S00547、报价 S00680：默认条款块与品牌推广不再出现，Payment terms 正常保留。
- 待确认 OCR/2026/00153：申请理由按行显示，与表格内容左侧对齐；确认提示及 Accept Revised Order / Decline Proposal 按钮有留白。
- 完成状态 OCR/2026/00124：提示不再贴卡片边缘。
- /terms 的 Contact us 实际点击进入 /contact。
- 样品申请页四步指引实际显示，并检查截图；按深色标题背景提高文字对比度。
- 抽查首页、产品列表、样品申请、My 首页、订单详情、两种改单状态、工单列表、消息列表、公司资料、个人资料、购物车、/terms、Terms of Use、Privacy Policy 共 15 个页面，未发现可见 Odoo 品牌文字和 Logo。

工单/发票详情的共享侧栏通过模板层统一覆盖；没有逐一创建所有业务单据实测。此次浏览器验证为桌面视口，手机断点样式已加入，但未进行真实手机设备验证。此次没有重复执行支付全流程。

## 自动回归

日志：odoo-portal-presentation-final-tests.log。

21 项测试通过，0 failed、0 errors：包含原有 16 项改单回归，以及 5 项展示/条款保护测试。
覆盖默认链接隐藏且备注不变、人工约定和外部链接保留、正式条款保留、公共品牌模板移除、报价详情入口。
git diff --check 通过。

## 测试数据

使用已有专用客户 Browser Order Flow Contact / Browser Order Flow Company。
新增报价 S00680、测试订单 S00681、待确认申请 OCR/2026/00153；统一业务参考 PORTAL-PRESENTATION-UAT-20260911。
准备数据使用本地受数据库限制的脚本 scripts/prepare_portal_presentation_uat.py；支付记录为 Demo 测试记录，没有调用真实支付接口。
本次没有点击接受/拒绝这份待确认申请，以便继续检查按钮布局；没有修改真实客户订单。

## 后续销售条款维护

正式销售条款仍放在 Odoo 原生公司条款配置中。当前会拦截空内容、YourCompany 和原生示例免责声明等明显占位内容；这只是展示保护，不代表法律审核或发布审批。
正式内容需要业务负责人确认，不能直接把网站 Terms of Use 当作销售条款，也不要改写已签署的历史订单约定。

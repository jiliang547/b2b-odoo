# 订单修改：浏览器复测记录（已完成本次范围）

环境：本地 8070；版本 19.0.1.15.2。用户授权创建测试账号后，已完成以下双角色 UI 流程。测试不代表真实支付、真实邮件及 Odoo.sh 上线验收。

## 已确认的问题与修复

1. 原先 Edit Proposed Order 跳转原生整页编辑，手册没有说明保存控件。现改为原生报价单弹窗，底部明确提供 Save & Close / Discard；隐藏报价单确认/发送等不适用于修改草案的头部操作。保存只修改草案，不修改原已付款订单。已实际点击验证保存、关闭返回、重新打开数据保留及丢弃未保存修改。
2. 实际 My 页面使用定制布局，覆盖了原生 Order Changes 卡片，侧栏也无入口。现补充 My 首页 View Change Requests 和侧栏 Order Changes，首页统计待客户确认/补款数，沿用当前公司的记录权限。
3. 未付款订单等待审核时，仅顶部付款按钮被隐藏，底部 Accept & Pay 仍然出现且可以打开支付弹窗。已在原生付款/签名资格方法统一限制 pending，并在交易创建及订单确认处增加服务端限制，防止旧窗口/直接请求绕过。
4. 退款凭证字段可选非退款或无关交易。已限制候选范围，并在财务完成时校验原订单、客户、币种、完成状态及金额。
5. 原生收款统计未计入未直接关联销售单的退款，会影响后续改单。已复用原生退款与源交易关系扣除已完成退款，避免重复计数；已确认的线下退款按财务登记的已完成申请扣减。

## 本次实际浏览器操作

- 客户 Browser Order Flow Contact，在已付款测试订单 S00501（$30）点击 Request an Order Change，填写增加商品数量需求，点击 Submit Request，生成 OCR/2026/00077。提交后返回原订单，确实存在 View Change Requests。
- 修改后的 My 首页实际显示 View Change Requests，侧栏存在 Order Changes。
- 客户通过商品卡 Add、购物车 Checkout、地址 Confirm，进入付款页，点击 Submit for Review — Pay Later，生成 S00547（$27.60，ID 546），显示 Review in progress。
- 修复前 S00547 底部 Accept & Pay 可点击并打开 Pay Order 弹窗，已复现；未点击付款。
- 重启加载修复后重新打开 S00547，Review in progress 保留，顶部与底部均不再出现支付/签名按钮。
- 实际点击首页 View Change Requests 成功进入列表，能找到 OCR/2026/00077。

## 自动测试与人工测试分开记录

- 首轮模块升级与 14 项订单修改回归测试通过，0 failed / 0 errors；日志 odoo-order-change-ui-regression.log。
- 新增 pending 支付拦截后的第二轮 14 项回归通过，0 failed / 0 errors；日志 odoo-order-change-ui-regression-guard.log。
- 最终 16 项回归通过，0 failed / 0 errors；日志 odoo-order-change-final-verification.log。覆盖退款匹配、退款不重复扣减、线下退款后再次改单等新增断言。
- 下表中的浏览器操作与服务端测试分开执行；不是用数据库写状态代替点击。

## 双角色实测结果

| 流程 | 实际操作与结果 |
| --- | --- |
| 付款前修改 | S00547：数量 2→3、单价 12→10、运费 0→5；Save manually → Release for Customer Payment；客户支付含税 $40.25，订单确认 |
| 付款后补款 | OCR/2026/00077，S00501：$30→$40.80；草案 Save & Close → Send to Customer → 客户接受 → Demo 补款 $10.80；Completed |
| 等额修改 | OCR/2026/00098，S00501：数量 3→2、单价 10.80→16.20；金额不变，接受后直接 Completed |
| 退款 | OCR/2026/00099，S00547：$40.25→$28.75；客户接受后 Finance Review；原生付款记录 Refund $11.50，R-S00547 确认；关联退款并 Finance Complete；客户 Completed |
| 丢弃草案编辑 | OCR/2026/00100：临时数量 2→99，Discard 后重新打开仍为 2 |
| 客户拒绝 | OCR/2026/00100：正式草案数量改为 3 并发送，客户 Decline Proposal；申请 Cancelled，原订单仍 $28.75、数量 2 |
| 退款后再次补款 | OCR/2026/00124，S00547：$28.75→$40.25；客户补款 $11.50 成功，双方页面 Completed，未把历史退款算成可用余额 |

所有上述业务状态由界面按钮产生，付款/退款使用 Demo。额外数据库读取用于最终核账，不替代 UI 测试。原订单编号保持不变，完成的改单解除交付暂停。

权限隔离、运营拒绝、已交付限制及已发送草案冻结由服务端测试覆盖；本次没有将它们全部再做逐角色浏览器点击。测试邮箱为 .test，投递失败不作为真实邮件验收；真实支付、实际交付和已过账发票处理不在本次实测范围。

正式操作手册：PARTNER_HUB_付款前改单操作手册_2026-09-11.md、PARTNER_HUB_付款后改单操作手册_2026-09-11.md。

本次未推送 GitHub；未操作用户真实订单 S00497。

# Partner Hub 售后退回、维修与换货操作说明

适用版本：b2b_website 19.0.1.16.30（2026-10-12 更新）。当前正式使用方式为外部 ERP / 人工确认履约结果。

## 本次更新：售后不一定需要寄回

审核时在 `Return and Resolution → Approval → Service Handling` 选择处理方式，再点击 `Approve Service`：

| 选择项 | 适用情况 | 后续操作 |
| --- | --- | --- |
| Pending Assessment | 新申请默认值 | 先评估，未选定方式不能批准 |
| No Logistics Required | 远程指导、配置解决 | 批准后直接 In Progress，填写解决结果，Complete Service |
| Dispatch Without Return | 免退补件／换新 | 批准后直接 In Progress，填写结果和发货信息，Confirm Dispatch，收到后 Complete Service |
| Return and Dispatch | 寄回维修／换货 | 按下方完整寄回流程操作 |
| Return Only | 仅需收回，无需再发货 | 收货、处理后填写结果，Complete Service；不会自动退款 |

无需寄回时不显示退回地址和客户运单表单；无需发货时不要求出库信息。批准后处理方式锁定，已有物流记录时也不能直接切换。升级前的工单保留 Return and Dispatch，不改变旧流程。网站新申请统一为 `Technical Support`（后台存储为 `Technical Support / Other Issue`）；申请类型不决定物流方式。历史维修、换货工单及后台原生功能保留。

下方第 4、5 节仅适用于需要寄回的工单，第 6 节仅适用于需要发货的工单。新版按钮 `Approve Service` 替代旧 `Approve Return`，`Confirm Dispatch` 替代旧 `Confirm Shipped Back`；状态 `In Progress` 和 `Dispatched` 分别替代旧处理、寄出名称。客户详情标题统一为 `Service Progress`。

## 1. 初始化和权限

升级应用会安装 Odoo 原生 Helpdesk Stock 和 Helpdesk Repair 连接模块。首次收到某销售公司的售后申请时，系统自动创建该公司的 `Partner Support — 公司名称` 团队；所有销售公司共用同一组阶段。

工单公司跟随原订单的销售公司，不跟随运营人员当前选中的公司。运营人员右上角勾选自己负责的销售公司后，可以集中处理这些公司的工单。需要分配 `B2B After-sales`，或使用 B2B Manager / Helpdesk 管理员。普通内部人员没有审批售后申请的权限。

原先设置页的单一 Helpdesk 团队选项不再负责新申请路由。旧工单升级时按照原订单修正团队和销售公司；没有关联订单的旧工单需要人工核对。旧工单的已关闭阶段保留，不能把旧取消工单当作已完成维修。

原生工单编号同时用作售后参考号，例如 `00114`。客户寄件时填写该编号，不需要再维护另一套 RMA 编号。

## 2. 客户提交

1. 登录网站，进入 `Service Center`，点击 `New Service Request`。
2. `Request type` 只显示 `Technical Support`，默认选中，无需另外选择维修或换货；运营人员后续评估实际处理方式。
3. 选择已确认订单，再选择该订单里的产品；填写型号、序列号、问题描述和联系资料。
4. 如有需要，附上照片或文件。点击 `Submit service request`。
5. 页面返回 Service Center，新申请显示 `Submitted`。点击申请进入详情查看后续进度。

未获批准前，请勿寄件。照片、物流凭证也可通过详情底部的消息区域 `Attach Files` 发送。

## 3. 运营审核

1. 后台进入 `Helpdesk`，找到对应的 `Partner Support — 公司名称`。
2. 点击该团队的 `Open` 数量或 `Tickets`，打开客户工单。
3. 点击顶部 `Review Request`，进入 `Under Review`。
4. 在页面下方 `Return and Resolution → Approval` 选择 `Service Handling`。仅需要寄回时，在 `Return address and instructions` 填写收货人、电话、完整退回地址、允许退回的数量/序列号和包装要求。
5. `Return by` 可填写建议寄出期限；这是一项给客户的提示，不会拒收客户已寄出的迟到包裹。
6. 选择 `Service Handling`（完整寄回流程选 `Return and Dispatch`），点击 `Approve Service`。按钮会先保存当前表单，然后推进阶段；如只保存资料，使用 Odoo 表单顶部的保存图标。

需要寄回的申请批准后，客户看到 `Awaiting Customer Shipment`，详情出现退回说明和运单输入框。不需要寄回的申请直接进入 `In Progress`。

如果拒绝，在 `Customer resolution / rejection reason` 填写客户可见原因，再点击 `Reject Request`。无理由不能拒绝。

## 4. 客户寄回并填写运单

客户打开工单详情，在 `Service Progress` 区域填写：

- `Carrier`：承运商，例如 DHL。
- `Tracking number`：退回运单号。
- `Shipment date`：实际寄出日期。

点击 `Submit Return Shipment` 后进入 `Return in Transit`。运单信息保留展示，重复提交不会覆盖原记录。填错时通过消息联系售后人员核对，避免随意覆盖物流记录。

## 5. 收到客户退货

1. 运营打开同一张工单，确认 `Customer Shipment` 中的运单信息。
2. 仓库或 ERP 确认收到货物后，在 `Receipt / inspection record` 写明实际数量、序列号、包装和产品状态。
3. 点击 `Confirm Return Received`，客户看到 `Received`。
4. 点击 `Start Inspection / Resolution`，进入 `In Progress`。

外部 ERP 模式下，此操作记录经确认的实际结果，不产生 Odoo 库存调拨。缺少收货记录时按钮会提示补充。

## 6. 处理完成并寄回客户

1. 在 `Customer resolution / rejection reason` 填写客户可见的检测和处理结论。
2. 在 `Dispatch to Customer` 填写 `Ship-back carrier`、`Ship-back tracking`、`Shipped back on`。
3. 实际寄出后点击 `Confirm Dispatch`。
4. 客户页面显示 `Dispatched`、处理结论和发货运单。
5. 确认客户收到货且问题已解决后，点击 `Complete Service` 并确认，状态变为 `Completed`。

维修与换货共用这一套流程；不要因为维修已经完成就提前结案。涉及退款或收费维修时仍需单独处理原生报价、贷项通知单及财务收退款；本流程不会自动执行退款或收款。

## 7. 将来使用 Odoo 库存时

工单读取原订单保存的履约模式。不能通过临时修改网站配置改变旧订单的履约归属。

Odoo inventory 模式下，具有相应原生库存权限的人员可使用工单上的 `Return`、`Repair`、`Replace`：

- 收货：创建并验证关联的原生退回入库单，再在工单确认收货。
- 维修：创建并完成关联的 Repair Order。
- 寄回：创建并验证关联的出库单，再确认寄回；原生出库单已有运单号时会带入工单。

未完成的退回单、维修单或出库单会阻止相应售后阶段确认。外部 ERP 模式隐藏这些库存执行入口，避免形成两套库存流水。五销售公司与工厂之间的完整退货库存/财务联动，应在未来切换库存执行方时专门验收。

## 8. 客户状态与通知

完整寄回顺序：Submitted → Under Review → Awaiting Customer Shipment → Return in Transit → Received → In Progress → Dispatched → Completed。无需物流：Submitted → Under Review → In Progress → Completed。免退补发仅增加 Dispatched；仅寄回不经过 Dispatched。

Service Center 的 `Assigned` 表示已分配负责人，`Closed` 包含已完成和已拒绝；不能把分配负责人当作实际维修进度。页面重新打开或刷新时读取最新状态。

阶段变化会写入原生工单消息，并进入 Message Center 和原生邮件通知流程。邮件是否实际送达取决于邮件服务器配置；邮件失败不影响站内查看进度。

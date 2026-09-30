# 用友 ERP 商品、客户映射操作说明

适用模块：Partner Hub Yonyou Connector（`b2b_yonyou`），19.0.1.2.0。本说明讲档案映射和注册审批时新建客户，不覆盖ERP已有档案。当前版本已另行支持销售订单同步，需开启独立开关，详见 [销售订单对接操作说明](YONYOU_SALES_ORDER_OPERATIONS_2026-09-23.md)。

## 一、初始化一次即可

1. 使用拥有 Settings 管理权限、并可进入 B2B Management 配置菜单的管理账号登录后台（本次验收账号同时有 B2B Manager）。
2. 打开 **B2B Management → Configuration → Yonyou ERP Mapping**。
3. 填写 C4 应用的 **App Key / App Secret**。不要把密钥放进商品、客户备注或 Git。
4. 勾选 **Enable Mapping Queries**，允许查询验证。
5. 当前测试阶段保留 **Restrict All Organizations to 999**，管理组织和默认使用组织均为 `999`。本版本的新客户创建还有服务端保护，不能写入正式组织。
6. 完成品牌配置后，勾选 **Create / Verify ERP Customer on Approval**。此后注册审批必须完成 ERP 绑定或创建；不勾选时保留原审批流程。
7. 点击原生表单的保存图标。Token 自动申请及按有效期刷新，不需要运营人员手工复制。

模块随 B2B Management 自动安装，但新数据库默认关闭外部调用，不包含任何密钥。部署到 Odoo.sh 后需要在对应数据库填写连接配置，不会把本地密钥随代码上传。

### 品牌默认配置

打开 **B2B Management → Configuration → Product Brands**，点击具体品牌行最右侧的 **View（Open in form view）** 打开完整表单；不要只点品牌名称进入行内编辑。在法人销售公司相关区域填写：

| 字段 | 用途 |
| --- | --- |
| Contracting / Invoicing Company | 沿用现有品牌所属销售公司，不是 ERP 管理组织 |
| ERP Customer Category Code | 此品牌默认客户分类编码 |
| Verify | 实际查询 ERP，成功显示分类名称 |
| ERP Salesperson Code | 新申请预填的业务员编码，审核时可逐客户修改 |
| ERP Department Code | 部门编码；留空时验证唯一任职部门后自动带出 |
| Verify Salesperson | 核验业务员状态、部门及目标组织任职，展示姓名和部门名称 |

已在 C4 查询确认的客户分类：`05 LIKE`、`06 LUCKY`、`07 BF`、`08 LDU`、`09 PG`、`99 其他`。编码是文本，保留前导零。

这些是ERP客户分类，不是网站的 Distributor / Installer 等价格分类。网站定价逻辑不改变。旧测试曾使用 `LQS0008 / 05`；新增的任职校验要求人员实际在目标组织下有有效任职。本次组织999已验证 `LQSTEST / cs`，不要未经核对套用其他组织人员。

## 二、给商品绑定 ERP 物料

1. **B2B Management → Business Data → Products**，打开商品。
2. 进入 **Partner Hub** 页签，找到 **ERP Material Mapping**。
3. 在 **ERP Material Code** 填 ERP 完整物料编码，例如 `000020`。
4. **Verify for Selling Company** 选择要核验的销售公司；当前测试模式实际都核验 ERP 组织 `999`。
5. 点击编码右边的 **Verify**。
6. 成功时显示 **Verified**、ERP 物料名称、组织以及最后验证时间。

采用 Odoo 原生表单机制：点击对象按钮会先保存当前表单，再执行验证；所以点击 Verify 后映射结果已保存。如果之后又编辑其他内容，再点顶部保存图标。

仅输入编码并保存，不等于验证通过。改编码后必须重新验证。查询失败会撤销旧验证结果，不会继续显示旧的 Verified。

网站商品名称、图片、售价保持 Odoo 管理；ERP 物料主数据继续由 ERP 维护。系统只记录后续下单需要的物料 ID、SKU、单位和组织等绑定信息。

多变体商品：在各个变体资料的 **ERP Mapping** 页签分别维护。当前核验支持已经实测的单 SKU、单位一致的 ERP 物料；ERP 多规格或多单位换算不会被系统自行猜测，须另行确认后扩展。验证成功也不等于已验收未来的自动下单接口。

## 三、给已有客户绑定 ERP 客户

1. **B2B Management → Business Data → Customers**，打开客户的**公司档案**，不是公司下面的个人联系人。
2. 进入 **Partner Hub**。
3. 在 **Collection and Brand** 区域，沿用现有流程设置 **Account Brand / Assigned Selling Company**。
4. 在销售公司旁的 **ERP Customer Category Code** 填分类编码，点击旁边的 **Verify**，核对返回名称。
5. 找到 **ERP Customer Code**，填 ERP 客户编码，点击右边的 **Verify & Refresh**。
6. 核对 **ERP Verification Result** 的客户名称、组织及自动回填的 **ERP Customer ID**，同时检查 **ERP Salesperson Code / Name**、**ERP Department Code / Name**。已有绑定只读；换负责人先在ERP修改，再刷新，分类Verify不会更换负责人。

联系人共享客户公司的绑定，无须逐个联系人填写。旧的 ERP Customer ID 现在在表单中只读，由验证回填；旧历史 ID 不能代替本次 Verified 结果。

查询只核验，不修改 ERP 客户名称、分类、业务员等资料。选择的分类与 ERP 实际分类不一致时会阻止绑定；先核对是否选错客户或分类。

一个 ERP 客户不能重复绑定两家 Odoo 客户公司。若客户已经绑定，给新联系人关联原有公司即可。

## 四、新注册客户审核

客户仍按原流程注册、激活邮箱。**不是提交注册后立即在 ERP 建档**，而是运营审核确认后才创建。

进入 **B2B Management → Operations → Pending Registrations**，打开申请，核对客户填写的信息。

### 情况 A：客户公司已经存在

1. **Company Resolution** 选择 **Link Existing Company**。
2. **Resolved Company** 选择已存在的 Odoo 客户公司。
3. 打开这家公司的 Partner Hub 页签，按上一节完成 ERP 客户编码验证。
4. 返回注册申请，点击 **Approve & Activate**。
5. 系统会重新查询 ERP 核验，再把联系人关联到该公司并完成原生审批。不会新建或覆盖 ERP 客户。

若 ERP 已有客户但 Odoo 没有公司档案：先在 Customers 创建 Odoo 公司、绑定已有 ERP 编码，再回到申请选择 Link Existing Company。

### 情况 B：确实是新客户

1. **Company Resolution** 选择 **Create New Company**。
2. 在 **ERP Customer Mapping** 选择 **Account Brand**。
3. 系统带出品牌默认分类；核对后点击分类右边的 **Verify**。
4. **ERP Customer Code (blank = generate for new company)** 可以留空，系统生成稳定测试编码；如果手填，必须符合 ERP 编码规则且未被使用。
5. 核对品牌带出的 **ERP Salesperson Code / ERP Department Code**，可以改为该客户专属负责人。点 **Verify Salesperson** 确认姓名、部门和验证状态；部门留空仅在可唯一确定时自动填入。
6. 点击 **Approve & Activate**。
7. 系统实时核验负责人 → 查询是否已存在 → 在 `999` 创建 → 查回核对包括业务员和部门的结果 → 建立/复用Odoo公司 → 关联联系人 → 完成原生审批。资料缺失或核验失败停留在待审核。

首次创建带入审核后的公司名称、国家、公司邮箱、公司电话、联系人、手机、网站及品牌分类；管理组织、客户来源/交易类型、汇率类型、支付方式等使用后台默认值，专管业务员和部门使用本次审核的指定值（初始从品牌预填）。不发送密码、激活令牌，也不把网站价格类型误当成ERP客户分类。创建请求冻结后不允许改负责人绕过重试保护。

## 五、错误和重试

| 提示/状态 | 如何处理 |
| --- | --- |
| No exact ERP ... code was found | 核对编码和前导零；不是自动创建授权 |
| 客户存在但使用组织不可用 | 请 ERP 人员处理组织分配，不要重复创建客户 |
| 分类未验证 | 在申请的分类框旁点击 Verify，再审批 |
| 分类不一致 | 核对客户身份和品牌，不会自动改 ERP 分类 |
| 接口权限/连接失败 | 管理员核对授权、密钥、组织和网络；申请保持待审核 |
| 创建请求超时 | 使用同一申请重试，不另建申请、不改编码；先查询 ERP，存在则核验复用 |
| 上次创建资料与本次不一致 | 不会自动覆盖或再次创建；管理员先核查原编码对应的 ERP 客户，再决定如何关联 |

新建请求使用稳定编码及幂等键防止重复提交。若进程崩溃使本地事务完全回滚，但 ERP 已建档，系统会发现编码已存在并停止自动创建；按“已有客户”流程核查关联，不盲目重建。

## 六、权限与边界

- 商品映射：B2B Product Manager 或 B2B Manager。
- 客户、分类、注册审批：B2B Manager；仍受原生记录权限和允许公司范围限制。
- 密钥配置：Settings 管理员；普通客户、产品人员不能读取密钥。
- 客户映射和验证不回写ERP客户资料，不自动分配组织；订单同步有独立开关，参见销售订单操作说明。
- 切换正式环境需先确认正式组织映射和业务默认值，并解除当前新建客户的 `999` 保护后另行验收；仅去掉界面测试勾选不会允许正式创建。

# Partner Hub 注册与审核流程操作手册

版本：V1.1（2026-09-03）

适用系统：Odoo 19 Enterprise + Partner Hub

适用对象：网站客户、B2B Manager、B2B Operator、Special Price Manager

## 1. 流程目的

本流程用于完成客户自助注册、邮箱真实性确认、公司资料预审核、公司建立或关联，以及 Partner Hub 权限激活。

完整状态流转如下：

```text
提交注册
→ Verify Email（等待验证邮箱）
→ Partner Review（运营审核）
→ Access Activated（审核通过并激活 B2B 权限）
```

审核不通过时进入 `Rejected`；邮箱验证链接过期时进入 `Email Link Expired`。

核心原则：

1. 注册时填写的公司名称首先作为待审核资料，不会立即生成正式公司。
2. 邮箱验证成功后才进入运营人员的待审核列表。
3. 只有 `B2B Manager` 可以批准、拒绝或重新开启注册申请。
4. 审核人员必须先搜索现有公司，避免创建重复公司。
5. Customer Type、价格表、Partner Hub 审批等业务配置以公司为准，个人联系人继承公司配置。

## 2. 使用前准备

### 2.1 系统准备

上线前确认：

- Odoo 已配置可用的出站邮件服务器。
- 网站允许客户自由注册。
- 邮件中的网站域名为正式可访问域名。
- CAPTCHA/机器人验证使用 Odoo 19 原生 Cloudflare Turnstile；正式启用时需配置生产密钥。
- `B2B Management → Configuration → Customer Types & Base Pricing` 已维护客户类型。
- 每个需要使用的客户类型，已经按网站和币种设置基础价格表。

若客户类型没有对应网站和币种的基础价格表，审核仍可完成，但客户登录后可能没有正确的 B2B 基础价格。

### 2.2 Cloudflare Turnstile 配置

系统已经安装 Odoo 19 原生 `Cloudflare Turnstile` 模块，注册表单使用原生 `captcha='signup'` 服务端验证链。不要在页面中另外粘贴 Cloudflare JavaScript，也不要自行新增 token 校验代码。

正式启用步骤：

1. 在 Cloudflare 控制台创建 Turnstile Widget，并把正式网站域名加入允许列表。
2. 复制 Cloudflare 提供的 Site Key 和 Secret Key。
3. 进入 Odoo `Settings → General Settings`。
4. 找到 `Cloudflare Turnstile`，分别填写 `CF Site Key` 和 `CF Secret Key` 后保存。
5. 使用无痕窗口打开 `/web/signup`，填写测试资料并完成一次注册。
6. 确认验证失败时不会创建账号，验证成功时才进入 Verify Email 流程。

注意：

- Site Key 可以发送到浏览器；Secret Key 只能保存在 Odoo 系统参数中，不能写进代码、文档或 Git。
- 两个 Key 必须来自同一个 Cloudflare Widget。
- 本地和自动化测试只能使用 Cloudflare 官方测试 Key，禁止把测试 Key 配到生产环境。
- 没有配置 Secret Key 时，Odoo 原生逻辑会把 Turnstile 视为未启用；因此上线验收必须同时检查两个 Key。
- 当前 Google reCAPTCHA 模块仍由 Odoo 安装，但未配置 Google Key；机器人验证由 Turnstile 承担，不需要重复配置两套服务。

### 2.3 人员权限

| 角色 | 可以查看注册申请 | 可以修改待审资料 | 可以批准/拒绝 |
|---|---:|---:|---:|
| B2B Operator | 是 | 否 | 否 |
| B2B Manager | 是 | 是 | 是 |
| B2B Special Price Manager | 按其已有权限 | 否 | 否 |
| 普通内部用户 | 否 | 否 | 否 |

权限统一在 `Settings → Users & Companies → Users` 使用 Odoo 原生权限组分配。

## 3. 客户注册操作

### 3.1 打开注册页

客户可以：

- 打开 `/web/signup`；或
- 在登录页点击 `Create account`。

### 3.2 填写注册资料

注册页字段如下：

| 字段 | 是否必填 | 用途 |
|---|---:|---|
| Full Name | 是 | 联系人姓名 |
| Job Title | 是 | 联系人职位 |
| Company Name | 是 | 待审核公司名称，不会立即创建正式公司 |
| Country / Region | 是 | 联系人及待创建公司的国家/地区 |
| Business Email | 是 | 登录账号及邮箱验证地址 |
| Company Phone | 否 | 公司联系电话 |
| Mobile / WhatsApp | 是 | 联系人移动电话或 WhatsApp |
| Business Type | 是 | Distributor、Integrator、Installer 等客户类型 |
| Company Website | 否 | 公司网站 |
| Products of Interest | 否 | 客户关注的产品方向 |
| Password | 是 | 登录密码 |
| Confirm Password | 是 | 再次确认密码 |
| Terms of Use / Privacy Policy | 是 | 条款及隐私政策确认 |

填写完成后点击 `Submit for Approval`。

提交成功后：

1. 系统建立一个尚未激活的 Portal 用户和一条注册申请。
2. 页面提示客户检查邮箱。
3. 注册申请状态为 `Verify Email`。
4. 此时运营 Dashboard 不计入 `Pending Registrations`，因为邮箱尚未验证。

### 3.3 验证邮箱

客户打开系统发送的验证邮件，点击验证链接。

验证成功后：

- Portal 登录账号被激活。
- 注册申请进入 `Partner Review`。
- 系统为一名可用的 B2B Manager 建立审核待办活动。
- `B2B Management Dashboard → Pending Registrations` 数量增加。
- 客户可以登录 My 页面查看 `Partner registration under review`，但尚未获得正式 B2B 公司权限。

验证链接有效期为 24 小时，并且只能使用一次。

### 3.4 没有收到邮件或链接过期

客户可以在注册成功页面或链接过期页面点击 `Resend verification email`。

注意：

- 同一邮箱一分钟内不能重复发送。
- 为防止他人探测账号，系统无论是否找到注册记录都显示相同的通用提示。
- 重发后旧链接失效，应使用最新一封邮件中的链接。
- 如果邮箱地址填写错误，客户无法自行改变该注册邮箱，应联系运营人员核查，必要时使用正确邮箱重新注册。

## 4. 运营人员审核

### 4.1 查看待审核提醒

邮箱验证成功后，运营人员可以：

1. 进入 `B2B Management → Dashboard`。
2. 查看 `Pending Registrations` 数量。
3. 点击该指标；或进入 `Operations → Pending Registrations`。
4. 打开具体申请。

`Pending Registrations` 只显示已经验证邮箱并等待审核的申请。仍处于 `Verify Email` 的客户不会显示在这里。

### 4.2 审核资料

在申请表单中检查：

- Full Name 与 Business Email 是否合理。
- Job Title 是否与采购、技术、项目或经营身份相符。
- Company Name、Country、Phone、Website 是否相互一致。
- 邮箱域名是否与公司网站匹配；免费邮箱需要增加人工核验。
- Business Type 是否选择正确。
- Products of Interest 是否与业务描述相符。
- 是否已经存在同名、同域名、同电话或同地址公司。

在 `Partner Review` 或 `Rejected` 状态下，B2B Manager 可以先修正客户提交的资料，再执行最终决定。修改前应在 Chatter 记录核验依据。

## 5. 关联已有公司

客户所属公司已经存在时使用此方式。

1. 在 Contacts 搜索公司名称、网站域名、邮箱域名、电话和税号。
2. 确认找到的记录是 `Company`，不是个人联系人。
3. 返回注册申请。
4. 将 `Company Resolution` 设为 `Link Existing Company`。
5. 在 `Resolved Company` 选择核实后的公司。
6. 再次检查该公司的 Customer Type、基础价格表、专属价格覆盖、Segments 和 Partner Hub 状态。
7. 点击 `Approve & Activate`。

系统处理结果：

- 注册用户对应的个人联系人归入所选公司。
- 已有公司的名称、电话、网站、国家和 Customer Type 不会被注册资料静默覆盖。
- 只有公司对应字段原本为空时，系统才使用注册资料补充电话、网站、国家或 Customer Type。
- 公司获得 Partner Hub 审批状态。
- 联系人继承公司的客户类型、商品权限和有效价格表。
- 客户收到审核通过邮件。

重要：如果客户填写的 Business Type 与已有公司的 Customer Type 不一致，应先人工确认。系统以已有公司资料为准，不自动改写。

## 6. 创建新公司

确认系统中不存在该公司时使用此方式。

1. 使用名称、域名、电话和国家再次搜索 Contacts，确认没有重复公司。
2. 返回注册申请并修正明显的拼写或格式错误。
3. 将 `Company Resolution` 设为 `Create New Company`。
4. 确认 Company Name、Country、Company Phone、Company Website 和 Business Type 正确。
5. 点击 `Approve & Activate`。

系统自动完成：

1. 创建 `Company` 类型的正式联系人记录。
2. 将审核后的公司名称、电话、网站、国家和 Customer Type 写入新公司。
3. 将注册用户对应的个人联系人归入新公司。
4. 把姓名、职位、邮箱、Mobile/WhatsApp 和 Products of Interest 写入个人联系人。
5. 批准新公司的 Partner Hub 权限。
6. 根据 Customer Type、网站和币种生成公司的有效价格表。
7. 发送审核通过邮件。

审核完成后，建议进入新公司记录补充以下正式资料：

- Legal Name、完整地址、税号/VAT。
- 销售负责人和内部标签。
- Customer Segments。
- ERP 客户号及同步资料。
- 必要的公司专属价格覆盖。

## 7. 拒绝申请

只有 `Partner Review` 状态可以直接拒绝。

1. 在 `Rejection Reason` 填写清晰、可对外说明的原因。
2. 点击 `Reject`。
3. 系统将状态改为 `Rejected` 并发送拒绝邮件。
4. 客户登录后会看到申请需要处理及拒绝原因。

常见拒绝原因：

- 无法验证公司真实性。
- 邮箱、网站或联系方式明显不一致。
- 重复申请或重复账号。
- 公司资料不足，需要客户补充。
- 申请不符合当前合作政策。

需要重新审核时，B2B Manager 点击 `Return to Review`，修正资料后再选择关联或创建公司。

不要使用模糊或带有内部敏感信息的拒绝原因，因为该内容会展示给客户。

## 8. 状态说明

| 后台状态 | 含义 | 客户账号 | 运营动作 |
|---|---|---|---|
| Verify Email | 已提交，尚未验证邮箱 | 未激活 | 通常等待客户验证 |
| Email Link Expired | 验证链接超过有效期 | 未激活 | 客户重新发送验证邮件 |
| Partner Review | 邮箱已验证，等待审核 | 已激活，但没有正式 B2B 公司权限 | B2B Manager 审核 |
| Access Activated | 审核通过 | 已激活并关联已审批公司 | 检查价格、Segments 和 ERP 后续配置 |
| Rejected | 审核未通过 | 可以登录查看状态，但没有 B2B 公司权限 | 根据情况 Return to Review |

## 9. 审核后的价格与商品检查

审批完成不等于所有商业配置都一定正确。建议按以下顺序检查：

1. 公司 Customer Type 是否正确。
2. `Customer Types & Base Pricing` 中是否存在当前网站、币种对应的基础价格表。
3. 公司是否需要专属价格覆盖；数值越小，覆盖优先级越高。
4. Effective Pricelists 是否已经生成。
5. Customer Segments 是否正确。
6. 使用客户账号登录，检查商品可见性、价格、MOQ 和下单入口。

若添加公司专属价格表时出现：

`Configure a base pricelist for this customer type, website, and currency before adding a company override.`

表示该 Customer Type 尚未配置相同网站和币种的基础价格表。应先进入 `Configuration → Customer Types & Base Pricing` 完成基础价格映射，再添加公司覆盖。

## 10. 常见问题排查

### 10.1 Dashboard 没有待审核提醒

先检查申请是否仍为 `Verify Email`。只有客户验证邮箱并进入 `Partner Review` 后，Dashboard 才显示待审核数量。

### 10.2 客户无法登录

- `Verify Email` / `Email Link Expired`：账号尚未激活，应完成或重发邮箱验证。
- `Partner Review`：账号可以登录；若仍失败，检查密码和用户 Active 状态。
- 已批准仍无法登录：使用 Odoo 原生密码重置功能，不要重新创建重复用户。

### 10.3 客户登录后看不到价格

检查公司是否已审批、Customer Type 是否正确，以及该类型是否配置当前网站和币种的基础价格表。

### 10.4 发现重复公司

不要继续点击 `Create New Company`。返回申请改为 `Link Existing Company`，核实后关联已有公司。已错误创建的重复公司应由管理员按照 Odoo 联系人合并规范处理。

### 10.5 审核后公司关联错误

已批准的注册申请用于保留历史审核记录，不应直接篡改。由 B2B Manager 在 Contacts 核实并调整联系人归属，同时在 Chatter 留痕；必要时走 Company Change 流程。

### 10.6 客户资料需要补充

资料不完整时先填写明确的 `Rejection Reason` 并拒绝，或通过站内消息/邮件要求客户补充。收到资料后使用 `Return to Review` 重新审核。

## 11. 每日运营检查清单

1. 查看 Dashboard 的 `Pending Registrations`。
2. 优先处理已经验证邮箱且资料完整的申请。
3. 搜索并排除重复公司。
4. 核实 Business Type 与基础价格表。
5. 选择 `Link Existing Company` 或 `Create New Company`。
6. 批准前确认邮箱、公司、国家和联系人身份。
7. 批准后检查公司、联系人归属、Partner Hub 状态和 Effective Pricelists。
8. 重要判断和人工修正写入 Chatter。
9. 拒绝时填写客户能够理解的原因。

## 12. 验收检查

新版本上线后至少使用一个测试邮箱完整执行：

1. 注册页所有必填项校验正常。
2. 注册提交后账号不能在验证邮箱前登录。
3. 验证邮件链接可以打开且只能使用一次。
4. 验证后 Dashboard 出现 Pending Registration。
5. 普通 B2B Operator 无法批准。
6. B2B Manager 可以关联已有公司并批准。
7. B2B Manager 可以创建新公司并批准。
8. 已有公司资料不会被注册资料覆盖。
9. 新公司和个人联系人字段写入正确。
10. 客户登录后看到正确的审核状态、商品权限、价格和 MOQ。

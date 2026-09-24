# 第三方 AI 对话接口配置

## 第三方向量模型配置入口（待测试，未启用）

同一个 Providers 区域下新增 **Third-party Embeddings — Configuration**：

1. 勾选配置开关，填写 Embedding API Base URL（不带 `/embeddings`）和 Embedding Model Name。
2. 同供应商且同一 Key 有向量接口权限时，可勾选 **Use the third-party chat API key**；否则填写独立的 Embedding API Key。复用 Key 不代表 URL 和模型名可以省略。
3. **Target Vector Dimensions** 保持 1536，这是当前原生向量库的固定维度。供应商必须支持输出该维度，不可仅修改数字来转换向量。
4. **Send dimensions parameter** 默认开启；若模型固定输出 1536 维且接口不接受 dimensions，可关闭，后续实测确认。
5. 点击左上角 Save。保存只进行本地字段校验，不发起请求、不自动授权向量计费、不切换原生文档索引/查询、不重建旧向量。

填写后告知助手，再进行供应商连接、输出维度及入库/检索兼容性测试和激活适配。此阶段仅提供可保存的配置入口，不代表第三方向量通道已接通。

## 第三方对话配置

入口：Partner Hub AI → Native AI Settings → AI → Providers。

1. 启用 **Third-party AI (OpenAI-compatible)**。
2. **API Base URL** 填供应商的 API 根地址，例如 `https://api.example.com/v1`。保留供应商要求的 `/v1`，不要追加 `/chat/completions`；不接受网页聊天地址、内网地址、HTTP、URL 中的密码或查询参数。
3. **API Key** 填该供应商提供的 Key。与原生 OpenAI Key 分开保存；只有设置管理员可以配置，界面遮罩，不发送到客户浏览器。
4. **Model Name** 填供应商文档里的精确模型 ID，不是自取的显示名称。
5. **JSON Output Mode** 优先 Strict JSON Schema；供应商只支持 JSON Object 时选择兼容模式。不是所有自称 OpenAI-compatible 的服务都支持这些能力。
6. 可点击 **Test Connection** 并确认。仅发送无客户资料的小型 JSON 测试，可能计费；不会自动重复调用，也不自动切换模型或供应商。测试通过仅证明基础 JSON 对话能力，不代表四类业务质量全部验收。
7. 点击设置页面左上角 **Save**。单纯保存不发送模型请求。开关关闭后，网站助手恢复使用原生 OpenAI 配置。

## 范围及注意事项

- 此开关作用于本数据库 Partner Hub 网站客户助手的对话，未改造 Odoo 其他原生 AI 功能。
- 网站助手仍沿用原生 Agent 的系统提示、现有业务流程、商品/价格权限、输出检查和请求限额；第三方模型名来自新配置，不需要修改 Agent 的原生模型选项。
- 商品、FAQ 检索保持原逻辑；产品文档的索引及向量检索仍使用原生 OpenAI embedding，需要另保留原生 OpenAI Key。第三方聊天模型不能直接代替 embedding 模型，已有向量也不会被改变。
- 新 Key 保存时授权当前测试环境；复制出来的测试数据库仍须在 Website AI Configuration 中明确授权，不因复制配置就自动产生费用。
- 第三方接口会收到当前问题、必要的对话上下文，以及通过权限检查的相关产品/知识内容；请只填写你信任且允许处理这些资料的供应商。
- 仅允许公开 HTTPS 443 接口，调用前核验域名解析地址；禁止重定向，限制响应大小、连接等待和输出长度。不记录原始第三方错误或密钥。
- 未提供真实第三方 URL、模型和 Key 时，只能通过模拟接口验证功能，不能声称已验证某个供应商的真实连通性。

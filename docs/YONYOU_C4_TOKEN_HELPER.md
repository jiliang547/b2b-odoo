# 用友 C4 access_token 获取与刷新脚本

适用范围：当前 Windows 电脑上的本地开发和联调。脚本只调用用友认证接口，不操作客户、订单、生产、库存或财务数据。它尚未集成到 Odoo 定时任务，也不是 Odoo.sh 的线上凭据管理实现。

## 1. 日常使用

在 PowerShell 中先进入项目的 scripts 目录：

```powershell
cd 'C:\Users\JLZ\Documents\Codex\2026-08-13\chakna\work\b2b-odoo\scripts'
```

正常获取：有可用缓存就复用，否则访问 C4 获取。

```powershell
.\Get-YonyouAccessToken.ps1
```

强制重新向 C4 请求：

```powershell
.\Get-YonyouAccessToken.ps1 -ForceRefresh
```

默认只显示成功状态、来源、剩余秒数和到期时间，不打印完整 token。

如果另一个脚本需要使用 token，在变量中接收：

```powershell
$accessToken = .\Get-YonyouAccessToken.ps1 -PrintToken
# 强制刷新后接收：
$accessToken = .\Get-YonyouAccessToken.ps1 -ForceRefresh -PrintToken
```

只有明确使用 `-PrintToken` 或 `-JsonToken` 才输出完整 token；请勿将输出写入公共日志、聊天或 Git。请求业务接口时使用 URL 参数编码工具，token 可能包含特殊字符，不要直接拼接或重复编码。

只查看配置/缓存，不访问网络：

```powershell
.\Get-YonyouAccessToken.ps1 -Status
```

## 2. 第一次配置或更换密钥

```powershell
.\Get-YonyouAccessToken.ps1 -Configure
```

按提示输入 AppKey、AppSecret。AppSecret 隐藏输入，不作为命令行参数保存。重新配置会使旧缓存失效；下次获取会使用新密钥。配置命令本身不验证密钥，随后执行一次正常获取即可验证。

脚本会把配置和缓存保存在当前 Windows 用户的：

```text
%LOCALAPPDATA%\PartnerHub\YonyouC4Auth\
  credentials.dpapi   加密的 AppKey/AppSecret
  token.dpapi         加密的 token 和有效期
  refresh.lock        并发获取的进程锁
```

使用 Windows 原生 DPAPI 当前用户加密，目录权限限制为当前用户和 SYSTEM。这些文件不在项目或 Git 中，不应复制到服务器、另一台电脑或另一个 Windows 账号；换电脑/账号应重新配置。

`-CredentialsStdin` 是自动化配置入口，必须与 `-Configure` 一起使用，标准输入为包含 `appKey` 和 `appSecret` 的 JSON。不要把含密钥的 JSON 写进脚本或普通磁盘文件。通常人工使用交互配置即可。

## 3. 刷新规则

- 缓存剩余时间大于 5 分钟时复用。
- 没有缓存、缓存损坏、配置被更换、临近到期或明确强制刷新时重新请求。
- 以用友实际返回的 `expire` 秒数计算有效期；不假设每次都得到新的两小时。
- 用友可能返回同一个仍有效的 token，强制刷新不意味着一定换 token 或延长有效期。
- 若强制刷新仍返回不足 5 分钟的有效 token，本次可返回，但下一次调用还会请求 C4；不会循环刷新或伪造有效期。
- 请求失败不会覆盖之前的缓存，也不会把旧 token 冒充本次成功结果；脚本以错误状态退出。
- 并发正常获取使用进程锁，避免同时重复刷新；缓存先写临时文件再原子替换。
- 这是按需刷新，不会启动常驻服务或后台定时任务。

## 4. Python 调用

PowerShell 包装脚本优先使用本机已安装的 Odoo Python，没有第三方 Python 包依赖。也可直接执行：

```powershell
& 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe' .\yonyou_token.py
& 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe' .\yonyou_token.py --force-refresh
```

Python CLI 参数：`--configure`、`--credentials-stdin`、`--status`、`--force-refresh`、`--print-token`、`--json-token`。

如 Python 安装位置不同，可向 PowerShell 包装脚本传 `-PythonPath '实际路径'`。不需要管理员权限。如果电脑策略禁止执行 PowerShell 脚本，可直接调用 Python，不必修改全局执行策略。

## 5. 协议与验证

- C4 认证地址：`https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken`
- 业务网关：`https://c4.yonyoucloud.com/iuap-api-gateway`
- GET 请求；参数为 AppKey、毫秒时间戳、HMAC-SHA256 / Base64 签名；签名仅 URL 编码一次。
- 使用 HTTPS 证书校验，不跟随重定向；日志不输出密钥、签名、请求 URL 或完整服务端错误正文。
- token 获取成功不代表具体业务 API 已经授权。

协议依据：[用友企业自建应用获取 access_token](https://open.yonyoucloud.com/#/doc-center/docDes/doc?code=open_jrwd&section=022c941650ae4989af7dd6ac7fd4d412)。使用文档后半部分注明的新版 `base/v1` 路径。

离线测试命令（不访问用友，使用合成数据）：

```powershell
& 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe' -m unittest discover -s scripts -p test_yonyou_token.py -v
```

该测试命令在项目根目录运行。

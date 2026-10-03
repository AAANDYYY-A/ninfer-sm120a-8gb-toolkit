# 局域网对外服务 · 验证记录（2026-10-03）

> 本仓库是**公开**的，所以本文里的内网地址一律写成 `<你的内网IP>`、用户目录写成 `%USERPROFILE%`。
> 密钥（api-key.txt）**不在仓库里**，请勿提交。

## 做了什么

| 项 | 内容 |
|---|---|
| 启动器 | `start-ptq1-mtp-lan.bat`：相对 `start-ptq1-mtp-8gb.bat` **只差两处** —— `--host 0.0.0.0`、`--api-key`（从同目录 `api-key.txt` 读） |
| 密钥 | 48 字符随机串，存 `api-key.txt`；已加入 `.gitignore` |
| 客户端 | `chat-web.bat` / `chat-cli.bat` / `agent\agent.bat` 都会**自动回退读 `api-key.txt`**（优先 `NINFER_API_KEY` 环境变量） |
| 对端用的启动器 | `agent-lan.bat`：不写死任何地址，运行时询问 Base URL 与 key（因此可安全公开） |
| 防火墙 | 入站 TCP 8095 放行，所有配置文件 |

## 防火墙规则的证据（**无需提权**的读法）

`netsh advfirewall show rule` 与 `Get-NetFirewallRule` **都需要提权**，普通权限下会返回
`The requested operation requires elevation` —— 容易被误读成"规则不存在"。正确的只读验证途径是直接读注册表：

```powershell
$p='HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules'
(Get-ItemProperty $p).PSObject.Properties | Where-Object { $_.Value -match 'NInfer' } | ForEach-Object { $_.Value }
```

本机实测输出（原文）：

```
v2.33|Action=Allow|Active=TRUE|Dir=In|Protocol=6|LPort=8095|Name=NInfer 8095|
```

判读：`Action=Allow` 放行、`Active=TRUE` 已启用、`Dir=In` 入站、`Protocol=6` 即 TCP、`LPort=8095`、
**没有 Profile 字段 = 三个配置文件全适用**。

## 服务侧验证读数（本机实测）

```
无密钥           -> HTTP 401
密钥 + 回环      -> HTTP 200
密钥 + 内网地址  -> HTTP 200
真实对话请求     -> {"message":{"content":"收到"}}
x-api-key 头     -> HTTP 200        （引擎 bearer 与 x-api-key 两种都收）
本机聊天页       -> /health {"engine": true}；经代理真发一条回 "收到"
本机 agent       -> 经代理 1.2 s 回 "收到"
```

## 仍未验证（诚实标注）

**跨设备可达性**只能由那台设备来验：本机访问自己的内网地址不过入站过滤，所以"本机 <你的内网IP>:8095 返回 200"
只证明引擎绑到了 `0.0.0.0`，**不证明防火墙路径已通**。判据（在对端执行）：

```powershell
curl.exe -sS -o NUL -w "%{http_code}`n" http://<你的内网IP>:8095/v1/models
# 期望 401（不带 key）；带上 -H "Authorization: Bearer <key>" 后期望 200
```

## 风险边界（重申）

1. 引擎**无 TLS**：密钥与对话内容在局域网明文传输。**只用于可信网络，绝不做端口转发/暴露公网**。
2. 8 GB 卡**单实例**：远端与本机共用同一引擎，decode ≈ 60 tok/s，同时使用会互相排队。
3. `max_tokens` **必须 ≤ 4096**：直连 8095 时没有代理那层钳制，超了会踩手册 §1-11 的 worker 崩溃。
4. Radmin VPN 那种虚拟网卡常被判为 Public 网络，这也是防火墙规则用"所有配置文件"的原因。

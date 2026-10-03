# 在别的设备上部署这个模型（含"给别的设备的 AI agent 用"）

> 结论先说：**能不能搬，取决于那台设备的显卡**。这套引擎是按架构分别编译的，**不会回退** ——
> 包内说明原话："One binary per architecture … the wrong one does not fall back — it dies with no usable
> kernel image"。所以先看架构，再选下面四条路之一。

## 第 0 步：判架构（一条命令）

在那台设备上跑：

```powershell
nvidia-smi --query-gpu=name,compute_cap,memory.total,driver_version --format=csv
```

| 结果 | 走哪条路 |
|---|---|
| `compute_cap` = **8.6**（RTX 30 系）/ **8.9**（RTX 40 系）/ **12.0**（RTX 50 系） | **路径 A**：`.ninfer` + **对应架构的引擎包**（我们手里只有 sm_120a） |
| 非 NVIDIA（AMD / Intel / Apple），或纯 CPU，或架构对不上 | **路径 B**：改用 GGUF + Prism 的 llama.cpp |
| 懒得搬 8 GB 权重 / 只想让别的设备的 agent 用上 | **路径 C**：这台机器当服务器，别的设备连过来 |

---

## 路径 A：同架构 NVIDIA 卡（要搬 6.4 GB 模型 + 对应引擎包）

需要两件东西，**我们都没有**（得跟发布方取）：

| 件 | 大小 | 从哪来 |
|---|---|---|
| 模型包 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | 6,394,697,216 B | 发布方的 `modelpack-ptq1-20261002` |
| **对应架构**的引擎包 | ~1.9 GB | 发布方的 `infer-engine-sm86-20261002.zip` / `infer-engine-sm89-20261002.zip`；或三架构齐全的 `betakit-pq2-v2` / `betakit-ptq1-v2` 包 |

> 我们的私有仓库里**只有 sm_120a** 的引擎（Release `engine-sm120a-20261002`），**在那台设备上不能用**。

到位后在那边做的事：把模型放进 `models\`，双击本仓库的 `start-ptq1-mtp-8gb.bat`（若那台卡显存更大，
把 `--kv-capacity` 按教程 §5.2 往上调、并可去掉 `--no-cuda-graph` 换速度），然后 `chat-web.bat` / `agent\agent.bat`。

## 路径 B：非 NVIDIA / 其它平台（GGUF + Prism llama.cpp）

`.ninfer` 只有 NInfer 引擎能读，所以换**官方 GGUF** + **Prism 的 llama.cpp fork**：

| 件 | 大小 | 说明 |
|---|---|---|
| `Ternary-Bonsai-2-27B-PQ2_0.gguf` | 7.21 GB | 官方件（`prism-ml/Ternary-Bonsai-2-27B-gguf`） |
| 或 `Ternary-Bonsai-2-27B-PTQ1_0.gguf` | 5.95 GB | 显存紧时选它（8 GB 卡适用） |
| `llama-prism-b10743-...-win-cuda-12.4-x64.zip` | 245 MB | **必须**是 Prism 的构建：stock llama.cpp / Ollama / LM Studio **读不了** PQ2_0 / PTQ1_0 |
| `cudart-llama-bin-win-cuda-12.4-x64.zip` | 373 MB | 缺它会 `0xC0000135` |

本机 `D:\build\prism\` 就有这套（引擎 + PQ2_0 GGUF），当时实测 **decode 41.4 t/s / prefill 99.1 t/s**
（比同卡 ninfer 那代引擎的 4.8 t/s 快 8.6 倍）。启动参数（每个都是踩出来的）：

```
llama-server.exe -m Ternary-Bonsai-2-27B-PQ2_0.gguf -ngl 99 -c 8192 \
  -ctk q8_0 -ctv q8_0 -fa on -np 1 --host 127.0.0.1 --port 8096 --alias qwen3.8-27b
```

`llama-server` 同样是 **OpenAI 兼容 + 支持 tools**，所以本仓库的 `agent\agent-min.py`、`ninfer-chat.py`、
`chat-cli.bat` 可以直接指过去（见下面"客户端怎么指"）。

## 路径 C：这台机器当服务器（零搬运，最快）

引擎默认只绑 `127.0.0.1`。改动两处即可对外（**引擎支持 `--api-key`，务必设上**）：

```batch
REM 在 start-ptq1-mtp-8gb.bat 里，把这两行改掉：
--host 0.0.0.0 --api-key <一串随机字符>
```

```powershell
# 放行端口（管理员 PowerShell 执行一次）
New-NetFirewallRule -DisplayName "NInfer 8095" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 8095 -Profile Private
# 查本机内网地址
ipconfig | findstr /i "IPv4"
```

然后别的设备的 agent 填：`http://<这台机器的内网IP>:8095/v1`，API Key = 你设的那串。

**必须知道的三条代价**：① 引擎**没有 TLS**（HTTP 明文），只适合可信局域网；② 8 GB 卡**单实例**，
远端和本机会抢同一个引擎，且 decode ≈ 60 tok/s；③ 开着 `--api-key` 后，**本机自己的客户端也要带上**
（设 `NINFER_API_KEY` 即可，见下）。

## 客户端怎么指过去（本仓库所有工具都支持）

| 工具 | 环境变量（推荐） | 等价命令行参数 |
|---|---|---|
| `chat-web.bat`（网页） | `set NINFER_ENGINE=192.168.1.20:8095`<br>`set NINFER_API_KEY=...` | `ninfer-chat.py --engine HOST:PORT --api-key K` |
| `agent\agent.bat`（AI agent） | `set NINFER_BASE=http://192.168.1.20:8095/v1`<br>`set NINFER_API_KEY=...` | `agent-min.py --base URL --api-key K` |
| `chat-cli.bat`（终端） | `set NINFER_ENGINE=192.168.1.20:8095`<br>`set NINFER_API_KEY=...` | `ninfer-cli.py --engine HOST:PORT --api-key K` |
| 任意第三方 agent 客户端 | —— | Base URL `http://HOST:PORT/v1`，Key `K`，模型 `qwen3.8-27b` |

## 到位后的验收清单（别只看端口）

1. `/v1/models` 返回 200 **不等于**能服务（手册 §1-11：worker 崩了它照样 200）⇒ **真发一条请求**。
2. 起服务：控制台出现 `engine ready` 与 `capacity |` 两行。
3. KVMem：启动期有 `[ring] content scoring ON by default`；发过请求后有 `kvmem_score: SELECT` 行。
4. agent 场景：喂 `tools` 后应返回 `finish_reason=tool_calls`（本机已实测支持）。
5. `max_tokens` **不得超过池 token 数**（手册 §1-11；本机池 8192，所以上限 4096）。

## 要搬多少数据（备料清单）

| 路径 | 要搬的东西 | 合计 |
|---|---|---|
| A（同架构 NVIDIA） | `.ninfer` 6.4 GB + 对应引擎包 ~1.9 GB | **~8.3 GB** |
| B（其它平台 / GGUF） | GGUF 5.95–7.21 GB + llama.cpp 245 MB + cudart 373 MB | **~6.6–7.8 GB** |
| C（本机当服务器） | 什么都不用搬 | **0** |

> GitHub 单文件上限 100 MiB、Release 单资产 2 GiB ⇒ **权重只能走网盘/移动硬盘**（我们已把引擎
> sm_120a 放进私有仓库的 Release，但那对别的架构无用）。

---

# ★ 路径 C 已在本机实施（2026-10-03 实测记录）

## 做了什么

| 项 | 值 |
|---|---|
| 新启动器 | **`start-ptq1-mtp-lan.bat`**（与 `start-ptq1-mtp-8gb.bat` 只差两处：`--host 0.0.0.0`、`--api-key`） |
| 密钥 | `api-key.txt`（48 字符随机串，**已生成**；该文件已加入 `.gitignore`，不要提交、不要贴聊天里） |
| 本机内网地址 | **`<你的内网IP>:8095`**（以太网）。另有 Hyper-V `<Hyper-V地址>` 与 **Radmin VPN `<RadminVPN地址>`** —— 若对端不在同一局域网，可试 Radmin 这条虚拟网 |
| 监听 | `0.0.0.0:8095`（已从 `127.0.0.1` 改过来） |

## 端到端验证读数（全部实测）

```
无密钥           -> HTTP 401        （鉴权确实生效）
密钥 + 回环      -> HTTP 200
密钥 + 内网地址  -> HTTP 200
真实对话请求     -> {"message":{"content":"收到"}}   （走 http://<你的内网IP>:8095/v1）
x-api-key 头     -> HTTP 200        （引擎 bearer 与 x-api-key 两种都收）
本机聊天页       -> /health {"engine": true}；经代理真发一条也回"收到"
本机 agent       -> 经代理 1.2 s 回"收到"
```

## 对端（另一台设备）要做的三步

**1) 放行防火墙**（在**这台机器**上，用**管理员** PowerShell 跑一次 —— 我没权限建规则，这步必须你来）：

```powershell
New-NetFirewallRule -DisplayName "NInfer 8095" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 8095 -Profile Private
```

**2) 读出密钥**：打开 `start-ptq1-mtp-lan.bat` 同目录的 **`api-key.txt`**，复制里面那 48 个字符。

**3) 在对端的 AI agent 里填**：

| 字段 | 值 |
|---|---|
| Base URL / API 地址 | `http://<你的内网IP>:8095/v1` |
| API Key | `api-key.txt` 里的那串 |
| 模型名 | `qwen3.8-27b` |

**先用这条命令确认能不能通**（在对端执行，把 KEY 换成密钥）：

```powershell
curl.exe -sS -o NUL -w "%{http_code}`n" -H "Authorization: Bearer KEY" http://<你的内网IP>:8095/v1/models
# 期望 401（不带 KEY）与 200（带 KEY）
```

## 本机使用方式的变化（重要）

引擎现在**要求密钥**，所以本机客户端也要带。三个 `.bat` **已自动回退读取同目录的 `api-key.txt`**
（优先 `NINFER_API_KEY` 环境变量），双击即可，无需额外设置：

| 启动器 | 行为 |
|---|---|
| `chat-web.bat` | 读 `api-key.txt` 给代理，代理再带密钥访问引擎（实测 `/health` → `engine: true`） |
| `chat-cli.bat` / `agent\agent.bat` | 同上 |

## 三条必须记住的代价与风险

1. **无 TLS**：密钥与全部对话内容在局域网内明文传输。**只在你信任的网络里用**，**绝不要**做端口转发或暴露到公网。
2. **单实例 + 慢**：8 GB 卡同时只有一个引擎，远端与本机共用；decode ≈ 60 tok/s，两端同时用会互相排队。
3. **`max_tokens` 仍受池限制**：远端客户端若把 `max_tokens` 设成 32000（手册 §1-11 的崩溃配方），
   本机代理会钳到 4096 —— 但**直连 8095 时没有这层保护**，请让对端把上限设为 ≤ 4096。


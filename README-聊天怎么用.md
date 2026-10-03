# 怎么和它聊天（本机 · RTX 5060 8 GB · PTQ1_0 档 · 2026-10-03）

引擎只提供 OpenAI 兼容 API（`http://127.0.0.1:8095/v1`），**没有内置网页界面**（`GET /` → 404），
也**不发 CORS 头**（`OPTIONS` → 404）。所以本目录额外带了两个文件（都是新增，不改动包内任何原文件）：

| 文件 | 作用 |
|---|---|
| `ninfer-chat.py` | 本地聊天页 + **同源代理**（v2）：浏览器只跟它说话，它再去跟引擎说话（因此绕开 CORS），并把引擎的流式输出逐块转发；页面上有逐步诊断与 45 秒看门狗 |
| `chat-web.bat` | 双击即用：启动上面的服务并自动打开浏览器 |
| `ninfer-cli.py` + `chat-cli.bat` | 双击即用：**终端聊天**，完全不经浏览器（网页出问题时的兜底） |

## 一、两步开始聊

1. **先起引擎**：双击 `start-ptq1-mtp-8gb.bat` → 等控制台出现两行
   `INFO engine ready | bonsai2-27b …` 与 `INFO capacity | KV 8,192 tokens, k8v4, explicit …`
2. **再开聊天窗**：双击 `chat-web.bat` → 浏览器自动打开 **http://127.0.0.1:8097/**

> 那个最小化的 **“NInfer chat”** 窗口就是聊天页的服务进程：关掉它 = 关掉聊天页，**不影响引擎**。
> 引擎要单独关：关掉 `start-ptq1-mtp-8gb.bat` 那个控制台窗口。

## 一·五、网页不回复时（先做这三步）

聊天页顶部有一行 **“步骤日志”**，它会逐条写出：点击发送 → 发起请求 → 收到响应头 → 首字 → 完成。
只要看它停在哪一步，就能定位是谁的问题：

| 步骤日志停在 | 含义 | 怎么办 |
|---|---|---|
| 完全没变化，连“点击发送”都没有 | 页面脚本没收到你的点击 | 刷新页面（Ctrl+F5）拿到 v2；或直接改用下面的终端聊天 |
| “点击发送 … 按钮当前为禁用态，已忽略” | 上一次请求卡住了 | 刷新页面；v2 已加 45 秒看门狗不会再卡死 |
| “发起请求”后有红字/看门狗 45 秒中止 | 聊天页代理没在跑 | 关掉旧窗口，重新双击 `chat-web.bat` |
| 顶部状态灯是红色“引擎未启动” | 引擎没跑 | 双击 `start-ptq1-mtp-8gb.bat`，等 `engine ready` |

**兜底方案（完全不用浏览器）**：双击 **`chat-cli.bat`** —— 终端里直接聊天。
它绕过浏览器的一切（CORS、流式、扩展、缓存），直接跟 `127.0.0.1:8095` 说话；命令有
`/exit` `/clear` `/max N` `/temp F` `/system 文字`。**终端能用而网页不能用 ⇒ 问题一定在浏览器侧。**

### 已修 bug（2026-10-03，症状：消息发不出去、只看到自己的气泡）

页面脚本里曾用 `var history = []` 存对话历史。**`history` 是浏览器内置的只读属性**
（`window.history`，History API），全局 `var` 声明覆盖不了它，赋值静默失败 —— 于是
`history.push(...)` 抛 `history.push is not a function`，而 v1 没有全局错误处理，异常无声逃逸，
表现为"自己的消息出现了，但永远没有回复，且请求根本没发出去"。
现已改名为 `msgs`，并加了 `window.onerror` / `unhandledrejection` 横幅，任何脚本异常都会显示在页面上。
排查时的对照实验（Node + 只读 `history`）：

```
OLD (var history = []): THROWS -> history.push is not a function
NEW (var msgs = [])   : OK
```

---

## 六、按《04-卡死与循环的防治》做的改造（2026-10-03）

手册是**单独投递**的（本机路径 `D:\DOWNLOADS\04-卡死与循环的防治.md`），不随任何包发。本包据此改了三处。

### 6.1 `max_tokens` 必须不高于池 token 数（手册 §1-11 + L1）

手册 §1 第 11 条（`ENGINE_DEAD`）写明：客户端 `max_tokens`（实测 32,000）**远大于池 token 数**时，
输出租约拿不到页 ⇒ worker 崩（日志签名 `Paged KV reservation invariant was violated`），
**而 `/v1/models` 照样返回 200 —— 健康检查骗人**。

本机池只有 **8,192**，而原 argv 是 `--default-max-tokens 32768`、聊天页输入框也开到 32768 ⇒ **正踩在这条上**。已改：

| 位置 | 改法 |
|---|---|
| 启动器 argv | `--default-max-tokens 32768` → **4096**（池的一半，给题面留驻留空间） |
| 聊天页输入框 | `max` 从 32768 → **4096**；超了当场钳制并在"步骤日志"里写出来 |
| 代理 | 客户端请求 `max_tokens > 4096` 一律**钳制并记日志**（`CLAMP ...`），`/stats` 里 `clamped` 计数 |

**实测**：故意发 `max_tokens: 32768` ⇒ 代理钳到 4096、请求正常返回、**引擎随后仍 200（没崩）**。

### 6.2 L3 交付护栏（手册 §3-L3：唯一能在"模型侧无信号"时拦住的一层）

手册要求：**判完整响应**（不是流中途），判定失败 ⇒ **在同一次调用里带纠正指令重发**，上限 2 次。
已在代理里实现：

| 状态 | 判据 | 本机默认 |
|---|---|---|
| `TRUNCATED` | `finish_reason=length`，或 ``` 围栏计数为奇数，或有 `<svg>` 无 `</svg>` | **开** |
| `FIXED_POINT` | 归一化空白后与上一轮答案逐字相同（取请求里最后一条 assistant 消息） | **开** |
| `EMPTY` | 正文短于阈值 | **默认关**（`--guard-empty-min 0`）：手册的 400 字阈值会把"收到"这类短回复误判 |
| `SAME_PLAN` / `SHELL_LOOP` | 计划行重复 / 纯 toolCall 无正文 | 本聊天页不涉及工具，未启用 |

- **动作**：判定失败 ⇒ 在**同一条响应流里**追加标记 `[交付检查未通过：<状态> · 第 N 次重试]` + 手册的纠正文案，然后重发；上限 2 次仍失败则记 `undelivered_final`（**不许当成功**）。
- **三个计数**（手册 §3"接收方要实现什么"要求）：`guard_fired` / `rescued_by_retry` / `undelivered_final` ⇒ **http://127.0.0.1:8097/stats**
- **关闸开关**：`--guard off` ⇒ 行为逐字回到未加护栏（手册要求的 `off` 开关）
- **实测**（`max_tokens=16` 故意截断）：护栏连续重试 2 次 ⇒ `guard_fired=3, undelivered_final=1`；正常请求不触发 ✓
- ⚠️ **踩过的坑**：代理一度把引擎的终端帧 `data: [DONE]` 原样转发，客户端一看到 `[DONE]` 就断开，
  于是"重发"永远送不达（日志里只有 `CLIENT-DISCONNECT`、没有 `GUARD fired`）。现在 `[DONE]` **由代理在所有尝试之后才发一次**。

### 6.3 手册 F1–F5 在本机的状态

| 手册条目 | 本机现状 |
|---|---|
| **F1 不回灌上一轮推理** | ✅ 引擎默认关思考（`--default-reasoning-effort none`），聊天页从不回传 `reasoning_content` |
| **F2 加交付护栏** | ✅ 见 6.2（本次加入） |
| **F3 `max_tokens` 给足** | ⚠️ 本机上限 4096（池的一半）。若产物被截断，护栏会判 `TRUNCATED` 并提示 —— 这是"池只有 8192"下的取舍 |
| **F4 思考通道补重复惩罚** | ➖ 不适用（默认关思考）；手册对工具/结构场景建议 `presence=0`，本机 argv 正是 `--presence-penalty 0` |
| **F5 降 effort / 关思考** | ✅ 已是启动器默认 |

> **诚实边界**：手册 §1-11 指出的是"客户端把 `max_tokens` 开得远超池"这条**我们确实踩着**的风险，已修；
> 但它**不是**本机那次"引擎静默消失"的已证原因 —— 那次的现象是整个监听端口消失，且**没有**手册记载的
> `Paged KV reservation invariant was violated` 签名。那次死亡仍未定位（见部署回执）。



## 二、聊天页上的东西

- **输入框**：`Enter` 发送，`Shift+Enter` 换行
- **回答上限**：默认 `1024` token。注意换算：**1000 token ≈ 250 个数字**（数数字语料）；要长回答就调大，最大 32768
- **温度**：默认 `0.7`（与启动器默认一致）；想要确定性输出填 `0`
- **停止**：正在生成时可以中断（已收到的内容会保留在对话历史里）
- **清空对话**：清掉本地历史（引擎本身无状态，历史每轮由浏览器整段发过去）
- 顶部状态灯每 15 秒自检一次：绿 = 引擎就绪，红 = 引擎没在跑（去双击 `start-ptq1-mtp-8gb.bat`）

## 三、不想用这个页面？换别的客户端都行（同一个引擎）

| 方式 | 怎么填 |
|---|---|
| **任意 OpenAI 兼容客户端**（Chatbox / Cherry Studio / NextChat…） | Base URL `http://127.0.0.1:8095/v1`，API Key 随便填（`auth disabled`），模型 `qwen3.8-27b` |
| **SillyTavern**（本机已装：`D:\SillyTavern Launcher GUI`） | API 选 *Custom (OpenAI-compatible)*，地址同上。它由服务端转发请求，所以**没有 CORS 问题** |
| **命令行 curl** | 见下方；注意 `Content-Type: application/json` 且请求体存成 **UTF-8** 文件 |
| **Python** | 见下方（本机可用 `%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`） |

```powershell
# curl：请求体必须用 UTF-8 写，别用 -Encoding ascii（中文会被烧成乱码）
$body = '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"用一句话介绍你自己"}],"temperature":0.7,"max_tokens":256}'
[System.IO.File]::WriteAllText("$env:TEMP\ask.json", $body, [System.Text.UTF8Encoding]::new($false))
curl.exe -sS -H "Content-Type: application/json" --data-binary "@$env:TEMP\ask.json" http://127.0.0.1:8095/v1/chat/completions
```

```python
import json, urllib.request
body = {"model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "用一句话介绍你自己"}],
        "temperature": 0.7, "max_tokens": 256}
req = urllib.request.Request("http://127.0.0.1:8095/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
print(json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"])
```

加 `"stream": true` 就是 SSE 流式（帧格式 `data: {...}`，以 `data: [DONE]` 收尾）。

## 四、本机实测速度（数数字语料，1,000 进 / 1,000 出）

`prefill ≈ 480–570 tok/s · decode ≈ 55–60 tok/s · TTFT ≈ 2 s · 1,000 token 约 19 s`

- 短问题基本"秒回"：3 个汉字的回答约 0.4 s 出第一块
- 这个速度**比包内构建机（RTX 4080 SUPER，decode 196.8 tok/s）慢约 3.3 倍**，主要原因：
  本卡带宽 448 GB/s（4080S 是 736）、本档为了装进 8 GB 显存**关了 CUDA Graph**、设备池 8192 而非 17920
- 想提速可试的只有：`--draft-tokens`（仅对可预测文本有效）、或换更大显存的卡

## 五、注意事项（都踩过）

1. **单实例**：这张 8 GB 卡同时只能跑一个引擎。别同时开 `start-pq2*.bat`、也别同时开本机另一条
   Prism llama.cpp 路线（端口 8096）——第二个实例会被 WDDM "加载成功"然后崩。
2. **中文没问题**（已实测：问"中华人民共和国的首都是哪里" → 答"中华人民共和国的首都是北京。"）。
   但**写请求体时务必 UTF-8**；用 PowerShell `Set-Content -Encoding ascii` 写含中文的 body 会变成乱码，
   模型会以为你的问题是坏数据。
3. **上下文**：引擎声明 `n_ctx = 262144`，但**设备池只有 8,192 token**，其余靠 KVMem 放在 16 GiB 主机池里
   按需搬回。所以长题面/多轮对话**理论可用但本机未测**（教程 §0.4 明令不做穷举式长测）。
4. **答案被截断**时 `finish_reason` 会是 `length`（不是丢上下文）：把"回答上限"调大即可。
5. 引擎默认**关闭思考**（`--default-reasoning-effort none`），这是启动器故意设的；别在客户端另开。

---

## 七、让它在 AI agent 里跑（工具调用）

**门槛已实测通过**（2026-10-03，直连 `8095`）：喂 `tools` 后引擎返回

```
finish_reason : tool_calls
tool_calls    : [{"function":{"arguments":"{}","name":"get_time"},"id":"call_…","type":"function"}]
```

即它**能**当 agent 的"大脑"。三种接法：

### 7.1 本机自带的最小 agent（开箱即用）

双击 **`agent\agent.bat`**（需先起引擎）。输入任务 → 模型自己决定调工具 → 执行 → 收尾给结论。

- 工具：`get_time` / `list_dir` / `read_file` / `write_file`（**故意没有 shell 工具**）
- 文件工具**限制在** `agent\agent-work\` 沙箱内，绝对路径与 `..` 越界一律拒绝
- 护栏（按手册 §1 第 6 条与 §9）：最多 6 步；连续"只调工具不给正文"超过 3 轮判 `SHELL_LOOP` 中止；
  同一工具同一参数重复超过 2 次拒绝执行并追加纠正；每轮 `max_tokens` 默认 1024
- 每轮写一行 JSONL（`agent-work\agent-run.jsonl`），字段对齐手册 §9：
  `turn / finish_reason / text_chars / tool_calls / wall_s`

**实测任务**「现在几点？然后在工作目录里创建 hello.txt，内容写当前时间」：

```
[step 1 · 1.5s · finish=tool_calls]  -> get_time {}       → 2026-10-03 14:06:36 Saturday
[step 2 · 1.2s · finish=tool_calls]  -> write_file {...}  → 已写入 hello.txt（19 字节）
[step 3 · 1.6s · finish=stop]        正文：现在时间…已在工作目录创建 hello.txt…
=== 结论（4.2s，3 步）===
```
落盘已核：`agent-work\hello.txt` = `2026-10-03 14:06:36`。

### 7.2 任何 OpenAI 兼容的 agent 客户端

| 填什么 | 值 |
|---|---|
| Base URL | `http://127.0.0.1:8095/v1`（直连引擎）或 `http://127.0.0.1:8097/v1`（**经护栏与钳制**） |
| API Key | 随便填（`auth disabled`） |
| Model | `qwen3.8-27b` |
| 工具 | 支持 `tools` / `tool_choice`；代理已透传，`tool_calls` 原样返回 |

> ⚠️ 客户端若把 `max_tokens` 设很大（如 32000）：走 8097 会被**钳到 4096**（手册 §1-11 的崩溃配方）；
> 直连 8095 则由 `--default-max-tokens 4096` 兜住（前提是客户端不显式覆盖）。

### 7.3 手工验证工具调用（curl 片段）

```powershell
$body = @'
{"model":"qwen3.8-27b","messages":[{"role":"user","content":"现在几点？必须调用工具"}],
 "tools":[{"type":"function","function":{"name":"get_time","description":"返回当前时间",
 "parameters":{"type":"object","properties":{},"required":[]}}}],"tool_choice":"auto","max_tokens":200}
'@
[System.IO.File]::WriteAllText("$env:TEMP\tc.json", $body, [System.Text.UTF8Encoding]::new($false))
curl.exe -sS -H "Content-Type: application/json" --data-binary "@$env:TEMP\tc.json" `
  http://127.0.0.1:8095/v1/chat/completions
```

### 7.4 能力边界（手册结论 + 本机实测，别高估）

| 事实 | 含义 |
|---|---|
| 手册 §6 内测结论：「**一次性手脚（单步工具调用 + 收尾可用），多步 agent 活不可用**」 | 1–3 步的任务能干；长链多步别指望 |
| 本机 decode ≈ **60 tok/s**、每轮输出 ≤ **4096** token、**单实例**、显存余量 ≈ 200 MiB | 多步循环慢；每次工具往返都要重新 prefill |
| 手册 §1 第 6 条 `SHELL_LOOP`、第 12 条工具名漂移 | `SHELL_LOOP` 与重复调用已在 `agent-min.py` 里拦截 |
| 本机**没有** shell 工具 | 安全选择；要加就等于接受任意命令执行，请自行权衡 |

代理为支持 agent 做的三处修复（均已实测）：① `tools`/`tool_choice` **透传**；② 非流式响应**原样返回引擎 JSON**
（此前重建会丢掉 `tool_calls`）；③ `finish_reason=tool_calls` 的轮次**不再被判 `EMPTY`**（否则护栏会把正常的
工具轮当失败"纠正"掉）。

---
*本说明由部署 agent 生成，所有读数均为本机实测；`ninfer-chat.py` / `chat-web.bat` / `agent\*` / `usage*` 为新增文件，包内原文件零改动。*

---

## 八、查看 API 调用量（用量看板）

双击 **`usage.bat`** → 浏览器打开 **http://127.0.0.1:8098/**（看板本身只占一个进程；关掉它的窗口不影响引擎）。
它**不猜、不估算**：数字全部来自引擎自己的两类机器可读输出。

### 数据来源（由 `start-ptq1-mtp-lan.bat` 开启）

| 来源 | 由哪个参数产生 | 内容 |
|---|---|---|
| `logs\requests.jsonl` | `--request-log-jsonl` | **每条请求一条全精度记录**：`result`（输入/输出/实际 prefill/前缀缓存命中 token、finish_reason、工具调用数）、`timings_seconds`（ttft / prefill / decode / total）、`speculative`（MTP 草稿数与接受数）、`server_start`（硬件与配置快照） |
| `http://127.0.0.1:8099` | `--stats-port 8099` | `/v1/load` 实时负载（KV 页占用、运行/排队、uptime）、`/metrics` Prometheus 累计计数、`/stats`、`/health`（**同样受 API key 保护**，无密钥返回 401） |

### 页面上有什么

- **八张大卡**：总请求数 · 输入 token（含缓存命中）· 输出 token（含实际 prefill）· 平均与最近 TTFT · 平均与最近 decode tok/s · 平均 prefill tok/s · 投机接受率 · 工具调用数
- **两张柱状图**：最近 24 小时「每小时请求数」与「每小时 token 数（蓝=输入 绿=输出）」
- **实时负载面板**：运行中/排队、已准入/峰值、设备 KV 页占用（x/y 页、token 数）、主机 KV 已用、已解码与已 prefill 计数、启动时长
- **累计计数面板**：`nimfer:requests_total`、`llamacpp:prompt_tokens_total`、`tokens_predicted_total`、`kv_cache_usage_ratio`、`ninfer:prefix_cache_hit_tokens_total` 等 10 项
- **最近请求明细表**：时间、#、协议、是否流式、输入/输出 token、缓存命中、TTFT、prefill tok/s、decode tok/s、投机（接受/草稿）、结束原因、工具调用

每 5 秒自动刷新；页面无任何外部依赖（图表是内联 SVG 画的）。

### 本机首次实测读数（4 条请求）

```
请求数 4 · 输入 81 token · 输出 108 token · 实际 prefill 71 · 前缀缓存命中 10
平均 TTFT 0.307 s · 平均 decode 53.9 tok/s · 平均 prefill 64 tok/s
投机解码 草稿 96 / 接受 84 = 87.5%（MTP，draft-tokens 4）
```

### 注意

1. 看板读的是**日志文件 + 统计口**，所以引擎必须是用 `start-ptq1-mtp-lan.bat` 起的（它带了那两个参数）；
   若你用的是 `start-ptq1-mtp-8gb.bat`，则没有 `logs\requests.jsonl`，看板会提示日志不存在。
2. 日志会一直增长：需要时用 `--request-log-max-mib`（引擎参数）做轮转，或直接删掉旧文件
   （看板检测到文件变小会自动从头重读）。
3. 统计口 `8099` 也绑在 `0.0.0.0`（与引擎同一进程），**它同样需要 API key**；不要把 8099 单独暴露出去。
4. 本机实测：加上 `--stats-port` 与请求日志后，显存占用没有增加（引擎仍是 7.6 GiB 级），启动 4 s。


# 《04-卡死与循环的防治》落地记录 · 本机（RTX 5060 8 GB · PTQ1_0 档）

- 手册来源：`D:\DOWNLOADS\04-卡死与循环的防治.md`（**单独投递、不随任何分发包**）
- 处置：按手册首页自己的要求，已放进本包 `docs\04-卡死与循环的防治.md` 当补充页
- 本记录只写**本机做了什么、读数是什么、哪些没做**；不改变手册本身的判据

## 1. 手册哪里直接命中了我们（最重要的一条）

**§1 第 11 条 `ENGINE_DEAD` + L1 处方：`max_tokens` 必须不高于池 token 数。**

| 手册原文口径 | 本机状态（改造前） |
|---|---|
| 客户端 `max_tokens` 32,000 ⇒ 输出租约拿不到页 ⇒ worker 崩，日志签名 `Paged KV reservation invariant was violated`，**而 `/v1/models` 仍 200** | 池 = `--kv-capacity 8192`；而 argv 是 `--default-max-tokens 32768`，聊天页输入框 `max=32768` ⇒ **正好踩着这条** |

**已改（三处，互为冗余）**

| 位置 | 改动 | 文件 |
|---|---|---|
| 引擎 argv | `--default-max-tokens 32768` → **4096** | `start-ptq1-mtp-8gb.bat` |
| 聊天页 | 输入框 `max` 32768 → **4096**，超出时当场钳制并在"步骤日志"里写明 | `ninfer-chat.py` 内嵌页面 |
| 代理 | 任何客户端 `max_tokens > 4096` ⇒ 钳制 + 日志 `CLAMP ...`，计数见 `/stats` 的 `clamped` | `ninfer-chat.py` |

**实测证据**

```
$ curl -X POST http://127.0.0.1:8097/api/chat -d '{"messages":[...],"max_tokens":32768}'
  → 代理日志: CLAMP max_tokens 32768 -> 4096 (pool 8192; doc §1-11 crash recipe)
  → 请求正常返回；随后对引擎直接发请求仍 200（引擎未崩）
  → /stats: {"clamped": 1, ...}
```

## 2. L3 交付护栏（手册 §3，本机从无到有）

手册判据 → 本机实现（`ninfer-chat.py`）：

| 手册状态 | 判据 | 本机 | 说明 |
|---|---|---|---|
| `TRUNCATED` | `finish_reason=length` / 围栏奇数 / `<svg>` 无 `</svg>` | **开** | 三种判据全实现 |
| `FIXED_POINT` | 与上一轮答案归一化空白后逐字相同 | **开** | 上一轮答案 = 请求里最后一条 assistant 消息，无需客户端额外配合 |
| `EMPTY` | 正文 < 阈值（手册举例 400 字） | **默认关** | 400 字会把"收到"这类短回复误判；`--guard-empty-min N` 可开 |
| `SAME_PLAN` / `SHELL_LOOP` | 计划行重复 / 纯 toolCall 无正文 | 未启用 | 本聊天页不涉及工具调用 |

**动作**：与手册一致 —— 在**同一条响应流内**追加标记 + 纠正文案后重发，上限 `--guard-retries 2`；
仍失败则记 `undelivered_final`（不当成功）。**关闸**：`--guard off`。

**实测证据**（故意用 `max_tokens=16` 造成截断）：

```
1 2 3 4 5 6 7 8
[交付检查未通过：TRUNCATED · 第 1 次重试]
1 2 3 4 5 6 7 8
[交付检查未通过：TRUNCATED · 第 2 次重试]
1 2 3 4 5 6 7 8
[交付检查未通过 · TRUNCATED · 已重试 2 次]

$ curl http://127.0.0.1:8097/stats
{ "requests": 2, "guard_fired": 3, "rescued_by_retry": 0, "undelivered_final": 1, "clamped": 0 }
```

对照：正常请求（`max_tokens=120`）**不触发**护栏 ✓。
`undelivered_final` 能取到非 0 ⇒ 满足手册"计数必须能变红"的要求。

**过程中踩到并修掉的一个坑（供后来者）**：代理一度把引擎的终端帧 `data: [DONE]` 原样转发，
客户端（含我的测试脚本）一看到 `[DONE]` 就结束读取并断开，于是**护栏的重发永远送不达**——
日志里只有 `CLIENT-DISCONNECT`、没有 `GUARD fired`，现象是"护栏像没生效"。
正确做法：**`[DONE]` 由代理在所有尝试结束后只发一次**；转发期间丢弃引擎的 `[DONE]`。

## 3. 手册 F1–F5 对照表

| 手册条目 | 本机 | 依据 |
|---|---|---|
| **F1 不回灌上一轮推理** | ✅ 已满足 | 引擎默认关思考（`--default-reasoning-effort none`）；聊天页只发 `role/content`，从不带 `reasoning_content` |
| **F2 加交付护栏** | ✅ 本次加入 | 见 §2 |
| **F3 `max_tokens` ≥ 思考 + 交付物** | ⚠️ 有取舍 | 本机池 8192 ⇒ 上限 4096；被截断时护栏判 `TRUNCATED` 并重发。要更长产物须先把池调大（8 GB 卡上受限） |
| **F4 思考通道补重复惩罚** | ➖ 不适用 | 默认关思考；手册对工具/结构化场景建议 `presence=0`，本机 argv 正是 `--presence-penalty 0` |
| **F5 降 effort / 关思考** | ✅ 已满足 | 启动器默认 `--default-reasoning-effort none` |
| **§4 平台守卫（DSH loop guard）** | 📌 仅登记 | 手册记本机 DSH 为 `action=notice`、`trips=0`；本次未改动 DSH 侧任何配置 |
| **§7 社区技巧 1（禁止回灌 reasoning）** | ✅ 同 F1 | —— |
| **§7 社区技巧 2（maintainer 采样配方 presence 1.5）** | ➖ 未采用 | 该配方针对**思考档**；本机默认关思考，且手册同页提示高 presence 会与工具/结构输出打架 |

## 4. 未做 / 未定位（诚实清单）

1. **本次未跑手册 §9 的"10 轮基线 JSONL 剧本"**。手册 §9 第一步要求先量基线（五态计数 + `undelivered_final`），
   再决定是否改配置。本机的改造属于**手册 L1 明文规则 + L3 兜底层**（不依赖基线即可判定其必要性：
   `max_tokens 32768 > 池 8192` 是规则违反；护栏是"没有就补"），但**基线读数仍然缺**，属于未做项。
2. **那次"引擎静默消失"仍未定位**，且**不应当归因于 §1-11**：手册第 11 条的症状是
   "请求全 503、`/v1/models` 仍 200、日志有 `Paged KV reservation invariant was violated`"；
   本机那次是**整个监听端口消失**（连接被拒）、无 FATAL 行、无该日志签名、无崩溃转储、无 WER 事件。
   两者现象不同 ⇒ 只能说"我们另有一条被手册点名、且确实踩着的风险，已修"，不能说"死因已查明"。
3. **手册 §5.5 Swift 档、§7 的窗口化惩罚、§8 的假想实验**均未做（未验项就该标未验）。
4. **`--default-thinking-budget` 未使用**（本机默认关思考，不需要）。

## 5. 复现命令（本机可直接跑）

```powershell
# 1) 池 vs max_tokens 规则：故意超出，看代理钳制
curl.exe -sS -H "Content-Type: application/json" `
  --data-binary '{\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"max_tokens\":32768}' `
  http://127.0.0.1:8097/api/chat > $null
curl.exe -sS http://127.0.0.1:8097/stats      # clamped 应 +1

# 2) 护栏：故意截断（finish_reason=length）
#    用 max_tokens=16 发一条长回答请求，响应流里应出现 [交付检查未通过：TRUNCATED · 第 N 次重试]
#    随后 /stats 的 guard_fired / undelivered_final 应增长

# 3) 关闸（行为必须逐字回到未加护栏）
#    重新起代理时加 --guard off
```

---
*本记录由部署 agent 生成：每条改动都附了判据与读数；未做的动作显式标注为未做。*

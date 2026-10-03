# 部署回执 · NInfer sm_120a 引擎包 · RTX 5060 8 GB（PTQ1_0 档）· 2026-10-03

- 包路径：`D:\AI-FAST\infer-engine-sm120a-20261002`
- 状态：**已部署并通过短测**（引擎 `engine ready` + `capacity |`；KVMem 两行证据齐；一条数数字测速完成）
- 服务地址：`http://127.0.0.1:8095`（`/v1/models` 返回 `status:"loaded"`）
- 包完整性：`verify-kit-manifest.ps1 -Kit .` = **`ok=18 mismatch=0 missing=0`**（新增文件不在清单内，原文件零改动：
  `start-ptq1-mtp.bat` 实测 sha256 `99ECBA4AFAC66A1473108D1652E1E4173B60E6548560F76D73AFC24C829F837C`，与清单第 15 行逐字一致）

---

## 1. 交付物与用法

| 路径 | 说明 |
|---|---|
| `models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | 模型权重，6,394,697,216 B（= 教程 §0.0 PTQ1 条目口径）；sha256 `5C4486C8A52687E3F62072C7DD2A320546D0E00D1C019BF137EB02CC944E21B8`（源文件与落地后**逐字相同**） |
| `start-ptq1-mtp-8gb.bat` | **新增**的 8 GB 卡启动入口（作业 agent 添加；包内原文件未动）。头注释里写全了每个改动的引擎原始数字 |
| `start-ptq1-mtp.bat` | 包内原启动器，**保持原样**；在本卡上必然 FATAL（见 §4） |

**起服务**：双击 `D:\AI-FAST\infer-engine-sm120a-20261002\start-ptq1-mtp-8gb.bat` → 等两行
`engine ready` 与 `capacity |`。**停服务**：关掉那个控制台窗口（或 `taskkill /IM ninfer-serve-120a.exe /F`）。
**单实例铁律**：8 GB 卡同时只能跑一个引擎实例（第二个会被 WDDM 超额承诺"加载成功"再崩，10-01 实测）；
本卡的 ninfer 路线（8095）与本机已有的 Prism llama.cpp 路线（8096）也互斥。

## 2. 本机事实

| 项 | 值 |
|---|---|
| GPU | NVIDIA GeForce RTX 5060，8151 MiB，驱动 <驱动版本>（CUDA 13.1），**compute cap 12.0**（= 本包 `sm_120a` 目标卡） |
| 引擎 | `engine\ninfer-serve-120a.exe`，1,329,240,576 B，sha256 `E3E0486A5B78DFC9CB2FE146FF9FE63433E1E52FC54B7CED8888EE54EE1F7BB3`（与清单一致） |
| 运行时标定 | 本 build 会**运行时标定**本卡：`calibrating routes for nvidia-geforce-rtx-5060-sm120 (30 SMs)` → `51 routed keys`，缓存在 `%LOCALAPPDATA%\ninfer\device-profiles.json`（`origin: calibration`），**只付一次约 70 s**，之后启动总耗时 ~3.7 s |

## 3. 最终配置（8 GB 档）与引擎给出的每一个数字

相对包内 `start-ptq1-mtp.bat` 的**全部**改动（其余 argv 与环境变量逐字相同）：

| # | 改动 | 依据（引擎原文数字，全部本机实测） |
|---|---|---|
| 1 | `--kv-capacity` 17920 → **8192** | 教程 §5.2 授权的池旋钮；实测斜率 27,336 B/token，8192 留约 195 MB 余量 |
| 2 | 增加 `--no-cuda-graph` | 这是**唯一**能消掉那个池无关固定项的手段 |
| 3 | 增加端口守卫（防第二实例） | 8 GB 卡第二实例必崩（10-01 实测） |

隔离实验表（每行只改一个旋钮，其余逐字等同原启动器）：

| 配置 | 引擎要求 (B) | 当时可用 (B) | 结果 |
|---|---|---|---|
| 原样 argv（17920 / 16384 / 262144） | `1,863,978,752` | `817,598,464` | FATAL |
| `--kv-capacity 7168` | `1,570,062,080` | `639,004,672` | FATAL |
| 7168 + `--host-kv-mib 1024` | `1,570,062,080` | `694,345,728` | FATAL（与上一行**逐字节相同**） |
| 7168 + host1024 + `--max-context 32768` | `1,570,033,408` | `641,953,792` | FATAL（只差 28,672 B） |
| 原样池数 + **`--no-cuda-graph`** | `1,010,437,888` | `940,736,512` | 差 66.5 MiB |
| 原样池数 + `--no-cuda-graph`（桌面几乎全空时重试） | `1,863,978,752` | `941,719,552` | FATAL（*这是原样 argv 的重试*） |
| **`--kv-capacity 8192` + `--no-cuda-graph`** | **710.0 MiB（启动成功）** | `941,719,552` | **READY** |

**回归结论**：`预留 ≈ 1,374,117,632 B（池无关固定项）+ 27,336 B × 池`，固定项主体是 CUDA Graph（814 MiB）。
`--host-kv-mib` 完全不影响该预留；`--max-context` 缩到 1/8 只影响 28,672 B。
⇒ **只调池（§5.2 明文的两项 + §2 的第三项）在本卡上无解**；这是本次最该回报给发布方的技术结论。

## 4. 原样 argv 为何必失败（可直接引用的证据）

即使把桌面占用压到 **467 MiB**（空闲 7429 MiB），原样 argv 仍然被拒：

```
2026-10-03 12:35:32.156  FATAL server failed during startup | requested Engine runtime reservation
  requires 1863978752 bytes, but only 941719552 bytes are available for runtime capacity
```

且可用的 0.9 GiB **不随桌面释放而增长**（桌面 1730 MiB 时可用 817,598,464；桌面 467 MiB 时可用 941,719,552）
⇒ 不是"被桌面挤占"，是引擎口径下的硬上限。

## 5. 短测读数（§0.2 口径：数数字语料，1,000 进 / 1,000 出，`temperature=0`）

**两次独立运行**（不同实例，同一 argv），可复现：

| 读数 | run #1 | run #2（交付入口） | 包内构建机基准（RTX 4080 SUPER / sm_89 / 池 17920） |
|---|---|---|---|
| prompt | 1,133 | 1,133 | 1,133 |
| output | 1,000（`finish_reason=length`，正常） | 1,000 | 1,000 |
| TTFT | 2.4 s | **2.0 s** | 565 ms |
| prefill | 481.2 tok/s | **570.1 tok/s** | 2.01k tok/s |
| decode | 59.0 tok/s | **60.3 tok/s** | 196.8 tok/s |
| total | 19.3 s | **18.6 s** | 5.7 s |
| mtp accepted | 780/875 (89.1%) | 780/875 (89.1%) | 88.1% |
| 答案 | `301 302 303 …` 连续正确 | 同左 | 同左 |

run #2 引擎原文（权威读数）：

```
req#1 done | openai-chat | output limit | prompt 1,133 | output 1,000 | cache 0 (0.0%) |
  TTFT 2.0s | total 18.6s | queue 10.7 ms | prefill 570.1 tok/s | decode 60.3 tok/s | mtp accepted 780/875 (89.1%)
```

**关于 §0.2 的"3 倍"触发线（诚实写法）**：decode 60.3 vs 196.8 = **3.3× 慢**，prefill 570 vs 2.01k = **3.5× 慢**，
已越过"差 3 倍以上按 §6 第 3 类上报"的线，故本回执按该类别准备。**但我没有把根因定位**，只能列出可核对的因素：
① 本卡带宽 448 GB/s vs 4080S 736 GB/s（1.64×）；② 本档**关了 CUDA Graph**（为了装得下）；
③ 设备池 8192 vs 17920；④ 引擎日志显示 decode 期间 `host 97.8–99.8%`（CPU 几乎满载），
且每一步都伴随 `ring retrieve: preferred=N restored=N` —— **疑似 host 侧成为瓶颈，但这只是观察，不是结论**。

## 6. KVMem 证据（教程 §3 两行判据）

```
[ring] content scoring ON by default (the ring is configured): retrieval ranks pages by the query-conditioned content score. …
kvmem_score: SELECT label=text_prefill_chunk n_blocks=1 budget_blocks=512 sink_blocks=64 recent_blocks=0 kept=1 runs=1
  skip=0 window_tokens=64 sink_kept=1 recent_kept=0 scored_kept=0 candidates=0 kept_range=[0,0] sum_score=64.000
  query_tokens=64 span_mode=abs span_abs=[3,1126) chunk_abs=0 span_local=[960,1024) oracle_ok=1 scale_floor=0.062500
```

- 第一行（启动期）✅ 出现；第二行 **`SELECT` 行数 = 1**（服务已就绪且发过请求，故此判据有效）
- 另有 `kvmem_score: ARMED capacity_blocks=4096 …`（启动期）与 `kvmem_score: KEPT 0`

**同时抓到的三条待发布方确认的现象（原样附上，不做推断）**：

1. `kvmem_score: query span [3,1126) not usable for chunk [0,1024) (empty overlap or longer than MAXQ=256) -- falling back to the tail rule (QUERY_TAIL)`
   —— 本次题面 1,133 token，query span 长度 1,123 > `MAXQ=256`，于是**回退到 tail 规则**。
2. `[ninfer] kvmem harvest: fused rmsnorm+rope branch cannot expose the pre-RoPE key (layer 0, N tokens); this chunk is NOT in the index`
   —— 多次出现（N = 3/4/9/102），即**部分 chunk 未进 KVMem 索引**。
3. `kvmem_score: KEPT 0` 紧跟 `SELECT … kept=1 sink_kept=1 scored_kept=0 candidates=0` —— 本次保留的是 sink 块，内容打分保留 0 块。

## 7. 未测（显式声明，不用推断顶替）

- 未跑长题面（>10k token）、未跑多轮、未跑超池检索、未跑其它 `--kv-dtype`、未跑其它档位（§0.4 明令禁止穷举）
- 未跑 `verify-arch-engine.ps1`（本机**无 E: 盘**，脚本默认模型路径 `E:\betakit-ptq1-v1\…` 与输出目录
  `E:\infer-build\…` 均不存在 ⇒ 必然 `REFUSE`；属路径前提不符，**不是**关于引擎的判决）
- 未验证 `--no-cuda-graph` 之外的任何"提速"改动（诚实：这条是为了装得下必须付的代价，不是调优结论）
- 未测 8 GB 配置在**长期/并发**下的稳定性（`--max-concurrency 1`，只发了单请求）

## 8. 回报发布方的三处包级异常

| # | 异常 | 证据 |
|---|---|---|
| 1 | **`README-pack.md` §2 身份表与实物+清单不符** | README：sha256 `42CD0735…89FD` / 1,343,609,856 B / built 10/02 21:47:04；实物与 `SHA256SUMS.txt`：`E3E0486A…F7BB3` / 1,329,240,576 B / mtime 10/03 03:16:38 |
| 2 | **包内缺 `MODELS.txt`** | 教程 §0.0 声称"下哪个/多大/sha256/去哪下"都在包根 `MODELS.txt`；本包没有，`SHA256SUMS.txt` 也不覆盖它 ⇒ 权重身份只能靠教程 §0.0 的字节数核对，sha256 无官方口径可比 |
| 3 | **原样 argv 在 8 GB 卡上无解** | §3/§4 的隔离实验与回归式：池无关固定项 1.31 GiB（CUDA Graph 814 MiB），只调 §5.2 明文旋钮无法消除 |

## 9. §0.3 回报模板（已按本机实测填好，可直接转发）

```
【部署回报】
卡：NVIDIA GeForce RTX 5060 / 显存 8151 MiB / 驱动 <驱动版本>（CUDA 13.1）/ compute cap 12.0
档位：PTQ1_0   端口：8095   argv：包内 start-ptq1-mtp.bat 的 argv，**两处改动**：
      --kv-capacity 17920→8192、增加 --no-cuda-graph（原文件未改，另建 start-ptq1-mtp-8gb.bat；
      改动依据见下"原样 argv 被拒"与隔离实验）
起服务：engine ready ✓   capacity | KV 8,192 tokens, k8v4, explicit | pages 128/4,096 | runtime 710.0 MiB | free 218.5 MiB
        host KV pinned 16.0 GiB ✓   listening on http://127.0.0.1:8095 ✓
KVMem：content scoring ON by default ✓   kvmem_score: SELECT 行数 = 1
测速（1,000 进 / 1,000 出，数数字语料）：prefill 570.1 tok/s · decode 60.3 tok/s · TTFT 2.0 s · 总 18.6 s
        （第二次独立运行：481.2 / 59.0 / 2.4 s / 19.3 s；mtp accepted 780/875 = 89.1%，两次相同）
短测结论：可用（HTTP 200，答案连续正确 301 302 303…，显存不炸）
原样 argv 被拒原文（即使桌面仅占 467 MiB / 空闲 7429 MiB 仍被拒）：
  FATAL server failed during startup | requested Engine runtime reservation requires 1863978752 bytes,
  but only 941719552 bytes are available for runtime capacity
隔离实验（每行只改一个旋钮）：
  17920/16384/262144            → requires 1,863,978,752 / available 817,598,464  FATAL
  7168/16384/262144             → requires 1,570,062,080 / available 639,004,672  FATAL
  7168/1024/262144              → requires 1,570,062,080（逐字节相同：host 池不影响该预留）
  7168/1024/32768               → requires 1,570,033,408（ctx 缩 1/8 只差 28,672 B）
  17920/16384/262144 + --no-cuda-graph → requires 1,010,437,888 / available 940,736,512（差 66.5 MiB）
  ⇒ 回归式：预留 ≈ 1,374,117,632 B（池无关固定项，主体 = CUDA Graph 814 MiB）+ 27,336 B × 池
  ⇒ 结论：本卡上不存在任何池组合能让原样 argv 启动
其它现象（原样附上，未定位根因）：
  1) kvmem_score: query span [3,1126) not usable for chunk [0,1024) (… longer than MAXQ=256) -- falling back to the tail rule (QUERY_TAIL)
  2) [ninfer] kvmem harvest: fused rmsnorm+rope branch cannot expose the pre-RoPE key (layer 0, N tokens); this chunk is NOT in the index（多次）
  3) decode 期间 host 97.8–99.8%，每步伴随 ring retrieve: preferred=N restored=N；decode 60.3 vs 构建机 196.8 = 3.3×
     （带宽 448 vs 736 GB/s = 1.64×；本档关了 CUDA Graph；池 8192 vs 17920）——**根因未定位，按 §6 第 3 类上报**
包级异常：README §2 身份表与实物不符（42CD0735… / 1,343,609,856 B vs 实物 E3E0486A… / 1,329,240,576 B）；
          包内缺 MODELS.txt（权重 sha256 无官方口径可对，本次仅以教程 §0.0 的 6,394,697,216 B 核对）
未测：长题面（>10k token）· 多轮 · 其它 --kv-dtype · 其它档位 · 超池检索 · 并发/长期稳定性
      （按 §0.4：穷举式测试属研究级，交发布方决定）
```

---
*本回执由部署 agent 生成：每条读数都来自引擎控制台原文或可复现命令；"未做"的动作一律显式标注为未做。*

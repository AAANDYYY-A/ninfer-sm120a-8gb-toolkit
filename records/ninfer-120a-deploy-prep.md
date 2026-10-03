# NInfer sm_120a 引擎包 · 部署准备与验收台账

- 包路径：`D:\AI-FAST\infer-engine-sm120a-20261002`
- 本机：NVIDIA GeForce RTX 5060 / 8151 MiB / 驱动 591.86（CUDA 13.1）/ compute cap **12.0**
- 当前状态：**引擎侧全部就位，唯一缺口是模型权重**（用户稍后提供下载链接）
- 已定策略（用户选定）：① 权重由用户给链接；② **argv 严格照包内原样，失败即停、贴原文回报，不调参**

---

## 1. 已核实（每条都可复现）

| # | 项 | 读数 | 判据 |
|---|---|---|---|
| 1 | 包清单完整性 | `ok=18 mismatch=0 missing=0 unparsed=0` | `powershell -NoProfile -ExecutionPolicy Bypass -File .\verify-kit-manifest.ps1 -Kit .` |
| 2 | 引擎哈希 | `E3E0486A5B78DFC9CB2FE146FF9FE63433E1E52FC54B7CED8888EE54EE1F7BB3` | 与 `SHA256SUMS.txt` 第 8 行逐字一致 |
| 3 | 引擎字节数 / mtime | `1,329,240,576` B / `2026-10-03 03:16:38` | `Get-Item` + `Get-FileHash` |
| 4 | 卡片与包匹配 | cc **12.0** → `pick-engine.bat` 规则映射到 `ninfer-serve-120a.exe` | `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv` |
| 5 | 引擎能否在本卡装载 | `--help` 正常输出完整 usage，**无** `cudaErrorNoKernelImageForDevice` | 直接在 `engine\` 下运行 exe（DLL 同目录，运行时齐备） |
| 6 | 端口占用 | 8091 / 8094 / 8095 / 8096 全部空闲 | `netstat -ano \| findstr` |
| 7 | D 盘余量 | `184,353,857,536` B ≈ **171.7 GiB**（放 7.65 GB 权重绰绰有余） | `dir D:\` |
| 8 | `models\` 目录 | 已创建（空） | 写在工作区外，已获一次性授权 |
| 9 | 启动器接线 | `start-pq2.bat` 现打印<br>`REFUSE: model not found: "...\models\\Ternary-Bonsai-2-27B-ninfer-v3-mtponly.ninfer"` | 证明"除权重外链路完整"，且期望文件名精确已知 |
| 10 | 引擎运行库 | 9 个 `.dll` 与 exe 同目录（CUDA/FFmpeg/curl） | `verify-arch-engine.ps1` 要求的"同目录运行库"前提满足 |

## 2. 必须回报给发布方的三处异常

### A2.1 `README-pack.md` §2 的身份表与实物不符（**需发布方确认**）

| | README 声称 | 实物 / 清单实测 |
|---|---|---|
| sha256 | `42CD073572643C9720E1AB54AD056D19BA44A33578DDDF53BBD010295DE189FD` | `E3E0486A…F7BB3` |
| bytes | `1343609856` | `1329240576` |
| built | `10/02/2026 21:47:04` | mtime `2026-10-03 03:16:38` |

清单本身是绿的（`SHA256SUMS.txt` 覆盖 18 个文件全中），所以**包自洽**；但 README 那句"verify before you trust any
reading"所指向的那个身份，不是这个二进制。二者必须由发布方对齐，否则后续任何"按 README 对哈希"的动作都会误判。

### A2.2 包内缺 `MODELS.txt`（**这是当前唯一的部署阻塞**）

教程 §0.0 第 1/3 步说"下哪个文件、多少字节、sha256、去哪下"全在包根 `MODELS.txt`；本包根目录没有该文件，
`SHA256SUMS.txt` 也不覆盖它。因此：

- 我**无法**自行取得权重（也没有任何官方 URL）；
- 即便拿到权重，若不给期望 sha256/字节数，**身份校验无法成立**（届时回报里会明确标"未校验"，不用推断顶替）。

本机已确认**不存在任何 `.ninfer`**（`dir D:\*.ninfer /s /b` 与 C:/D: 全盘递归搜索均为空）；
同期的两个 7 GB 级大 zip 经查是安卓 OTA 包（`payload.bin`），与模型无关。

`D:\DOWNLOADS\ZIP-README.txt` 只说明模型包位于发布方本机 `E:\ship-next\modelpack-pq2-v2-20261002`：
`Ternary-Bonsai-2-27B-ninfer-v3.ninfer`（9.52 GB）+ `Ternary-Bonsai-2-27B-ninfer-v3-mtponly.ninfer`（7.65 GB），
**未给下载地址**。

### A2.3 8 GB 卡 + 包内 argv 的已知冲突（**按你的决定：原样跑，失败即停**）

本机 2026-10-01 的回执 `D:\build\RECEIPT-8GB-5060-20261001.md` 在**同一张卡**上实测：

| 观察 | 原始读数 |
|---|---|
| 默认 `--host-kv-mib 8192` 直接失败 | `cudaMallocHost failed: cudaErrorMemoryAllocation`（当时 RAM 空闲 23.6 GB） |
| `--host-state-slots` 默认 8 同类失败 | 必须降到 1 |
| 不加 `--wddm-evictable-budget` | planning 直接拒启（`requires … available …`） |

而包内 `start-pq2.bat` 写的是 `--kv-capacity 17920 --host-kv-mib 16384`（16 GiB 常驻 pin）。
按你的选择，我**不改**任何 argv：原样起；若被拒，**原文照抄回报**，不做调参重试。
（教程 §5.2 允许"按引擎报的数字改池参数"，这条路已登记为**未采用**。）

## 3. 档位选择（已按卡定档，不再讨论）

| 档位 | 启动器 | 需要的模型 | 本机 8 GB 是否适用 |
|---|---|---|---|
| **PQ2 小卡档** | `start-pq2.bat`（端口 **8091**） | `Ternary-Bonsai-2-27B-ninfer-v3-mtponly.ninfer` 7.65 GB | ✅ **本次目标档** |
| PQ2 全量档 | `start-pq2-dflash.bat`（8094） | `Ternary-Bonsai-2-27B-ninfer-v3.ninfer` 9.52 GB | ❌ 模型 9.52 GB > 8 GB 显存 |
| PTQ1_0 档 | `start-ptq1-mtp.bat`（8095） | `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 6.39 GB | ⚠️ 需另配 PTQ1 模型包，本次未取 |
| 第三方 paicat | 不适用本包 | `Ternary-Bonsai-2-27B.ninfer` 9.81 GiB | ❌ 该工程全部档位需 ≥10.2 GiB 显存 |

> ⚠️ 本机已有另一条 **Prism llama.cpp** 路线（`D:\build\service-control.ps1`，端口 8096，实测 decode 40.5 t/s）。
> 8 GB 卡**两个引擎互斥**：回执 M13 实测同卡起第二个实例必然崩（WDDM 超售 → `cudaErrorLaunchFailure`）。
> 起 ninfer 前先确认 8096 没有在跑（当前实测：**没在跑**）。

## 4. 环境限制（记录在案，不构成部署阻塞）

1. **本包无 `docs\`** → 教程 §0.5 **纯指令路径**适用：脚本结果只是加分项。
2. **本机无 E: 盘**，而 `verify-arch-engine.ps1` 默认模型路径为 `E:\betakit-ptq1-v1\models\…`、输出目录为
   `E:\infer-build\fusion-master\needle\…` ⇒ 该脚本在本机**必然 REFUSE**（`REFUSE: missing …`）。
   这是路径前提不符，**不是**关于引擎的判决；改为纯指令验收（§0.1 的 1/2/3/5 步都不依赖脚本）。
3. **TLS/Schannel 在沙箱内不可用（本次实测）**：
   - `curl.exe --ssl-no-revoke -I https://hf-mirror.com` → `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`
   - `Invoke-WebRequest` → `基础连接已经关闭: 接收时发生错误`
   - 原生 .NET `SslStream` → `No credentials are available in the security package`
   - TCP 443 `TcpTestSucceeded=True`；同一条 curl/SslStream 在 `danger-full-access` 下 **http=200 / TLS 1.3** 正常
   ⇒ **根因是 DSH 沙箱对 Schannel 凭证的访问限制，不是机器故障、不是代理**（WinINET `ProxyEnable=0`，仅残留 `127.0.0.1:7890`）。
   **下载通道（已验证可用）**：bundled CPython + OpenSSL 3.5.8，`https://hf-mirror.com` → `status=200`。
   本地 HTTP（`127.0.0.1`）不需要 Schannel，短测请求不受影响。

## 5. 待办（链接到位后按序执行，全程不改包内任何文件）

### 步骤 1 · 下载 + 校验（权重）

```powershell
$py = 'C:\Users\DDJOI\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
& $py C:\Users\DDJOI\Documents\deepseek-harness\default-workspace\fetch-ninfer-model.py `
  --url "<用户提供的直链>" `
  --out "D:\AI-FAST\infer-engine-sm120a-20261002\models\Ternary-Bonsai-2-27B-ninfer-v3-mtponly.ninfer" `
  --bytes <期望字节数> --sha256 <期望SHA256> --skip-if-ok
```

- 断点续传（HTTP Range → `.part`，忽略 Range 时自动**从 0 重下**而不是拼接垃圾数据）
- 结束时逐字比对**字节数 + sha256**；无期望值时必须输出 `[warn] … NOT verified`
- 该步骤写 D 盘，需要一次提权（或在沙箱内用 Python 通道跑，TLS 已实测可用）

### 步骤 2 · 起服务（argv 原样，零改动）

```powershell
cmd /c "cd /d D:\AI-FAST\infer-engine-sm120a-20261002 && start-pq2.bat"
```

**就绪判据（两项都要）**：控制台出现 `engine ready` 与 `capacity |` 两行。
若被拒：原文抄最后 5 行，停止，不进步骤 3（按你的决定）。

### 步骤 3 · 两行 KVMem 证据

```
[ring] content scoring ON by default (the ring is configured): …      <- 启动期
kvmem_score: SELECT label=text_prefill_chunk n_blocks=… query_tokens=64 span_mode=…   <- 发过请求后，≥1 行
```

第二条为 0 行 ⇒ 打分没跑、退回词法排序 ⇒ 小池下会静默答错，**部署不成立**。

### 步骤 4 · 一条测速请求（1000 进 / 1000 出，数数字语料）

请求体已备好：`count-1000-payload.json`（`model=qwen3.8-27b`、`temperature=0`、`max_tokens=1000`，
题面 = `1..300` + 逐字照抄的 Continue 指令）。

```powershell
curl.exe -sS http://127.0.0.1:8091/v1/chat/completions `
  -H "Content-Type: application/json" `
  --data-binary "@C:\Users\DDJOI\Documents\deepseek-harness\default-workspace\count-1000-payload.json"
```

**三个数不从响应里算，去引擎自己的控制台抄这一行**（权威读数）：

```
req#1 done | openai-chat | output limit | prompt <N> | output 1,000 | cache 0 (0.0%) |
  TTFT <N> ms | total <N>s | queue <N> ms | prefill <N> tok/s | decode <N> tok/s | mtp accepted <a>/<b>
```

`finish_reason=length` 是正常的（就该写满 1000 token）。构建机基准（RTX 4080S / sm_89 / 池 17920）：
PQ2-mtponly 档 ≈ prefill 3.30k tok/s · decode 237.9 tok/s（mtp 接受 88.1%）· TTFT 344 ms · 总 4.6 s。
**卡型不同 2 倍以内算正常；差 3 倍以上按 §6 第 3 类上报（附证据）。**

### 步骤 5 · 回报（照抄填空）

```
【部署回报】
卡：NVIDIA GeForce RTX 5060 / 显存 8151 MiB / 驱动 591.86（CUDA 13.1）
档位：PQ2-mtponly   端口：8091   argv：start-pq2.bat 原样（逐字，未改动）
起服务：engine ready □   capacity 行：<逐字贴>
KVMem：启动行 content scoring ON by default □   SELECT 行数：<N>
自检：verify-arch-engine.ps1 本机不可用（无 E: 盘 + 默认路径指向 E:\，非引擎判决）
      verify-kit-manifest.ps1 => ok=18 mismatch=0 missing=0
测速（1000 进 / 1000 出，数数字语料）：prefill <N> tok/s · decode <N> tok/s · TTFT <N> ms · 总 <N> s
短测结论：<可用 / 有问题（症状 + 已贴证据）>
未测：长题面（>10k token）、多轮、其它 --kv-dtype、其它档位、超池检索、-mtponly 以外的模型件
      （按 §0.4：穷举式测试属研究级，交发布方决定）
另报：README §2 身份表与实物不符（见 A2.1）；包内缺 MODELS.txt（见 A2.2）
```

## 6. 一页速查（本机专用）

```
起服务   ：cmd /c "cd /d D:\AI-FAST\infer-engine-sm120a-20261002 && start-pq2.bat"   -> engine ready + capacity |
验 KVMem ：content scoring ON by default  +  kvmem_score: SELECT（=0 即部署问题）
测速     ：POST 127.0.0.1:8091/v1/chat/completions，count-1000-payload.json -> 抄控制台 prefill/decode/TTFT
校验     ：verify-kit-manifest.ps1 -Kit .（18/18 绿）；引擎 sha256 E3E0486A…F7BB3
下载     ：bundled python + fetch-ninfer-model.py（Schannel 在沙箱内不可用，别用 curl 硬试）
互斥     ：本卡同时只能跑一个实例（ninfer 8091 与 Prism llama.cpp 8096 二选一，起前先查端口）
禁止     ：改包内文件 / 长测穷举 / 逐字节重发超池题面 / 用推断代替实测
拿不准   ：交发布方（§6 三类 + 上报格式）
```

---
*本台账由部署 agent 生成，仅记录实测读数与命令，不含推断性结论。所有"未做"的动作都显式标注为未做。*

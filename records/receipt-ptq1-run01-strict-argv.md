# 运行 #01 · PTQ1_0 档 · 严格照包内 argv（未改一字）· 2026-10-03 12:06–12:07

- 命令：`cmd /c "cd /d D:\AI-FAST\infer-engine-sm120a-20261002 && start-ptq1-mtp.bat"`
- 模型：`models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（6,394,697,216 B，sha256 `5C4486C8…E21B8`）
- 结果：**FATAL，启动失败（exit 1）**；权重已装完、KVMem 打分器已上线，倒在"Engine runtime reservation"

## 1. 引擎控制台原文（逐字）

```
[engine] D:\AI-FAST\infer-engine-sm120a-20261002\engine\ninfer-serve-120a.exe
[model ] D:\AI-FAST\infer-engine-sm120a-20261002\models\\bonsai2_27b_ternary_ptq1_native_mtp.ninfer
[note  ] content scorer defaults ON (set NINFER_TERNARY_KVMEM=0 to disable = negative control)

2026-10-03 12:06:18.870  INFO  build unknown
2026-10-03 12:06:18.872  INFO  engine init | constructing service
2026-10-03 12:06:18.958  INFO  starting engine
2026-10-03 12:06:19.103  INFO  engine | engine init | device ready, constructing model instance
2026-10-03 12:06:19.104  INFO  engine | calibrating routes for nvidia-geforce-rtx-5060-sm120 (30 SMs)
2026-10-03 12:07:29.640  INFO  engine | device profile nvidia-geforce-rtx-5060-sm120: 51 routed keys (calibration)
2026-10-03 12:07:30.320  INFO  loading weights | 5.94 GiB
2026-10-03 12:07:33.458  INFO  weights ready | 5.94 GiB | 3.1s | 1.89 GiB/s
[ring] content scoring ON by default (the ring is configured): retrieval ranks pages by the query-conditioned content score. Set NINFER_TERNARY_KVMEM_SCORE=0 (or the master switch NINFER_TERNARY_KVMEM=0) to fall back to the lexical ranking (that is the negative control, not a tuning knob).
2026-10-03 12:07:33.536  ERROR startup failed | finalizing target | 73.6 ms
2026-10-03 12:07:33.596  ERROR engine init | FAILED while constructing the service: requested Engine runtime reservation requires 1863978752 bytes, but only 817598464 bytes are available for runtime capacity
2026-10-03 12:07:33.596  FATAL server failed during startup | requested Engine runtime reservation requires 1863978752 bytes, but only 817598464 bytes are available for runtime capacity

[engine exited] errorlevel=1
```

## 2. 两个证据行的判定（教程 §3 的判据，按服务是否 ready 区分）

| 判据 | 读数 | 判定 |
|---|---|---|
| `[ring] content scoring ON by default` | **出现**（启动期） | ✅ KVMem 内容打分器**已默认开启** |
| `kvmem_score: SELECT …` | 0 行 | ⚠️ **不能**据此判"打分没跑"：服务从未 `engine ready`，没有任何请求被服务过，SELECT 行**不可能**存在。教程 §3 那条"=0 ⇒ 退回词法排序"的前提是"服务已就绪且发过请求" |

## 3. 拒绝的算术

| 项 | 字节 | 换算 |
|---|---|---|
| 引擎要求的 runtime 预留 | `1,863,978,752` | 1.736 GiB |
| 当时可用 | `817,598,464` | 779.7 MiB |
| **缺口** | `1,046,380,288` | **997.9 MiB ≈ 1.0 GiB** |

同一时刻的显存账（`nvidia-smi`，起服务前实测）：总 8151 MiB · **桌面已占 1730 MiB** · 空闲 6166 MiB ·
权重 `5.94 GiB` = 6098 MiB ⇒ 权重装完后只剩 ~68 MiB 可用，而引擎还要 1.736 GiB。

> 这不是"权重装不下"（`weights ready` 已打印），是**预留被桌面占用挤掉**。
> 与本机 2026-10-01 回执 `M12` 的判断一致：当时也指向"桌面占用降到 ~0.6 GiB 才能过"。

## 4. 本次的正面发现（对发布方有价值，之前未记录）

1. **本 2026-10-02 引擎会在运行时为本卡标定 route**：`calibrating routes for nvidia-geforce-rtx-5060-sm120 (30 SMs)`
   → `51 routed keys (calibration)`。**不再出现**旧包那套"出货常量 SM=170 与实卡 30 SM 不匹配"的问题
   （10-01 回执 §0 曾记 `sm_matches=false`）。
2. **标定结果会缓存**：`%USERPROFILE%\AppData\Local\ninfer\device-profiles.json`（6.2 KB，
   `origin: "calibration"`，`multiprocessors: 30`）。代价约 **70 秒**（12:06:19 → 12:07:29），
   **只在首次发生**，后续启动复用。
3. 权重装载速率 `1.89 GiB/s`、`5.94 GiB` 用 **3.1 s**；本卡运行库/内核镜像装载**无任何报错**
   （README §5.1 那条"未验证本二进制能否在对应卡上跑"在本机已被推到"能跑到运行时预留这一步"）。

## 5. 环境状态（本次运行后）

- 无残留进程；端口 8095 空闲；显存回到 `1516 MiB used / 6380 MiB free`
- 包内文件**未被改动**：`verify-kit-manifest.ps1 -Kit .` = `ok=18 mismatch=0 missing=0`
- 唯一新增：`models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（设计就是要放这里）

## 6. §5.2 调池隔离实验（用户放行后执行；探针 `ninfer-probe.bat`，包内文件未动）

每轮只改一个旋钮，其余逐字节等同 `start-ptq1-mtp.bat` 的 argv；六条 KV 环境变量原样复制。

| # | `--kv-capacity` | `--host-kv-mib` | `--max-context` | 引擎要求 (B) | 当时可用 (B) | 结果 |
|---|---|---|---|---|---|---|
| 0 | 17920 | 16384 | 262144 | `1,863,978,752` | `817,598,464` | FATAL |
| 1 | **7168** | 16384 | 262144 | `1,570,062,080` | `639,004,672` | FATAL |
| 2 | 7168 | **1024** | 262144 | `1,570,062,080` | `694,345,728` | FATAL（与 #1 **逐字节相同**） |
| 3 | 7168 | 1024 | **32768** | `1,570,033,408` | `641,953,792` | FATAL（只差 28,672 B） |

**结论（三条，均为实测反推，非推断）**

1. `--host-kv-mib` 16384 → 1024：预留**完全不变** ⇒ 主机池页表不占这 1.31 GiB。
2. `--max-context` 262144 → 32768（1/8）：预留只降 28,672 B ⇒ 逻辑上下文不是驱动项。
3. `--kv-capacity` 17920 → 7168（-60%）：预留只降 293,916,672 B ⇒ 斜率 **27,336 B/token**
   （与教程 §2 的 k8v4 ≈ 25 KiB/token 同量级）。
   ⇒ **回归式：预留 ≈ `1,374,117,632` B（1.31 GiB 固定项）+ 27,336 B × 池。**

**因此：§5.2 明文的两个旋钮 + §2 的第三个池数，都无法消除那 1.31 GiB 固定项；
在这张 8 GB 卡（6.39 GB 权重 + ~1.5 GiB 桌面占用）上，本档 argv 不存在可用的池组合。**
能跑起来的形状要求一整组池无关的压缩/规避开关（本机 10-01 用上一代包实测 runtime 仅 485.7 MiB），
那已超出 §5.2 的授权范围，属"换配置形状"，须发布方给 8 GB 口径。

## 7. 未做（显式声明，不用推断顶替）

- 未跑测速（服务未就绪，§0.2 的三个数**拿不到**）
- 未跑 `verify-arch-engine.ps1`（本机无 E: 盘，脚本默认路径必然 REFUSE；属路径前提不符）
- 未改任何 argv、未改任何池参数、未换档位、未换 dtype

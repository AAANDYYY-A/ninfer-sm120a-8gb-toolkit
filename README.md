# NInfer sm_120a 引擎包 · 8 GB 显卡（RTX 5060）部署工具集

本仓库**只包含我们自己写的脚本、文档与实验记录**，用于把一台 8 GB 显存的机器
（NVIDIA GeForce RTX 5060，compute capability 12.0）跑通 **NInfer `sm_120a` 引擎包**（PTQ1_0 档）。

## 不包含什么（重要）

| 未包含 | 大小 | 原因 |
|---|---|---|
| `engine\ninfer-serve-120a.exe` 及 9 个运行时 DLL | 1,901 MiB | 是发布方的二进制制品；且单文件超过 GitHub 的 100 MiB 硬上限 |
| `models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | 6,098 MiB | 是独立分发的模型包；6 GB 单文件无法上传（Release 单资产上限也只有 2 GB） |

⇒ 想跑起来需要**自备引擎包与模型包**，按发布方的说明放置：
引擎包解到本仓库同级目录，模型放进 `models\`，文件名逐字保持
`bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（字节数 6,394,697,216，
sha256 `5C4486C8A52687E3F62072C7DD2A320546D0E00D1C019BF137EB02CC944E21B8`）。

## 快速开始（引擎与模型就位后）

1. 双击 **`chat-web.bat`** → 本窗口跑引擎，另开一个最小化窗口跑聊天页，并自动打开浏览器
2. 聊天页：<http://127.0.0.1:8097/> · 引擎 API：<http://127.0.0.1:8095/v1>
3. 想用终端聊天：`chat-cli.bat`；想让它当 agent：`agent\agent.bat`

## 本仓库内容

| 路径 | 作用 |
|---|---|
| `start-ptq1-mtp-8gb.bat` | 引擎启动器。相对发布方原启动器只有 4 处改动，全部附引擎实测数字（见文件头） |
| `ninfer-chat.py` | 聊天页 + 同源代理（引擎无内置网页、不发 CORS）；含交付护栏与 `max_tokens` 钳制 |
| `chat-web.bat` / `chat-cli.bat` / `ninfer-cli.py` | 一键入口 / 终端聊天 |
| `agent\agent-min.py` / `agent\agent.bat` | 最小 AI agent（工具循环 + 护栏 + 文件沙箱） |
| `demos\` | 示例提示词与产出（蜻蜓闹钟，单文件 HTML） |
| `docs\` | 部署回执与手册落地记录 |
| `records\` | 全部工程记录：逐轮读数、被拒原文、隔离实验、生成与验证脚本 |
| `README-聊天怎么用.md` | 面向使用者的完整说明（七章） |

## 关键实测读数（RTX 5060 8 GB / 驱动 <驱动版本>）

| 项 | 读数 |
|---|---|
| 引擎启动 | `engine ready | bonsai2-27b | total 3.7s`；`capacity | KV 8,192 tokens, k8v4, explicit | runtime 710.0 MiB` |
| 数数字语料 1,000 进 / 1,000 出 | prefill 570.1 tok/s · decode 60.3 tok/s · TTFT 2.0 s · 总 18.6 s · MTP 接受 780/875 (89.1%) |
| 与发布方构建机（RTX 4080 SUPER，decode 196.8 tok/s）对比 | 慢约 3.3×（带宽 448 vs 736 GB/s；为装进 8 GB 关闭了 CUDA Graph） |
| 工具调用 | 支持；`finish_reason=tool_calls`，规范 `tool_calls` 数组 |
| 为何不能照搬原启动器 argv | 池无关固定项 1.31 GiB（CUDA Graph 814 MiB）；`--host-kv-mib` 与 `--max-context` 均不影响它 |

## 许可与归属

- 引擎与模型：归发布方（UP主 / Prism ML / 阿里云等）所有，**不在本仓库**。
- 本仓库的脚本与文档：由部署 agent 编写，随你处置（若发布请自行附许可）。
- `docs\04-卡死与循环的防治.md` **未收录**：那是发布方单独投递的内部手册，公开再分发请先取得同意。

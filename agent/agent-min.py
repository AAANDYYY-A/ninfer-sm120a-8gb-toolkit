#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal local AI agent on top of the NInfer engine (26B/27B, OpenAI-compatible).

WHY THIS FILE
  The engine answers `finish_reason=tool_calls` with a proper `tool_calls` array
  (verified 2026-10-03), so it can drive an agent loop. This is the smallest honest
  loop: you give it a task, it may call tools, it reports every step.

GUARDRAILS COPIED FROM docs\\04-卡死与循环的防治.md (the field manual)
  * SHELL_LOOP  : "assistant sends only tool_calls, text empty" for N turns in a row
                  is a FAILURE state, not progress -> `--max-shell-turns` (default 3)
  * same tool, same arguments, repeated      -> cut off after `--max-same-call` (default 2)
                  and inject a correction message (the manual limits consecutive calls)
  * step cap    : `--max-steps` (default 6); one-shot tool use + a wrap-up is what the
                  manual says this model is actually good at
  * max_tokens  : kept <= the KV pool (manual section 1-11); default 1024 per turn
  * JSONL log   : one line per turn, for the manual's counters (turn/tool/args/finish/wall)

SAFETY
  File tools are confined to one sandbox directory (`--root`, default
  .\\agent-work). Absolute paths and `..` outside the root are refused. There is
  deliberately NO shell tool; add one only if you accept arbitrary execution.

USAGE
  python agent-min.py "现在几点？然后在工作目录里建 hello.txt，写入当前时间。"
  python agent-min.py --root D:\\some\\dir --max-steps 8 "..."
  python agent-min.py --base http://127.0.0.1:8097/v1    # go through the guarded proxy
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

TOOLS = [
    {"type": "function", "function": {
        "name": "get_time",
        "description": "返回本机当前日期与时间",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "列出工作目录（或其子目录）里的文件名",
        "parameters": {"type": "object", "properties": {
            "subdir": {"type": "string", "description": "相对工作目录的子目录，留空为根"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取工作目录内的一个文本文件",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "相对工作目录的路径"},
            "max_bytes": {"type": "integer", "description": "最多读多少字节，默认 4000"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "在工作目录内创建或覆盖一个文本文件",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "相对工作目录的路径"},
            "content": {"type": "string", "description": "要写入的完整内容"}},
            "required": ["path", "content"]}}},
]

SYSTEM = ("你是一个本地 AI agent。需要用工具时调用工具；拿到工具结果后给出简短结论。"
          "不要重复调用同一个工具同样的参数；不要只输出计划而不给结果。")


def jdump(x):
    return json.dumps(x, ensure_ascii=False)


class Engine:
    def __init__(self, base, model, max_tokens, timeout=600):
        self.base = base.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout

    def chat(self, messages, tools=True, temperature=0.7):
        body = {"model": self.model, "messages": messages, "temperature": temperature,
                "max_tokens": self.max_tokens}
        if tools:
            body["tools"] = TOOLS
            body["tool_choice"] = "auto"
        req = urllib.request.Request(self.base + "/chat/completions",
                                     data=jdump(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError("engine HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
        return out["choices"][0], time.time() - t0


class Sandbox:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def resolve(self, rel):
        p = os.path.abspath(os.path.join(self.root, rel or "."))
        if p != self.root and not p.startswith(self.root + os.sep):
            raise ValueError("拒绝越出工作目录：%s" % rel)
        return p


def run_tool(sbx, name, args):
    try:
        if name == "get_time":
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
        if name == "list_dir":
            p = sbx.resolve(args.get("subdir", ""))
            if not os.path.isdir(p):
                return "不是目录：%s" % args.get("subdir")
            items = sorted(os.listdir(p))[:200]
            return jdump(items) if items else "（空目录）"
        if name == "read_file":
            p = sbx.resolve(args.get("path", ""))
            if not os.path.isfile(p):
                return "文件不存在：%s" % args.get("path")
            n = int(args.get("max_bytes") or 4000)
            with open(p, "rb") as f:
                data = f.read(n)
            return data.decode("utf-8", "replace")
        if name == "write_file":
            p = sbx.resolve(args.get("path", ""))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            content = args.get("content") or ""
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            return "已写入 %s（%d 字节）" % (args.get("path"), len(content.encode("utf-8")))
        return "未知工具：%s" % name
    except Exception as exc:
        return "工具错误：%s" % exc


def main():
    ap = argparse.ArgumentParser(description="Minimal local AI agent on the NInfer engine")
    ap.add_argument("task", nargs="*", help="要 agent 做的事；不填则进入交互模式")
    ap.add_argument("--base", default="http://127.0.0.1:8095/v1",
                    help="OpenAI 兼容基址；用 8097 则同时受交付护栏与 max_tokens 钳制保护")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--max-tokens", type=int, default=1024, help="每轮输出上限，必须 <= 池（8192）")
    ap.add_argument("--max-steps", type=int, default=6)
    ap.add_argument("--max-shell-turns", type=int, default=3, help="连续只调工具不给正文的上限（手册 SHELL_LOOP）")
    ap.add_argument("--max-same-call", type=int, default=2, help="同一工具同一参数重复次数上限")
    ap.add_argument("--root", default=os.path.join(os.getcwd(), "agent-work"))
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--log", default="agent-run.jsonl")
    args = ap.parse_args()

    eng = Engine(args.base, args.model, args.max_tokens)
    sbx = Sandbox(args.root)
    batch = bool(args.task)

    try:  # make Chinese survive a non-UTF8 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 72)
    print(" 本地 AI agent · 引擎 %s · 模型 %s" % (args.base, args.model))
    print(" 工作目录 %s" % sbx.root)
    print(" 工具：get_time / list_dir / read_file / write_file（无 shell 工具）")
    print(" 护栏：最多 %d 步 · 连续纯工具轮 <= %d · 同一调用 <= %d 次 · 每轮 <= %d token"
          % (args.max_steps, args.max_shell_turns, args.max_same_call, args.max_tokens))
    print("=" * 72)

    while True:
        if args.task:
            task = " ".join(args.task)
            args.task = None
        else:
            try:
                task = input("\n任务> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                return 0
        if not task:
            continue
        if task in ("/exit", "/quit"):
            print("再见。")
            return 0

        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": task}]
        logf = open(args.log, "a", encoding="utf-8", newline="\n")
        call_counts = {}
        shell_turns = 0
        t_start = time.time()

        for step in range(1, args.max_steps + 1):
            ch, el = eng.chat(messages, tools=True, temperature=args.temperature)
            msg = ch.get("message") or {}
            calls = msg.get("tool_calls") or []
            text = (msg.get("content") or "").strip()
            print("\n[step %d · %.1fs · finish=%s]" % (step, el, ch.get("finish_reason")))
            if text:
                print("  正文: %s" % text.replace("\n", "\n        ")[:800])

            logf.write(jdump({"turn": step, "finish_reason": ch.get("finish_reason"),
                              "text_chars": len(text), "tool_calls": len(calls),
                              "wall_s": round(el, 2)}) + "\n")
            logf.flush()

            if not calls:
                print("\n=== 结论（%.1fs，%d 步）===\n%s" % (time.time() - t_start, step, text or "（空回答）"))
                break

            # --- manual section 1-6: pure tool-call turns must not go on forever ---
            shell_turns += 1
            if shell_turns > args.max_shell_turns:
                print("\n[护栏] 连续 %d 轮只调工具、不给正文 -> 判 SHELL_LOOP（手册 §1 第 6 条），中止。"
                      % args.max_shell_turns)
                break

            messages.append({"role": "assistant", "content": msg.get("content"),
                             "tool_calls": calls})
            for c in calls:
                fn = (c.get("function") or {})
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                key = name + "|" + raw_args
                call_counts[key] = call_counts.get(key, 0) + 1
                print("  -> 调用 %s %s" % (name, raw_args[:160]))
                if call_counts[key] > args.max_same_call:
                    result = ("[护栏] 同一次调用已重复 %d 次，拒绝再执行。"
                              "换一个思路：用已有信息直接给出结论。" % call_counts[key])
                    print("     %s" % result)
                else:
                    try:
                        a = json.loads(raw_args) if raw_args.strip() else {}
                    except Exception:
                        a = {}
                    result = run_tool(sbx, name, a if isinstance(a, dict) else {})
                    print("     %s" % str(result).replace("\n", "\n     ")[:400])
                messages.append({"role": "tool", "tool_call_id": c.get("id") or "call_x",
                                 "content": str(result)})
            if text:
                shell_turns = 0  # it did produce prose, so the loop is not empty
        else:
            print("\n[护栏] 达到 %d 步上限，停止（避免无界循环）。" % args.max_steps)
        logf.close()
        if batch:
            return 0


if __name__ == "__main__":
    sys.exit(main())

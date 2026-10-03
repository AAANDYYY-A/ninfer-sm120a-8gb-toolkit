#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Terminal chat for the NInfer engine -- no browser involved at all.

WHY: if the browser page ever fails, this removes every browser-side variable
(no CORS, no streaming quirks, no extensions, no cache). It talks straight to
the engine's OpenAI-compatible endpoint.

DEPENDENCIES: none (standard library only).

USAGE
  python ninfer-cli.py [--engine 127.0.0.1:8095] [--model qwen3.8-27b] [--max-tokens 1024]
  Type your message and press Enter. Commands:
    /clear          forget the conversation
    /max N          set the reply token ceiling (default 1024)
    /temp F         set temperature (default 0.7)
    /system TEXT    set the system prompt
    /exit           quit
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BANNER = "=" * 68


def stream_reply(engine, payload, prefix=""):
    req = urllib.request.Request(
        "http://%s/v1/chat/completions" % engine,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.time()
    first = None
    text = ""
    sys.stdout.write(prefix)
    sys.stdout.flush()
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                delta = json.loads(body)["choices"][0].get("delta", {}).get("content")
            except Exception:
                delta = None
            if delta:
                if first is None:
                    first = time.time() - t0
                text += delta
                sys.stdout.write(delta)
                sys.stdout.flush()
    secs = time.time() - t0
    sys.stdout.write("\n")
    rate = (len(text) / secs) if secs > 0 else 0
    print("[%d 字 · %.1f s · %.1f 字/秒 · 首字 %.2f s]" % (len(text), secs, rate, first or 0))
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="127.0.0.1:8095")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.7)
    a = ap.parse_args()

    try:  # make Chinese survive a non-UTF8 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(BANNER)
    print(" NInfer 终端聊天 · 引擎 http://%s/v1 · 模型 %s" % (a.engine, a.model))
    print(" 直接打字回车发送；/exit 退出，/clear 清空，/max N 改上限，/temp F 改温度")
    print(BANNER)

    try:
        with urllib.request.urlopen("http://%s/v1/models" % a.engine, timeout=8) as r:
            ids = [m.get("id") for m in json.load(r).get("data", [])]
        print("引擎就绪：%s" % (ids[0] if ids else a.model))
    except Exception as exc:
        print("!! 连不上引擎（%s）：%s" % (a.engine, exc))
        print("!! 请先双击 start-ptq1-mtp-8gb.bat，等它打印 engine ready 与 capacity |")
        return 2

    history = []
    system_prompt = None
    max_tokens = a.max_tokens
    temperature = a.temperature

    while True:
        try:
            line = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit"):
            print("再见。")
            return 0
        if line == "/clear":
            history = []
            print("（对话已清空）")
            continue
        if line.startswith("/max "):
            try:
                max_tokens = int(line.split(None, 1)[1])
                print("（回答上限 = %d token）" % max_tokens)
            except Exception:
                print("（用法：/max 1024）")
            continue
        if line.startswith("/temp "):
            try:
                temperature = float(line.split(None, 1)[1])
                print("（温度 = %s）" % temperature)
            except Exception:
                print("（用法：/temp 0.7）")
            continue
        if line.startswith("/system "):
            system_prompt = line.split(None, 1)[1]
            print("（系统提示已设置）")
            continue

        history.append({"role": "user", "content": line})
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + history
        payload = {
            "model": a.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            answer = stream_reply(a.engine, payload, prefix="AI> ")
            history.append({"role": "assistant", "content": answer})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            print("!! 引擎返回 HTTP %s：%s" % (exc.code, detail))
            history.pop()
        except Exception as exc:
            print("!! 请求失败：%s" % exc)
            history.pop()


if __name__ == "__main__":
    sys.exit(main())

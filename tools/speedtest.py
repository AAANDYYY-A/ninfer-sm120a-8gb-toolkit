#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One-shot speed measurement against the NInfer engine (stdlib only).

Sends the pack's standard counting corpus and prints the engine's OWN timings
from the response JSON - the authoritative reading, no log parsing.

  prefill tok/s = timings.prompt_per_second
  decode tok/s  = timings.predicted_per_second
  acceptance    = timings.draft_n_accepted / timings.draft_n

Recorded on this machine 2026-10-03 with the shipped 8 GB profile
(draft-tokens 4, no fast-prefill-kernel, pool 8192):
  prefill 482.8 tok/s | decode 54.5 tok/s | draft 875/780 = 89.1% | wall 20.7 s
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASELINE = {"prefill": 482.8, "decode": 54.5, "accept": 89.1, "label": "8GB profile, draft 4, no fast-prefill"}


def build_prompt():
    seq = " ".join(str(i) for i in range(1, 301))
    return (seq + "\n\nContinue the same number sequence from the next number. "
                   "Output numbers only, in the same space-separated format, "
                   "and keep going until the length limit.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="127.0.0.1:8095", help="host:port")
    ap.add_argument("--key", default="", help="API key (empty when the engine has none)")
    ap.add_argument("--max-tokens", type=int, default=1000)
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    body = {"model": "qwen3.8-27b",
            "messages": [{"role": "user", "content": build_prompt()}],
            "temperature": 0, "max_tokens": a.max_tokens}
    headers = {"Content-Type": "application/json"}
    if a.key:
        headers["Authorization"] = "Bearer " + a.key
    req = urllib.request.Request("http://%s/v1/chat/completions" % a.engine,
                                 data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    print("请求中（1000 token 输出，本机约 20 秒）...")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            j = json.load(r)
    except urllib.error.HTTPError as e:
        print("!! 引擎返回 HTTP %s：%s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
        if e.code in (401, 403):
            print("!! 需要密钥：把 api-key.txt 放在本脚本同目录，或 set NINFER_API_KEY=...")
        return 2
    except Exception as e:
        print("!! 连不上引擎（%s）：%s" % (a.engine, e))
        return 2
    wall = time.time() - t0

    ch = j["choices"][0]
    tim = j.get("timings") or {}
    usage = j.get("usage") or {}
    pre = float(tim.get("prompt_per_second") or 0.0)
    dec = float(tim.get("predicted_per_second") or 0.0)
    dn = int(tim.get("draft_n") or 0)
    da = int(tim.get("draft_n_accepted") or 0)
    acc = (100.0 * da / dn) if dn else 0.0

    print()
    print("=" * 62)
    print(" 权威读数（引擎自报 timings，不是估算）")
    print("=" * 62)
    print("  提示/输出 token   : %s / %s      finish=%s" %
          (usage.get("prompt_tokens"), usage.get("completion_tokens"), ch.get("finish_reason")))
    print("  墙钟耗时          : %.1f s" % wall)
    print("  prefill           : %8.1f tok/s   (%.0f ms)" % (pre, float(tim.get("prompt_ms") or 0)))
    print("  decode            : %8.1f tok/s   (%.0f ms)" % (dec, float(tim.get("predicted_ms") or 0)))
    print("  投机 草稿/接受    : %d / %d  = %.1f%%" % (dn, da, acc))
    if tim.get("cache_n") is not None:
        print("  缓存命中          : %s token" % tim.get("cache_n"))
    print("-" * 62)
    print("  对照基线（%s）：" % BASELINE["label"])
    print("    prefill %.1f  ->  %+.1f%%" % (BASELINE["prefill"], 100.0 * (pre / BASELINE["prefill"] - 1)))
    print("    decode  %.1f  ->  %+.1f%%" % (BASELINE["decode"], 100.0 * (dec / BASELINE["decode"] - 1)))
    print("    接受率  %.1f%% ->  %+.1f 个百分点" % (BASELINE["accept"], acc - BASELINE["accept"]))
    print("=" * 62)
    if dec >= BASELINE["decode"] * 1.3:
        print("结论：明显更快。可考虑长期使用这一档（不可预测输出会变慢，见启动器注释）。")
    elif dec >= BASELINE["decode"] * 1.05:
        print("结论：有提升但不显著。")
    else:
        print("结论：没有更快。换回 start-ptq1-mtp-lan.bat，并把这次读数交给发布方。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

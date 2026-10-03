#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the dragonfly alarm clock through the deployed chat proxy and check it.

Checks are the ones that matter for a one-shot artifact (doc 04 §1 states 1/2):
  * closed        -> ends with </html>, no guard TRUNCATED marker in the reply
  * self-contained-> no http(s) URLs, no media file references
  * non-empty     -> size in bytes
"""
import json
import os
import re
import sys
import time
import urllib.request

PROXY = "http://127.0.0.1:8097"
OUT = r"%USERPROFILE%\Documents\deepseek-harness\default-workspace\dragonfly-alarm.html"

PROMPT = """请写一个单文件 HTML 网页，双击即可在浏览器打开，实现一个「蜻蜓闹钟」。

硬性要求：
1. 只能是一个 HTML 文件，完全自包含：不允许任何外部资源（不要 CDN、不要外链字体/图片/音频/JS/CSS）；
   样式与脚本全部内联；提示音用 WebAudio 现场合成，不要音频文件。
2. 断网可用；闹钟设置存 localStorage，刷新后仍在。
3. 页面顶部用一行小字写明快捷键：空格=贪睡 5 分钟，Esc=关闭闹铃。

功能：
1. 时间显示：数字时钟 + 指针表盘，两种可切换；用系统时间，每秒刷新。
2. 蜻蜓：用内联 SVG 画一只蜻蜓停在表盘边缘，翅膀随秒针每秒扇动一次；
   闹铃响起时蜻蜓绕表盘盘旋一圈。
3. 闹钟：可添加、删除多个闹钟时间（时:分，24 小时制）；到点触发。
   触发时页面高亮闪烁 + 蜂鸣声由弱到强；提供「贪睡 5 分钟」和「关闭」两个按钮。
4. 交互：用时间输入框添加闹钟；空格贪睡、Esc 关闭。
5. 视觉：深色主题，蜻蜓要有轻量感（翅膀半透明、扇动用 CSS 动画）。

输出格式（严格遵守）：
- 只输出这一个文件的完整内容：从 <!DOCTYPE html> 开始，到 </html> 结束；
- 除了这一个代码块，不要写任何解释、不要写"以下是代码"之类的引导语；
- 必须写完整并闭合。若长度紧张，先精简功能（例如简化动画细节），但文件必须闭合、必须能直接双击运行。"""


def stats():
    try:
        with urllib.request.urlopen(PROXY + "/stats", timeout=10) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}


def strip_fences(text):
    t = text.strip()
    m = re.search(r"```(?:html)?\s*(.*?)```", t, re.S)
    if m:
        return m.group(1).strip()
    return t


def main():
    print("stats before:", json.dumps(stats(), ensure_ascii=False))
    body = {"messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 4096, "temperature": 0.7, "stream": False}
    req = urllib.request.Request(PROXY + "/api/chat",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.load(r)
    el = time.time() - t0
    raw = (resp["choices"][0].get("message") or {}).get("content") or ""
    finish = resp["choices"][0].get("finish_reason")
    html = strip_fences(raw)

    guard_hit = "[交付检查未通过" in raw
    unclosed_fence = raw.count("```") % 2 == 1
    closed = html.rstrip().lower().endswith("</html>")
    externals = sorted(set(re.findall(r"https?://[^\s\"'<>)]+", html)))
    media = sorted(set(re.findall(r"[\w\-/]+\.(?:mp3|wav|ogg|png|jpe?g|gif|woff2?|ttf)", html, re.I)))
    has_svg = "<svg" in html.lower()
    svg_closed = ("</svg>" in html.lower()) if has_svg else None

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html + "\n")

    print("elapsed        : %.1f s" % el)
    print("finish_reason  : %s" % finish)
    print("reply chars    : %d" % len(raw))
    print("file bytes     : %d  -> %s" % (os.path.getsize(OUT), OUT))
    print("closed </html> : %s" % closed)
    print("guard marker   : %s" % guard_hit)
    print("odd fences     : %s" % unclosed_fence)
    print("inline svg     : %s (closed: %s)" % (has_svg, svg_closed))
    print("external urls  : %s" % (externals or "none"))
    print("media refs     : %s" % (media or "none"))
    print("stats after    :", json.dumps(stats(), ensure_ascii=False))
    ok = closed and not guard_hit and not unclosed_fence and not externals and not media and len(html) > 1500
    print("VERDICT        : %s" % ("PASS - artifact is closed, self-contained, usable" if ok
                                   else "FAIL - see the flags above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

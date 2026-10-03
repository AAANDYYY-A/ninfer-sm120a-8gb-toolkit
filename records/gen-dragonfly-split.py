#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Two-step generation of the dragonfly alarm clock (fits the pool-8192 => 4096 cap).

Step 1: skeleton + CSS only, closed HTML, empty <script></script> placeholder.
Step 2: send that HTML back and ask ONLY for the <script> block; splice it in.
Then run the same closure / self-containment checks as the one-shot version.
"""
import json
import os
import re
import sys
import time
import urllib.request

PROXY = "http://127.0.0.1:8097"
OUT = r"C:\Users\DDJOI\Documents\deepseek-harness\default-workspace\dragonfly-alarm.html"

STEP1 = """只写一个「蜻蜓闹钟」单文件 HTML 的骨架与样式：从 <!DOCTYPE html> 开始，到 </html> 完整闭合。
必须自包含：不要任何外部资源（无 CDN、无外链字体/图片/音频/JS/CSS），样式全部内联。
内容包含：数字时钟显示、内联 SVG 指针表盘 + 一只停在表盘边缘的蜻蜓、闹钟列表区与添加闹钟的时间输入框、
「贪睡 5 分钟」「关闭」两个按钮、顶部一行说明快捷键的小字（空格=贪睡，Esc=关闭）。深色主题，
蜻蜓翅膀半透明并用 CSS 动画扇动。
不要写任何 JavaScript：在 </body> 之前留一个空的 <script></script> 占位。
只输出这一个完整闭合的 HTML 代码块，不要解释。"""

STEP2 = """下面是我已有的「蜻蜓闹钟」HTML。请只输出要插入到它 </body> 之前的那个 <script> 块
（包含 <script> 与 </script> 标签本身），实现：
1. 每秒用系统时间刷新数字时钟，并驱动表盘时针/分针/秒针角度；
2. 蜻蜓翅膀随秒针每秒扇动一次（切换 CSS 类即可），闹铃响起时蜻蜓绕表盘盘旋一圈；
3. 闹钟：读取输入框时间加入列表、可删除、到点触发；触发时页面高亮闪烁；
4. 提示音用 WebAudio 现场合成（OscillatorNode + GainNode，音量由弱到强，不要音频文件）；
5. 「贪睡 5 分钟」按钮与 Esc 键 = 关闭/贪睡；空格键 = 贪睡 5 分钟；
6. 闹钟列表存 localStorage，刷新后恢复；页面加载时启动定时器。
不要重复输出 HTML 结构，不要解释，不要使用任何外部库。

--- HTML 如下 ---
"""


def ask(content, max_tokens=4096, temperature=0.7):
    body = {"messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens, "temperature": temperature, "stream": False}
    req = urllib.request.Request(PROXY + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.load(r)
    ch = resp["choices"][0]
    text = (ch.get("message") or {}).get("content") or ""
    return text, ch.get("finish_reason"), time.time() - t0


def unfence(text):
    m = re.search(r"```(?:html|javascript|js)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def main():
    print("--- step 1: skeleton + CSS ---")
    raw1, fin1, el1 = ask(STEP1)
    html = unfence(raw1)
    print("  %.1f s | finish=%s | chars=%d | closed=%s"
          % (el1, fin1, len(html), html.rstrip().lower().endswith("</html>")))

    print("--- step 2: the script block ---")
    raw2, fin2, el2 = ask(STEP2 + html)
    script = unfence(raw2)
    if "<script" not in script.lower():
        script = "<script>\n" + script + "\n</script>"
    print("  %.1f s | finish=%s | chars=%d | has <script>=%s"
          % (el2, fin2, len(script), "<script" in script.lower()))

    # splice the script in place of the empty placeholder / before </body>
    if re.search(r"<script>\s*</script>", html, re.I):
        html = re.sub(r"<script>\s*</script>", script, html, count=1, flags=re.I)
    else:
        html = re.sub(r"</body>", script + "\n</body>", html, count=1, flags=re.I)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html if html.endswith("\n") else html + "\n")

    externals = sorted(set(re.findall(r"https?://[^\s\"'<>)]+", html)))
    media = sorted(set(re.findall(r"[\w\-/]+\.(?:mp3|wav|ogg|png|jpe?g|gif|woff2?|ttf)", html, re.I)))
    checks = {
        "closed </html>": html.rstrip().lower().endswith("</html>"),
        "has script logic": ("setInterval" in html) or ("requestAnimationFrame" in html),
        "has webaudio": ("AudioContext" in html) or ("webkitAudioContext" in html),
        "has dragonfly svg": "<svg" in html.lower() and "</svg>" in html.lower(),
        "no external urls": not externals,
        "no media files": not media,
        "fits a file": len(html) > 1500,
    }
    print("\n--- checks on the assembled file (%d bytes) ---" % os.path.getsize(OUT))
    for k, v in checks.items():
        print("  %-18s %s" % (k, "PASS" if v else "FAIL"))
    print("  external urls     : %s" % (externals or "none"))
    print("  media refs        : %s" % (media or "none"))
    print("  file              : %s" % OUT)
    ok = all(checks.values())
    print("VERDICT: %s" % ("PASS - open it by double-click" if ok else "FAIL - see flags"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

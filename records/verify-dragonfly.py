#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify the assembled dragonfly alarm artifact: structure + embedded JS syntax.

'has a file' is not 'the file works' (doc 04 section 1, item 2), so:
  * closure and self-containment (w3.org namespace URIs are NOT external resources)
  * the feature surface the prompt asked for
  * the <script> body is handed to node --check, i.e. the JS actually parses
"""
import os
import re
import subprocess
import sys

HTML = r"C:\Users\DDJOI\Documents\deepseek-harness\default-workspace\dragonfly-alarm.html"
NODE = r"C:\Users\DDJOI\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
TMPJS = os.path.join(os.environ.get("TEMP", "."), "dragonfly-extracted.js")


def main():
    html = open(HTML, encoding="utf-8").read()
    low = html.lower()

    urls = [u for u in re.findall(r"https?://[^\s\"'<>)]+", html) if "w3.org" not in u]
    media = re.findall(r"[\w\-/]+\.(?:mp3|wav|ogg|png|jpe?g|gif|woff2?|ttf)", html, re.I)
    links = re.findall(r"<link\b[^>]*>", html, re.I)
    ext_scripts = re.findall(r"<script[^>]*\bsrc\s*=", html, re.I)

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S | re.I)
    js = "\n;\n".join(s for s in scripts if s.strip())
    open(TMPJS, "w", encoding="utf-8", newline="\n").write(js)

    checks = [
        ("closed </html>", html.rstrip().lower().endswith("</html>")),
        ("no external urls", not urls),
        ("no media files", not media),
        ("no <link> tags", not links),
        ("no external <script src>", not ext_scripts),
        ("inline svg dragonfly", "<svg" in low and "</svg>" in low),
        ("css wing animation", "@keyframes" in low and ("wing" in low or "flap" in low)),
        ("clock ticks每秒", "setInterval" in html),
        ("webaudio beep", "audiocontext" in low),
        ("alarm list + storage", "localstorage" in low),
        ("snooze 5 min", "snooze" in low or "贪睡" in html),
        ("Esc / Space keys", "escape" in low and ("keydown" in low)),
        ("time input", 'type="time"' in low or "type='time'" in low),
        ("closing buttons", "关闭" in html),
    ]
    print("file  : %s (%d bytes, %d lines)" % (HTML, len(html.encode("utf-8")), html.count("\n") + 1))
    print("js    : %d chars extracted" % len(js))
    print()
    bad = 0
    for name, ok in checks:
        print("  %-26s %s" % (name, "PASS" if ok else "FAIL"))
        bad += 0 if ok else 1
    print()
    print("  external urls           : %s" % (urls or "none"))
    print("  media refs              : %s" % (media or "none"))
    print("  <link> tags             : %s" % (links or "none"))
    print("  <script src=...>        : %s" % (ext_scripts or "none"))

    print("\n--- node --check on the embedded JS ---")
    r = subprocess.run([NODE, "--check", TMPJS], capture_output=True, text=True)
    print("  exit=%d" % r.returncode)
    if r.stdout.strip():
        print("  stdout:", r.stdout.strip()[:400])
    if r.stderr.strip():
        print("  stderr:", r.stderr.strip()[:800])
    js_ok = (r.returncode == 0)
    print("  JS parses               : %s" % ("PASS" if js_ok else "FAIL"))

    verdict = (bad == 0 and js_ok)
    print("\nVERDICT: %s" % ("PASS - the artifact is closed, self-contained and its JS parses"
                            if verdict else "FAIL - see the flags above"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())

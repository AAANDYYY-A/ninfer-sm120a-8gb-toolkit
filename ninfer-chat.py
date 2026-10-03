#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local chat window + delivery guard for the NInfer engine.  (v4, 2026-10-03)

WHY THIS EXISTS
  The engine serves only /v1/*, has no built-in web assets (GET / -> 404) and
  sends no CORS headers, so a chat page cannot call it from a file:// origin.
  This script serves the page AND proxies server-side => one same origin, no CORS.

WHAT v4 ADDED (after receiving docs\\04-卡死与循环的防治.md)
  1) THE DOC'S §1-11 CRASH RECIPE IS NOW IMPOSSIBLE FROM THIS PATH.
     "ENGINE_DEAD: client max_tokens (32,000) >> pool tokens => the output lease
      cannot get pages => worker crash 'Paged KV reservation invariant was
      violated', while /v1/models still answers 200."
     Our pool is 8,192 tokens, so requests are clamped to --max-tokens-cap
     (default 4096 = half the pool, leaving room for the prompt's residency),
     the page's input box cannot ask for more, and every clamp is logged.
  2) THE §3-L3 DELIVERY GUARD (the doc's "only layer that can catch a silent
     model-side failure"): judge the COMPLETE answer, and on failure re-send in
     the SAME response with the doc's correction text, at most --guard-retries
     times.  States implemented: TRUNCATED (finish_reason=length, unclosed ```
     fence, <svg> without </svg>) and FIXED_POINT (byte-identical to the previous
     answer after whitespace normalisation).  EMPTY is available but OFF by
     default (--guard-empty-min 0): a 400-character floor would misjudge short
     chat replies such as "收到".
  3) Counters required by the doc's §3 "接收方要实现什么": guard_fired /
     rescued_by_retry / undelivered_final, visible on GET /stats.
  4) An off switch: --guard off makes behaviour byte-for-byte the pre-guard path.

WHAT v2/v3 ADDED (kept)
  step-by-step log on the page, window.onerror banner, 45 s watchdog, non-stream
  fallback, IME-safe Enter.  Note: never name a page global after a window
  built-in -- `var history = []` silently fails to shadow window.history and
  `history.push` throws "history.push is not a function" (that bug cost a round
  trip; the page uses `msgs`).

DEPENDENCIES: none. Python standard library only.

USAGE
  python ninfer-chat.py [--port 8097] [--engine 127.0.0.1:8095] [--model qwen3.8-27b]
                        [--max-tokens-cap 4096] [--guard on|off] [--guard-retries 2]
                        [--guard-empty-min 0]
"""

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CORRECTION = (
    "【交付检查未通过 · 第 {n} 次重试】{which}。\n"
    "现在只做一件事：立刻输出完整且闭合的产物；空间不够就先精简但必须闭合；"
    "不许只写计划、不许写“同上”、不许重复上一轮的措辞。"
    "若上一轮的方案已完成，就换一个不同的点。"
)

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本地 AI 对话 · qwen3.8-27b</title>
<script>
/* before anything else: make even a load-time script error visible on screen */
window.__fatal = function (msg) {
  var d = document.createElement('div');
  d.style.cssText = 'margin:8px 16px;padding:10px 14px;border-radius:8px;background:#4a1f22;' +
                    'color:#ffd7d7;font:13px/1.6 Consolas,monospace;white-space:pre-wrap';
  d.textContent = '页面脚本错误：' + msg + '\n请把这一行发给管理员。';
  (document.body || document.documentElement).appendChild(d);
};
window.onerror = function (m, s, l, c) { window.__fatal(m + '  @' + l + ':' + c); };
window.addEventListener('unhandledrejection', function (e) {
  window.__fatal('未处理的 Promise 拒绝：' + (e.reason && e.reason.message ? e.reason.message : e.reason));
});
</script>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#0f1115;
         color:#e8e8ea; height:100vh; display:flex; flex-direction:column; }
  header { padding:10px 16px; background:#161a22; display:flex; align-items:center; gap:12px;
           border-bottom:1px solid #262b36; flex-wrap:wrap; }
  header h1 { font-size:14px; margin:0; font-weight:600; color:#cfd4df; }
  #status { font-size:12px; padding:2px 10px; border-radius:10px; background:#333; color:#ddd; }
  #status.ok { background:#14432b; color:#6ee7a0; }
  #status.bad { background:#4a1f22; color:#f38a8a; }
  header label { font-size:12px; color:#8a93a6; display:flex; align-items:center; gap:4px; }
  header input[type=number] { width:80px; background:#0f1115; color:#e8e8ea; border:1px solid #2a3142;
                              border-radius:6px; padding:4px 6px; font-size:12px; }
  header button { background:#2a3040; color:#cfd4df; border:none; border-radius:6px;
                  padding:6px 12px; cursor:pointer; font-size:12px; }
  header button:hover { background:#39415a; }
  #steps { padding:4px 16px; background:#12151c; border-bottom:1px solid #1d222c;
           font:11px/1.7 Consolas,monospace; color:#7f8aa0; white-space:pre-wrap; }
  #log { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:82%; padding:10px 14px; border-radius:12px; white-space:pre-wrap;
         word-break:break-word; line-height:1.7; font-size:14px; }
  .user { align-self:flex-end; background:#2b4b8f; }
  .assistant { align-self:flex-start; background:#1d2230; border:1px solid #2a3142; }
  .err { align-self:flex-start; background:#3a1d1f; border:1px solid #5a2a2e; color:#f0b3b3;
         font-size:13px; max-width:100%; white-space:pre-wrap; }
  .meta { font-size:11px; color:#8a93a6; margin-top:6px; }
  .hint { color:#8a93a6; font-size:13px; text-align:center; margin-top:60px; line-height:2; }
  footer { padding:12px 16px; background:#161a22; border-top:1px solid #262b36; display:flex; gap:10px; }
  #input { flex:1; resize:none; height:70px; background:#0f1115; color:#e8e8ea; border:1px solid #2a3142;
           border-radius:8px; padding:10px; font-size:14px; font-family:inherit; }
  #input:focus { outline:none; border-color:#3b6fd4; }
  #send { width:92px; background:#3b6fd4; color:#fff; border:none; border-radius:8px; font-size:14px; cursor:pointer; }
  #stop { width:70px; background:#5a2a2e; color:#f0b3b3; border:none; border-radius:8px; font-size:13px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
</style>
</head>
<body>
<header>
  <h1>本地 AI 对话 · qwen3.8-27b</h1>
  <span id="status">检测中…</span>
  <label title="池 8192 token；上限被钳制在池的一半以防引擎输出租约崩溃（手册 §1-11）">回答上限
    <input id="maxtok" type="number" min="16" max="4096" step="64" value="1024"> token</label>
  <label>温度 <input id="temp" type="number" min="0" max="2" step="0.1" value="0.7"></label>
  <button id="diag">诊断</button>
  <button id="reset">清空对话</button>
</header>
<div id="steps">步骤日志：等待操作…</div>
<div id="log"><div class="hint" id="hint">正在连接本地引擎…<br>
  <span style="font-size:12px">若一直红色，说明引擎没在跑：双击 chat-web.bat（或 start-ptq1-mtp-8gb.bat）</span></div></div>
<footer>
  <textarea id="input" placeholder="输入消息：Enter 发送，Shift+Enter 换行"></textarea>
  <button id="send">发送</button>
  <button id="stop" disabled>停止</button>
</footer>
<script>
/* NOTE: never name a page global after a window built-in. `var history = []`
   silently fails to shadow window.history and `history.push` throws
   "history.push is not a function". Keep `msgs`. */
var msgs = [];
var controller = null;
var elLog = document.getElementById('log');
var elIn = document.getElementById('input');
var elSend = document.getElementById('send');
var elStop = document.getElementById('stop');
var elStatus = document.getElementById('status');
var elSteps = document.getElementById('steps');
var elHint = document.getElementById('hint');

function steps(text) {
  elSteps.textContent = '步骤日志：[' + new Date().toLocaleTimeString() + '] ' + text;
}
function setStatus(ok, text) { elStatus.textContent = text; elStatus.className = ok ? 'ok' : 'bad'; }
function bubble(cls, text) {
  var d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  elLog.appendChild(d);
  elLog.scrollTop = elLog.scrollHeight;
  return d;
}
function meta(node, text) {
  var m = document.createElement('div');
  m.className = 'meta';
  m.textContent = text;
  node.appendChild(m);
}
function busy(on) { elSend.disabled = on; elStop.disabled = !on; elSend.textContent = on ? '生成中' : '发送'; }

function checkHealth() {
  fetch('/health', {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(j){
    if (j.engine) { setStatus(true, '引擎就绪 · ' + j.model); if (elHint) { elHint.remove(); elHint = null; } }
    else { setStatus(false, '引擎未启动'); }
  }).catch(function(e){ setStatus(false, '代理异常: ' + e.message); });
}

function send() {
  var text = elIn.value.trim();
  steps('点击发送：' + (text ? '文本 ' + text.length + ' 字' : '文本为空') +
        (elSend.disabled ? ' · 按钮当前为禁用态，已忽略' : ''));
  if (!text || elSend.disabled) return;
  elIn.value = '';
  if (elHint) { elHint.remove(); elHint = null; }
  bubble('user', text);
  msgs.push({role:'user', content:text});

  var node = bubble('assistant', '');
  var acc = '';
  var gotAnyByte = false;
  var t0 = performance.now();
  var maxtok = parseInt(document.getElementById('maxtok').value, 10) || 1024;
  if (maxtok > 4096) { maxtok = 4096; steps('上限被钳制为 4096（池 8192 的一半，手册 §1-11）'); }
  var temp = parseFloat(document.getElementById('temp').value);
  if (isNaN(temp)) temp = 0.7;

  var canStream = !!(window.ReadableStream && window.TextDecoder);
  var body = { messages: msgs, max_tokens: maxtok, temperature: temp, stream: canStream };
  if (!canStream) body.stream = false;

  busy(true);
  steps('POST /api/chat（' + (canStream ? '流式' : '非流式降级') + '，经代理转发到引擎）…');
  controller = (typeof AbortController === 'function') ? new AbortController() : null;

  var watchdog = setTimeout(function () {
    if (controller) { try { controller.abort(); } catch (e) {} }
    steps('看门狗：45 秒无任何响应，已中止');
    bubble('err', '请求 45 秒没有任何响应，已自动中止。\n请确认引擎控制台还开着，并看窗口顶部的“步骤日志”。');
    busy(false); controller = null;
  }, 45000);

  function done(note) {
    clearTimeout(watchdog);
    var secs = (performance.now() - t0) / 1000;
    if (acc) msgs.push({role:'assistant', content:acc});
    meta(node, '完成 · ' + acc.length + ' 字 · ' + secs.toFixed(1) + ' s'
              + (secs > 0 && acc ? ' · ' + (acc.length / secs).toFixed(1) + ' 字/秒' : '')
              + (note ? ' · ' + note : ''));
    busy(false); controller = null;
  }

  fetch('/api/chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    signal: controller ? controller.signal : undefined,
    body: JSON.stringify(body)
  }).then(function(resp){
    steps('已收到响应头：HTTP ' + resp.status + (resp.ok ? '' : '（失败）'));
    if (!resp.ok) {
      return resp.text().then(function(t){ throw new Error('HTTP ' + resp.status + ' ' + t.slice(0, 300)); });
    }
    if (!canStream || !resp.body || typeof resp.body.getReader !== 'function') {
      steps('本浏览器不支持流式读取，改用整段返回');
      return resp.json().then(function(j){
        var m = j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
        if (!m) throw new Error('响应里没有内容：' + JSON.stringify(j).slice(0, 300));
        acc = m; node.textContent = m; done('非流式');
      });
    }
    var reader = resp.body.getReader();
    var dec = new TextDecoder('utf-8');
    var buf = '';
    function pump() {
      return reader.read().then(function(r){
        if (r.done) { steps('流结束：共收到 ' + acc.length + ' 字'); done(gotAnyByte ? '' : '空响应'); return; }
        gotAnyByte = true;
        clearTimeout(watchdog);
        buf += dec.decode(r.value, {stream:true});
        var lines = buf.split('\n');
        buf = lines.pop();
        lines.forEach(function(line){
          line = line.trim();
          if (!line || line.indexOf('data:') !== 0) return;
          var payload = line.slice(5).trim();
          if (payload === '[DONE]') return;
          try {
            var j = JSON.parse(payload);
            var ch = j.choices && j.choices[0];
            var piece = ch && ch.delta && ch.delta.content;
            if (piece) { acc += piece; node.textContent = acc; elLog.scrollTop = elLog.scrollHeight; }
          } catch (e) { /* partial JSON, the next chunk completes it */ }
        });
        return pump();
      });
    }
    return pump();
  }).catch(function(e){
    clearTimeout(watchdog);
    if (e && e.name === 'AbortError') {
      if (acc) msgs.push({role:'assistant', content:acc});
      meta(node, '已停止 · 已收到 ' + acc.length + ' 字');
      steps('已中止');
    } else {
      var m = (e && e.message) ? e.message : String(e);
      steps('请求失败：' + m);
      bubble('err', '请求失败：' + m +
        '\n\n排查：1) 引擎控制台还开着吗 2) 上面“步骤日志”停在哪一步，把那一行发给管理员');
    }
    busy(false); controller = null;
  });
}

elSend.onclick = function () { try { send(); } catch (e) { window.__fatal('send() 抛错：' + e.message); } };
elStop.onclick = function () { if (controller) controller.abort(); };
elIn.addEventListener('keydown', function(e){
  if (e.key === 'Enter' && !e.shiftKey) {
    if (e.isComposing || e.keyCode === 229) { steps('输入法组词中的回车已忽略'); return; }
    e.preventDefault();
    try { send(); } catch (err) { window.__fatal('send() 抛错：' + err.message); }
  }
});
document.getElementById('reset').onclick = function(){
  msgs = [];
  elLog.innerHTML = '';
  var h = document.createElement('div');
  h.className = 'hint';
  h.textContent = '对话已清空，可以重新开始。';
  elLog.appendChild(h);
  steps('已清空对话');
};
document.getElementById('diag').onclick = function(){
  steps('开始诊断：先看 /health，再发一条固定测试消息');
  fetch('/health', {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(j){
    steps('诊断：/health → engine=' + j.engine + '，池上限 ' + (j.max_tokens_cap || '?') + '，护栏 ' + (j.guard ? 'on' : 'off'));
    elIn.value = '回答两个字：收到';
    send();
  }).catch(function(e){ steps('诊断失败：' + e.message); });
};
checkHealth();
setInterval(checkHealth, 15000);
elIn.focus();
steps('页面已就绪（' + (window.ReadableStream ? '支持流式' : '不支持流式，将降级') + '）');
</script>
</body>
</html>
"""


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def judge(text, finish_reason, prev_answer, empty_min):
    """Return a state name, or None when the answer passes.  Doc §3-L3 states."""
    # AGENT TURN: an assistant message that carries tool_calls and no prose is the
    # NORMAL shape of an agent step, not an EMPTY delivery. Judging it as EMPTY made
    # the guard "correct" a perfectly good tool call (measured 2026-10-03).
    if finish_reason == "tool_calls":
        return None
    t = (text or "").strip()
    if not t:
        return "EMPTY"
    if finish_reason == "length":
        return "TRUNCATED"
    if t.count("```") % 2 == 1:
        return "TRUNCATED"
    if "<svg" in t and "</svg>" not in t:
        return "TRUNCATED"
    if empty_min and len(t) < empty_min:
        return "EMPTY"
    if prev_answer and len(t) > 20 and normalize(t) == normalize(prev_answer):
        return "FIXED_POINT"
    return None


def prev_assistant(messages):
    for m in reversed(messages[:-1] if messages else []):
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            return m["content"]
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine = "127.0.0.1:8095"
    model = "qwen3.8-27b"
    timeout = 1800
    max_tokens_cap = 4096
    guard = True
    guard_retries = 2
    guard_empty_min = 0
    api_key = ""            # set when the engine was started with --api-key
    stats = {"requests": 0, "guard_fired": 0, "rescued_by_retry": 0,
             "undelivered_final": 0, "clamped": 0}

    def _up_headers(self, extra=None):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        if extra:
            h.update(extra)
        return h

    def log_message(self, fmt, *args):
        sys.stderr.write("[chat] %s - %s\n" % (self.address_string(), fmt % args))
        sys.stderr.flush()

    def _note(self, text):
        sys.stderr.write("[chat] %s\n" % text)
        sys.stderr.flush()

    def _send(self, code, ctype, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _engine_ok(self):
        try:
            req = urllib.request.Request("http://%s/v1/models" % self.engine,
                                         headers=self._up_headers())
            with urllib.request.urlopen(req, timeout=8) as r:
                ids = [m.get("id") for m in json.load(r).get("data", [])]
                return True, (ids[0] if ids else self.model)
        except Exception:
            return False, self.model

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif path == "/health":
            ok, model = self._engine_ok()
            body = json.dumps({"engine": ok, "model": model, "guard": self.guard,
                               "max_tokens_cap": self.max_tokens_cap,
                               "note": "/v1/models 200 does not prove the worker is alive "
                                       "(see 04-卡死与循环的防治.md §1-11)"}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif path == "/stats":
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(self.stats, indent=1).encode("utf-8"))
        elif path == "/v1/models":
            # passthrough so agent clients that probe the standard path work
            try:
                req = urllib.request.Request("http://%s/v1/models" % self.engine,
                                             headers=self._up_headers())
                with urllib.request.urlopen(req, timeout=10) as r:
                    self._send(200, "application/json; charset=utf-8", r.read())
            except Exception as exc:
                self._send(502, "application/json; charset=utf-8",
                           json.dumps({"error": "engine unreachable: %s" % exc}).encode("utf-8"))
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def _chunk(self, data):
        self.wfile.write(("%X\r\n" % len(data)).encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _emit_text(self, s):
        frame = ('data: ' + json.dumps({"choices": [{"delta": {"content": s}, "index": 0,
                 "finish_reason": None}]}, ensure_ascii=False) + "\n\n").encode("utf-8")
        self._chunk(frame)

    def _upstream_once(self, payload, streaming, emit):
        """One engine call.  Returns (text, finish_reason, http_code, detail)."""
        req = urllib.request.Request(
            "http://%s/v1/chat/completions" % self.engine,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._up_headers({"Accept": "text/event-stream"}),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            return None, None, exc.code, exc.read().decode("utf-8", "replace")[:500]
        except Exception as exc:
            return None, None, 0, str(exc)

        if not streaming:
            try:
                data = resp.read()
            finally:
                resp.close()
            self._last_raw_body = data  # verbatim passthrough (keeps tool_calls)
            try:
                j = json.loads(data)
                ch = j["choices"][0]
                return (ch.get("message", {}).get("content") or ""), ch.get("finish_reason"), 200, ""
            except Exception as exc:
                return None, None, 200, "unparsable body: %s" % exc

        text = []
        finish = None
        try:
            for raw in resp:
                if not raw:
                    continue
                s = raw.decode("utf-8", "replace").strip()
                terminal = s.startswith("data:") and s[5:].strip() == "[DONE]"
                # NEVER forward the engine's [DONE]: ours has to be the last frame,
                # after any guard retry. Forwarding it made the client stop reading
                # (and hang up) before the retry could be delivered -- measured.
                if emit and not terminal and not self.client_gone:
                    try:
                        emit(raw.replace(b"\r\n", b"\n"))
                    except (BrokenPipeError, ConnectionResetError, socket.timeout):
                        self.client_gone = True
                        self._note("CLIENT-DISCONNECT while forwarding; the guard still evaluates")
                if terminal or not s.startswith("data:"):
                    continue
                body = s[5:].strip()
                if not body:
                    continue
                try:
                    ch = json.loads(body)["choices"][0]
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        text.append(piece)
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
                except Exception:
                    pass
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return "".join(text), finish, 200, ""

    def do_POST(self):
        path = self.path.split("?")[0]
        # /v1/chat/completions is the OpenAI-compatible path every agent client uses;
        # /api/chat is what this page posts to. Both must be accepted or no agent
        # client can point at this proxy (measured: 404 before this fix).
        if path not in ("/api/chat", "/v1/chat/completions"):
            self._send(404, "text/plain", b"not found")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            req = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._note("BAD-REQUEST %s" % exc)
            self._send(400, "application/json; charset=utf-8",
                       json.dumps({"error": "bad request: %s" % exc}).encode("utf-8"))
            return

        # OpenAI semantics: stream defaults to FALSE. The page always sets it
        # explicitly, so defaulting to non-stream is what makes ordinary agent
        # clients (which omit the field) get JSON instead of SSE.
        want_stream = bool(req.get("stream", False))
        messages = list(req.get("messages") or [])
        prev = prev_assistant(messages)

        # ---- the doc's §1-11 rule: max_tokens must not exceed the KV pool ----
        asked = req.get("max_tokens")
        cap = self.max_tokens_cap
        if asked is None:
            max_tokens = cap
            self._note("max_tokens not given -> using the pool-safe cap %d" % cap)
        else:
            max_tokens = int(asked)
            if max_tokens > cap:
                self.stats["clamped"] += 1
                self._note("CLAMP max_tokens %d -> %d (pool 8192; doc §1-11 crash recipe)" % (max_tokens, cap))
                max_tokens = cap
        if max_tokens < 1:
            max_tokens = 1

        temp = req.get("temperature")
        temp = 0.7 if temp is None else float(temp)

        self.stats["requests"] += 1
        chars = sum(len(m.get("content") or "") for m in messages)
        self._note("REQUEST body=%d bytes, messages=%d, chars=%d, stream=%s, max_tokens=%d"
                   % (len(raw), len(messages), chars, want_stream, max_tokens))

        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                   "temperature": temp, "stream": want_stream}
        # AGENT SUPPORT: pass the tool/agent-related fields straight through. Without
        # this the proxy silently stripped `tools`, and no agent client could work.
        for key in ("tools", "tool_choice", "parallel_tool_calls", "stop",
                    "top_p", "top_k", "presence_penalty", "seed", "response_format"):
            if req.get(key) is not None:
                payload[key] = req[key]
                if key in ("tools", "tool_choice"):
                    self._note("AGENT passthrough: %s=%s" % (key, json.dumps(req[key])[:200]))

        # Non-streaming: no guard needed mid-flight, judge then retry as a whole.
        if not want_stream:
            attempt = 0
            text, finish = "", None
            while True:
                text, finish, code, detail = self._upstream_once(payload, False, None)
                if code != 200 or text is None:
                    self._note("UPSTREAM FAILED code=%s %s" % (code, detail))
                    self._send(code or 502, "application/json; charset=utf-8",
                               json.dumps({"error": detail or "engine unreachable"}).encode("utf-8"))
                    return
                state = judge(text, finish, prev, self.guard_empty_min) if self.guard else None
                if state is None or attempt >= self.guard_retries:
                    if state is not None:
                        self.stats["undelivered_final"] += 1
                        self._note("GUARD undelivered_final state=%s" % state)
                    break
                self.stats["guard_fired"] += 1
                attempt += 1
                self._note("GUARD fired state=%s attempt=%d" % (state, attempt))
                payload["messages"] = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": CORRECTION.format(n=attempt, which=state)},
                ]
            if attempt and judge(text, finish, prev, self.guard_empty_min) is None:
                self.stats["rescued_by_retry"] += 1
            # Return the engine's own JSON verbatim: rebuilding it here used to drop
            # tool_calls, which silently broke every agent client (measured).
            body = getattr(self, "_last_raw_body", None)
            if not body:
                body = json.dumps({"choices": [{"index": 0, "finish_reason": finish,
                                                "message": {"role": "assistant", "content": text}}],
                                   "model": self.model, "object": "chat.completion"}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return

        # Streaming: forward attempt 1 (and any retry) inside the SAME response,
        # with the doc's correction text appended between attempts.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        attempt = 0
        self.client_gone = False
        try:
            while True:
                text, finish, code, detail = self._upstream_once(payload, True, self._chunk)
                if code != 200 or text is None:
                    self._note("UPSTREAM FAILED code=%s %s" % (code, detail))
                    self._emit_text("\n[代理] 引擎返回错误 %s：%s\n" % (code, detail))
                    break
                state = judge(text, finish, prev, self.guard_empty_min) if self.guard else None
                if state is None:
                    if attempt:
                        self.stats["rescued_by_retry"] += 1
                    break
                self.stats["guard_fired"] += 1
                if attempt >= self.guard_retries:
                    self.stats["undelivered_final"] += 1
                    self._note("GUARD undelivered_final state=%s" % state)
                    self._emit_text("\n[交付检查未通过 · %s · 已重试 %d 次]\n" % (state, attempt))
                    break
                attempt += 1
                self._note("GUARD fired state=%s attempt=%d" % (state, attempt))
                self._emit_text("\n\n[交付检查未通过：%s · 第 %d 次重试]\n\n" % (state, attempt))
                payload["messages"] = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": CORRECTION.format(n=attempt, which=state)},
                ]
            # our own terminal frame, once, after every attempt has been delivered
            if not self.client_gone:
                self._chunk(b"data: [DONE]\n\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, socket.timeout) as exc:
            self._note("CLIENT-DISCONNECT (%s)" % exc)
        except Exception as exc:
            self._note("STREAM-ERROR %s" % exc)
        finally:
            pass


def main():
    ap = argparse.ArgumentParser(description="Local chat window + delivery guard for the NInfer engine")
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--engine", default="127.0.0.1:8095")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--api-key", default=os.environ.get("NINFER_API_KEY"),
                    help="engine's --api-key value; also read from NINFER_API_KEY")
    ap.add_argument("--max-tokens-cap", type=int, default=4096,
                    help="hard ceiling for max_tokens; must stay below the engine's KV pool (8192 here)")
    ap.add_argument("--guard", choices=["on", "off"], default="on",
                    help="L3 delivery guard from 04-卡死与循环的防治.md")
    ap.add_argument("--guard-retries", type=int, default=2)
    ap.add_argument("--guard-empty-min", type=int, default=0,
                    help="flag EMPTY below this many characters (0 = off; a 400 floor would "
                         "misjudge short chat replies)")
    args = ap.parse_args()

    Handler.engine = args.engine
    Handler.model = args.model
    Handler.api_key = args.api_key or ""
    Handler.max_tokens_cap = args.max_tokens_cap
    Handler.guard = (args.guard == "on")
    Handler.guard_retries = args.guard_retries
    Handler.guard_empty_min = args.guard_empty_min

    # Refuse to become a SECOND listener on the same port. On Windows
    # SO_REUSEADDR lets two sockets bind the same port, and then the OLD instance
    # answers the browser while the new one looks healthy (seen 2026-10-03).
    try:
        with urllib.request.urlopen("http://%s:%d/health" % (args.host, args.port), timeout=3) as r:
            who = r.read(200).decode("utf-8", "replace")
        print("[REFUSE] something is already serving http://%s:%d/ :" % (args.host, args.port))
        print("         %s" % who)
        print("         Close that window first, or start this one with --port N.")
        return 2
    except Exception:
        pass  # nothing there: good

    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)

    print("=" * 70)
    print(" NInfer 本地聊天窗口 + 交付护栏 v4")
    print("   打开这个地址聊天 : http://%s:%d/" % (args.host, args.port))
    print("   转发的引擎       : http://%s/v1  (model %s)" % (args.engine, args.model))
    print("   max_tokens 上限  : %d   <- 引擎池 8192；手册 §1-11 要求 max_tokens <= 池" % args.max_tokens_cap)
    print("   交付护栏         : %s (retries=%d, empty_min=%d)" %
          ("on" if Handler.guard else "off", args.guard_retries, args.guard_empty_min))
    print("   计数             : http://%s:%d/stats" % (args.host, args.port))
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[chat] bye")


if __name__ == "__main__":
    main()

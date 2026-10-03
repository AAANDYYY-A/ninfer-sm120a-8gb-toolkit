#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""API usage dashboard for the NInfer engine (stdlib only, no external assets).

DATA SOURCES
  1) the engine's structured request log  (--request-log-jsonl FILE)
       server_start  : hardware / config snapshot
       request_start : per-request request info
       request_done  : result (tokens, finish_reason, tool calls), timings
                       (ttft / prefill / decode), speculative (MTP draft+accept)
       throughput    : 5 s interval counters (used for the live sparkline)
  2) the engine's stats port (--stats-port N), all需要 API key when the engine has one
       /health   /stats   /v1/load   /metrics    (Prometheus text)

WHAT IT SHOWS
  * 调用量：总数、按小时/按天柱状图、按协议与流式拆分
  * token 用量：prompt / completion / 实际 prefill / 前缀缓存命中（省下的）
  * 性能：平均与最近 TTFT、prefill tok/s、decode tok/s
  * 投机解码：草稿数 vs 接受数 → 接受率
  * 最近请求明细表 + 实时负载（running/waiting/KV 占用）

USAGE
  python usage-dashboard.py --request-log D:\\...\\logs\\requests.jsonl ^
      --stats http://127.0.0.1:8099 --api-key-file D:\\...\\api-key.txt ^
      --port 8098
  then open http://127.0.0.1:8098/
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API 调用量 · NInfer</title>
<script>
window.onerror = function (m, s, l, c) {
  var d = document.createElement('div');
  d.style.cssText = 'margin:8px 16px;padding:10px;border-radius:8px;background:#4a1f22;color:#ffd7d7;font:13px monospace';
  d.textContent = '页面脚本错误：' + m + ' @' + l + ':' + c;
  document.body.appendChild(d);
};
</script>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; background:#0f1115; color:#e8e8ea; font-family:"Segoe UI","Microsoft YaHei",sans-serif; }
  header { padding:12px 18px; background:#161a22; border-bottom:1px solid #262b36;
           display:flex; align-items:center; gap:14px; flex-wrap:wrap; position:sticky; top:0; z-index:5; }
  header h1 { font-size:15px; margin:0; font-weight:600; color:#cfd4df; }
  #status { font-size:12px; padding:2px 10px; border-radius:10px; background:#333; }
  #status.ok { background:#14432b; color:#6ee7a0; }
  #status.bad { background:#4a1f22; color:#f38a8a; }
  #meta { font-size:12px; color:#8a93a6; margin-left:auto; }
  main { padding:16px 18px 40px; display:flex; flex-direction:column; gap:16px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:12px; }
  .card { background:#161a22; border:1px solid #262b36; border-radius:10px; padding:12px 14px; }
  .card .k { font-size:12px; color:#8a93a6; }
  .card .v { font-size:22px; font-weight:600; margin-top:6px; color:#e8e8ea; }
  .card .s { font-size:11px; color:#6f7a8d; margin-top:4px; }
  .panel { background:#161a22; border:1px solid #262b36; border-radius:10px; padding:14px 16px; }
  .panel h2 { font-size:13px; margin:0 0 10px; color:#cfd4df; font-weight:600; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:1000px) { .grid2 { grid-template-columns:1fr; } }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th, td { text-align:right; padding:5px 8px; border-bottom:1px solid #1f242e; white-space:nowrap; }
  th:first-child, td:first-child { text-align:left; }
  th { color:#8a93a6; font-weight:500; }
  tbody tr:hover { background:#1a1f29; }
  .bar { fill:#3b6fd4; }
  .bar2 { fill:#2f9e6b; }
  .axis { stroke:#2a3142; stroke-width:1; }
  .lbl { fill:#7f8aa0; font-size:10px; }
  code { color:#9ecbff; }
  .muted { color:#7f8aa0; }
  .tag { display:inline-block; padding:1px 6px; border-radius:6px; background:#222835; color:#9aa6bb; font-size:11px; }
</style>
</head>
<body>
<header>
  <h1>API 调用量 · NInfer sm_120a</h1>
  <span id="status">加载中…</span>
  <span id="meta"></span>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="grid2">
    <div class="panel"><h2>每小时请求数（最近 24 小时）</h2><div id="chartReq"></div></div>
    <div class="panel"><h2>每小时 token 数（最近 24 小时 · 蓝=输入 绿=输出）</h2><div id="chartTok"></div></div>
  </div>
  <div class="grid2">
    <div class="panel"><h2>实时负载（引擎 /v1/load）</h2><div id="load" class="muted">…</div></div>
    <div class="panel"><h2>累计计数（引擎 /metrics · 自本次启动）</h2><div id="metrics" class="muted">…</div></div>
  </div>
  <div class="panel">
    <h2>最近请求（明细）</h2>
    <div style="max-height:420px; overflow:auto"><table id="recent">
      <thead><tr><th>时间</th><th>#</th><th>协议</th><th>流式</th><th>输入 tok</th><th>输出 tok</th>
      <th>缓存命中</th><th>TTFT</th><th>prefill tok/s</th><th>decode tok/s</th><th>投机</th><th>结束</th><th>工具</th></tr></thead>
      <tbody></tbody></table></div>
  </div>
</main>
<script>
function fmt(n, d) { if (n === null || n === undefined) return '—'; return Number(n).toLocaleString(undefined, {maximumFractionDigits: d===undefined?0:d}); }
function fmtSec(s) { if (!s) return '—'; return s >= 1 ? s.toFixed(2) + ' s' : (s*1000).toFixed(0) + ' ms'; }

function bars(el, rows, keyA, keyB) {
  var w = el.clientWidth || 520, h = 150, pad = 22;
  if (!rows.length) { el.innerHTML = '<div class="muted">还没有数据</div>'; return; }
  var max = 1;
  rows.forEach(function (r) { max = Math.max(max, r[keyA] || 0, (keyB ? (r[keyB] || 0) : 0)); });
  var bw = Math.max(3, (w - pad*2) / rows.length - 3);
  var svg = ['<svg width="100%" height="' + (h+18) + '" viewBox="0 0 ' + w + ' ' + (h+18) + '">'];
  svg.push('<line class="axis" x1="' + pad + '" y1="' + h + '" x2="' + (w-pad) + '" y2="' + h + '"/>');
  rows.forEach(function (r, i) {
    var x = pad + i * ((w - pad*2) / rows.length);
    var hA = Math.round((r[keyA] || 0) / max * (h - 14));
    svg.push('<rect class="bar" x="' + x + '" y="' + (h - hA) + '" width="' + bw + '" height="' + hA + '"><title>' + r.label + ' · ' + keyA + '=' + fmt(r[keyA]) + '</title></rect>');
    if (keyB) {
      var hB = Math.round((r[keyB] || 0) / max * (h - 14));
      svg.push('<rect class="bar2" x="' + (x + bw + 2) + '" y="' + (h - hB) + '" width="' + bw + '" height="' + hB + '"><title>' + r.label + ' · ' + keyB + '=' + fmt(r[keyB]) + '</title></rect>');
    }
    if (i % 3 === 0) svg.push('<text class="lbl" x="' + (x-2) + '" y="' + (h+14) + '">' + r.label.slice(-5) + '</text>');
  });
  svg.push('</svg>');
  el.innerHTML = svg.join('');
}

function card(k, v, s) {
  return '<div class="card"><div class="k">' + k + '</div><div class="v">' + v + '</div><div class="s">' + (s||'') + '</div></div>';
}

var lastGood = 0;
function refresh() {
  fetch('/data', {cache:'no-store'}).then(function (r) { return r.json(); }).then(function (d) {
    document.getElementById('status').textContent = d.engine_ok ? '引擎在跑' : '引擎未响应';
    document.getElementById('status').className = d.engine_ok ? 'ok' : 'bad';
    document.getElementById('meta').textContent =
      '日志 ' + d.log_file + ' · ' + (d.log_bytes/1024/1024).toFixed(2) + ' MiB · 统计口 ' + d.stats_url
      + ' · 更新 ' + new Date().toLocaleTimeString();

    var t = d.totals;
    document.getElementById('cards').innerHTML =
      card('总请求数', fmt(t.requests), '来自请求日志（跨重启累计）') +
      card('输入 token', fmt(t.prompt_tokens), '其中缓存命中 ' + fmt(t.cache_hit_tokens)) +
      card('输出 token', fmt(t.completion_tokens), '实际 prefill ' + fmt(t.prefill_tokens)) +
      card('平均 TTFT', fmtSec(t.avg_ttft), '最近一次 ' + fmtSec(t.last_ttft)) +
      card('平均 decode', t.avg_decode ? t.avg_decode.toFixed(1) + ' tok/s' : '—', '最近一次 ' + (t.last_decode ? t.last_decode.toFixed(1) : '—') + ' tok/s') +
      card('平均 prefill', t.avg_prefill ? t.avg_prefill.toFixed(0) + ' tok/s' : '—', '') +
      card('投机接受率', t.accept_rate === null ? '—' : (t.accept_rate*100).toFixed(1) + '%', '草稿 ' + fmt(t.drafted) + ' / 接受 ' + fmt(t.accepted)) +
      card('工具调用', fmt(t.tool_calls), '含工具历史的请求 ' + fmt(t.requests_with_tools));

    bars(document.getElementById('chartReq'), d.hourly, 'requests', null);
    bars(document.getElementById('chartTok'), d.hourly, 'prompt_tokens', 'completion_tokens');

    var L = d.load;
    document.getElementById('load').innerHTML = L ? (
      '<table><tbody>' +
      '<tr><th>运行中 / 排队</th><td>' + fmt(L.requests.running) + ' / ' + fmt(L.requests.waiting) + '</td></tr>' +
      '<tr><th>已准入 / 峰值</th><td>' + fmt(L.requests.admitted) + ' / ' + fmt(L.requests.peak_admitted) + '</td></tr>' +
      '<tr><th>设备 KV 页占用</th><td>' + fmt(L.occupancy.device_main_kv_pages) + ' / ' + fmt(L.capacity.kv_capacity_pages) + ' 页（' + fmt(L.occupancy.device_main_kv_tokens) + ' / ' + fmt(L.capacity.kv_capacity_tokens) + ' token）</td></tr>' +
      '<tr><th>主机 KV 已用</th><td>' + (L.occupancy.host_kv_bytes/1073741824).toFixed(2) + ' / ' + (L.capacity.host_kv_bytes/1073741824).toFixed(1) + ' GiB</td></tr>' +
      '<tr><th>已解码 / 已 prefill token</th><td>' + fmt(L.counters.committed_decode_tokens) + ' / ' + fmt(L.counters.computed_prefill_tokens) + '</td></tr>' +
      '<tr><th>启动时长</th><td>' + fmtSec(L.uptime_seconds) + '</td></tr>' +
      '</tbody></table>') : '<div class="muted">统计口没响应（引擎带 --stats-port 吗？密钥对吗？）</div>';

    document.getElementById('metrics').innerHTML = d.metrics && d.metrics.length
      ? '<table><tbody>' + d.metrics.map(function (m) {
          return '<tr><th>' + m.name + '</th><td>' + fmt(m.value, 2) + '</td></tr>'; }).join('') + '</tbody></table>'
      : '<div class="muted">没有取到 /metrics</div>';

    var tb = document.querySelector('#recent tbody');
    tb.innerHTML = d.recent.map(function (r) {
      return '<tr><td>' + r.time + '</td><td>' + r.id + '</td><td>' + r.protocol + '</td><td>' + (r.stream ? '是' : '否') +
        '</td><td>' + fmt(r.prompt_tokens) + '</td><td>' + fmt(r.completion_tokens) +
        '</td><td>' + fmt(r.cache_hit) + '</td><td>' + fmtSec(r.ttft) +
        '</td><td>' + (r.prefill_tps ? r.prefill_tps.toFixed(0) : '—') +
        '</td><td>' + (r.decode_tps ? r.decode_tps.toFixed(1) : '—') +
        '</td><td>' + (r.drafted ? (r.accepted + '/' + r.drafted) : '—') +
        '</td><td>' + (r.finish || '—') + '</td><td>' + fmt(r.tool_calls) + '</td></tr>';
    }).join('') || '<tr><td colspan="13" class="muted">还没有请求记录</td></tr>';
  }).catch(function (e) { document.getElementById('status').textContent = '看板错误: ' + e.message; });
}
refresh();
setInterval(refresh, 5000);
window.addEventListener('resize', function () { refresh(); });
</script>
</body>
</html>
"""


class Agg:
    """Incremental parser for the engine's request-log JSONL."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.partial = b""
        self.totals = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                       "prefill_tokens": 0, "cache_hit_tokens": 0, "drafted": 0, "accepted": 0,
                       "tool_calls": 0, "requests_with_tools": 0, "ttft_sum": 0.0, "ttft_n": 0,
                       "prefill_time": 0.0, "decode_time": 0.0, "last_ttft": None, "last_decode": None}
        self.hourly = {}
        self.recent = []
        self.start_info = None
        self.protocols = {}
        self.streams = {"stream": 0, "non_stream": 0}

    def poll(self):
        if not os.path.exists(self.path):
            return
        size = os.path.getsize(self.path)
        if size < self.offset:      # log rotated
            self.offset = 0
            self.partial = b""
        if size == self.offset:
            return
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
            self.offset = f.tell()
        data = self.partial + data
        lines = data.split(b"\n")
        self.partial = lines.pop()
        for raw in lines:
            if not raw.strip():
                continue
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            self._event(ev)

    def _event(self, ev):
        kind = ev.get("event")
        if kind == "server_start":
            self.start_info = {"gpu": (ev.get("environment") or {}).get("gpu_name"),
                               "cap": "%s.%s" % ((ev.get("environment") or {}).get("compute_capability_major"),
                                                 (ev.get("environment") or {}).get("compute_capability_minor")),
                               "kv": (ev.get("engine") or {}).get("kv_cache"),
                               "capacity": (ev.get("engine") or {}).get("kv_capacity")}
            return
        if kind == "request_done":
            res = ev.get("result") or {}
            tim = ev.get("timings_seconds") or {}
            spec = ev.get("speculative") or {}
            req = ev.get("request") or {}
            p_tok = int(res.get("prompt_tokens") or 0)
            c_tok = int(res.get("completion_tokens") or 0)
            pre_tok = int(res.get("computed_prefill_tokens") or 0)
            cache_hit = int(res.get("prefix_cache_hit_tokens") or 0)
            ttft = float(tim.get("ttft") or 0.0)
            pre_s = float(tim.get("prefill") or 0.0)
            dec_s = float(tim.get("decode") or 0.0)
            drafted = int(spec.get("drafted_tokens") or 0)
            accepted = int(spec.get("accepted_tokens") or 0)
            tools = int(res.get("tool_call_count") or 0)

            t = self.totals
            t["requests"] += 1
            t["prompt_tokens"] += p_tok
            t["completion_tokens"] += c_tok
            t["prefill_tokens"] += pre_tok
            t["cache_hit_tokens"] += cache_hit
            t["drafted"] += drafted
            t["accepted"] += accepted
            t["tool_calls"] += tools
            if req.get("has_tool_history"):
                t["requests_with_tools"] += 1
            if ttft:
                t["ttft_sum"] += ttft
                t["ttft_n"] += 1
                t["last_ttft"] = ttft
            t["prefill_time"] += pre_s
            t["decode_time"] += dec_s
            dec_tps = (c_tok / dec_s) if dec_s > 0 else 0.0
            pre_tps = (pre_tok / pre_s) if pre_s > 0 else 0.0
            if dec_tps:
                t["last_decode"] = dec_tps

            ts = ev.get("timestamp_unix_ms") or 0
            hour = time.strftime("%m-%d %H:00", time.localtime(ts / 1000.0)) if ts else ""
            b = self.hourly.setdefault(hour, {"label": hour, "requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
            b["requests"] += 1
            b["prompt_tokens"] += p_tok
            b["completion_tokens"] += c_tok

            proto = req.get("protocol") or "?"
            self.protocols[proto] = self.protocols.get(proto, 0) + 1
            self.streams["stream" if req.get("stream") else "non_stream"] += 1

            self.recent.append({
                "time": time.strftime("%H:%M:%S", time.localtime(ts / 1000.0)) if ts else "?",
                "id": req.get("request_id"), "protocol": proto.replace("openai_", ""),
                "stream": bool(req.get("stream")), "prompt_tokens": p_tok, "completion_tokens": c_tok,
                "cache_hit": cache_hit, "ttft": ttft, "prefill_tps": pre_tps, "decode_tps": dec_tps,
                "drafted": drafted, "accepted": accepted,
                "finish": res.get("finish_reason"), "tool_calls": tools,
            })
            if len(self.recent) > 300:
                self.recent = self.recent[-300:]

    def snapshot(self):
        t = dict(self.totals)
        t["avg_ttft"] = (t["ttft_sum"] / t["ttft_n"]) if t["ttft_n"] else None
        t["avg_decode"] = (t["completion_tokens"] / t["decode_time"]) if t["decode_time"] > 0 else None
        t["avg_prefill"] = (t["prefill_tokens"] / t["prefill_time"]) if t["prefill_time"] > 0 else None
        t["accept_rate"] = (t["accepted"] / t["drafted"]) if t["drafted"] else None
        hours = sorted(self.hourly.keys())[-24:]
        return {"totals": t,
                "hourly": [self.hourly[h] for h in hours],
                "recent": list(reversed(self.recent[-50:])),
                "start_info": self.start_info,
                "protocols": self.protocols, "streams": self.streams}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    agg = None
    stats_url = ""
    api_key = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("[usage] %s - %s\n" % (self.address_string(), fmt % args))
        sys.stderr.flush()

    def _send(self, code, ctype, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _fetch(self, path, timeout=6):
        req = urllib.request.Request(self.stats_url.rstrip("/") + path,
                                     headers={"Authorization": "Bearer " + self.api_key} if self.api_key else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def _metrics_subset(self):
        try:
            text = self._fetch("/metrics")
        except Exception:
            return None
        want = ("ninfer:requests_total", "llamacpp:prompt_tokens_total", "llamacpp:tokens_predicted_total",
                "llamacpp:prompt_tokens_seconds", "llamacpp:predicted_tokens_seconds",
                "llamacpp:kv_cache_usage_ratio", "llamacpp:kv_cache_tokens",
                "ninfer:prefix_cache_hit_tokens_total", "llamacpp:n_decode_total",
                "ninfer:requests_admitted")
        out = []
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            name, val = parts[0], parts[1]
            if name in want:
                try:
                    out.append({"name": name, "value": float(val)})
                except ValueError:
                    pass
        return out

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
            return
        if path == "/health":
            self._send(200, "application/json", b'{"ok":true}')
            return
        if path != "/data":
            self._send(404, "text/plain", b"not found")
            return

        self.agg.poll()
        snap = self.agg.snapshot()
        engine_ok, load = False, None
        try:
            load = json.loads(self._fetch("/v1/load"))
            engine_ok = True
        except Exception:
            pass
        body = {
            "engine_ok": engine_ok,
            "log_file": os.path.basename(self.agg.path),
            "log_bytes": os.path.getsize(self.agg.path) if os.path.exists(self.agg.path) else 0,
            "stats_url": self.stats_url,
            "load": load,
            "metrics": self._metrics_subset(),
            **snap,
        }
        self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="API usage dashboard for the NInfer engine")
    ap.add_argument("--port", type=int, default=8098)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--request-log", required=True, help="the engine's --request-log-jsonl file")
    ap.add_argument("--stats", default="http://127.0.0.1:8099", help="the engine's --stats-port base URL")
    ap.add_argument("--api-key", default=os.environ.get("NINFER_API_KEY"))
    ap.add_argument("--api-key-file", default=None, help="read the key from this file instead")
    args = ap.parse_args()

    key = args.api_key or ""
    if args.api_key_file and os.path.exists(args.api_key_file):
        key = open(args.api_key_file, encoding="utf-8").read().strip()

    Handler.agg = Agg(args.request_log)
    Handler.stats_url = args.stats
    Handler.api_key = key
    Handler.agg.poll()

    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 70)
    print(" API 调用量看板")
    print("   打开      : http://%s:%d/" % (args.host, args.port))
    print("   请求日志  : %s" % args.request_log)
    print("   统计口    : %s   (api key: %s)" % (args.stats, "已配置" if key else "未配置"))
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[usage] bye")


if __name__ == "__main__":
    main()

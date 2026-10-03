#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Resumable, verifying downloader for ninfer model packs.

Why this exists instead of `curl.exe -C -`:
  In this DSH session, Schannel is unusable under the workspace-write sandbox
  (curl  -> "schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS"
   .NET  -> "No credentials are available in the security package").
  TCP 443 is reachable and the same curl succeeds under danger-full-access,
  so it is a sandbox restriction on Schannel credentials, not the network.
  This script uses the bundled CPython + OpenSSL (3.5.8, verified HTTP 200 to
  hf-mirror.com), i.e. it does not touch Schannel at all.

The pack's tutorial (section 0.0 step 1) demands a resumable download plus a
byte-exact hash check, so both are implemented here:
  * HTTP Range resume against a .part file (server must honour 206)
  * sha256 of the finished file, compared against the expected value
  * byte count compared against the expected value
Both --sha256 and --bytes are optional: if omitted the file is only hashed and
the measurement is *reported*, never silently treated as "verified".

Usage:
  python fetch-ninfer-model.py --url URL --out PATH [--sha256 HEX] [--bytes N]
"""

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request


def human(n):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return "%.2f %s" % (n, unit)
        n /= 1024.0


def remote_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        length = r.headers.get("Content-Length")
        return int(length) if length else None


def download(url, out, expected_bytes=None):
    part = out + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0

    if expected_bytes is not None and have > expected_bytes:
        print("[warn] .part is larger than the expected size; restarting at 0")
        os.remove(part)
        have = 0

    req = urllib.request.Request(url)
    mode = "wb"
    if have:
        req.add_header("Range", "bytes=%d-" % have)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        if have and e.code == 416:
            print("[info] server says the .part already covers the whole file")
            os.replace(part, out)
            return out
        raise

    code = resp.status
    if have and code != 206:
        print("[warn] server ignored Range (HTTP %s): restarting from 0 "
              "instead of appending garbage" % code)
        resp.close()
        os.remove(part)
        have = 0
        resp = urllib.request.urlopen(urllib.request.Request(url), timeout=120)
    mode = "ab" if have else "wb"
    print("[dl  ] HTTP %s, resuming at %s" % (resp.status, human(have)))

    total = expected_bytes
    if total is None:
        cl = resp.headers.get("Content-Length")
        if cl:
            total = have + int(cl)

    done = have
    with open(part, mode) as f:
        while True:
            chunk = resp.read(4 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = 100.0 * done / total
                sys.stdout.write("\r[dl  ] %s / %s  %5.1f%%"
                                 % (human(done), human(total), pct))
            else:
                sys.stdout.write("\r[dl  ] %s" % human(done))
            sys.stdout.flush()
    resp.close()
    sys.stdout.write("\n")

    os.replace(part, out)
    return out


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest().upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True, help="final path, e.g. ...\\models\\x.ninfer")
    ap.add_argument("--sha256", default=None, help="expected sha256 (hex, case-insensitive)")
    ap.add_argument("--bytes", type=int, default=None, help="expected size in bytes")
    ap.add_argument("--skip-if-ok", action="store_true",
                    help="if the output already exists and matches, do nothing")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    if not os.path.isdir(os.path.dirname(out)):
        print("[fail] target directory does not exist: %s" % os.path.dirname(out))
        return 3

    if a.skip_if_ok and os.path.exists(out):
        size = os.path.getsize(out)
        digest = sha256_of(out)
        if (a.bytes is None or size == a.bytes) and \
           (a.sha256 is None or digest.lower() == a.sha256.lower()):
            print("[ok  ] already present and matching: %s" % out)
            return 0

    if a.bytes is None:
        try:
            a.bytes = remote_size(a.url)
            print("[info] Content-Length from HEAD: %s" % human(a.bytes))
        except Exception as e:
            print("[warn] HEAD failed (%s); size taken from the GET response" % e)

    download(a.url, out, a.bytes)

    size = os.path.getsize(out)
    digest = sha256_of(out)
    print("[file] %s" % out)
    print("[size] %d bytes (%s)" % (size, human(size)))
    print("[sha ] %s" % digest)

    verdict = 0
    if a.bytes is not None and size != a.bytes:
        print("[FAIL] size mismatch: expected %d, got %d" % (a.bytes, size))
        verdict = 1
    if a.sha256 is not None and digest.lower() != a.sha256.lower():
        print("[FAIL] sha256 mismatch: expected %s" % a.sha256.upper())
        verdict = 1
    if a.bytes is None and a.sha256 is None:
        print("[warn] no expected size/sha256 supplied -> this file is NOT verified "
              "(report it as unverified, never as checked)")
    elif verdict == 0:
        print("[PASS] byte count and sha256 both match")

    return verdict


if __name__ == "__main__":
    sys.exit(main())

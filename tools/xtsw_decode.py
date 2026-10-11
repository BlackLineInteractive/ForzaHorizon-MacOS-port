#!/usr/bin/env python3
"""Decode title-service requests saved by the Forza Live server (--dump-requests).

    tools/xtsw_decode.py DATA_DIR/requests/<file> ...   # these requests
    tools/xtsw_decode.py -n 20 DATA_DIR                  # the last 20 (polling calls skipped)

Each line: time, Class.Method, body size, the parameters (zero and empty fields left out;
"[+N bytes]" when the body is longer than the record). Uses server/forza_xtsw_all.py.
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import forza_xtsw as x  # noqa: E402
import forza_xtsw_all as schema  # noqa: E402

POLLING = {"GetStringTableInfo", "DownloadContent", "RetrieveForUser", "UserRegister"}


def short(v):
    if isinstance(v, bytes):
        return v.hex()[:40] + ("..(%d)" % len(v) if len(v) > 20 else "")
    if isinstance(v, dict):
        return {k: short(w) for k, w in v.items() if w not in (0, "", b"", [], 0.0)}
    if isinstance(v, list):
        return [short(w) for w in v[:8]] + (["...%d" % len(v)] if len(v) > 8 else [])
    return v


def decode_file(path):
    raw = open(path, "rb").read()
    head, body = raw.split(b"\r\n\r\n", 1)
    h = dict(line.split(": ", 1) for line in head.decode().split("\r\n") if ": " in line)
    cls = h.get("x-classname", "").split(",")[0].split(".")[-1]
    method = h.get("x-method", "")
    out = "(no record)"
    for name in dir(schema):
        if not name.endswith(cls + method + "_Params"):
            continue
        try:
            v, pos = x.decode(getattr(schema, name), body)
            out = str(short(v)) + ("" if pos == len(body) else " [+%d bytes]" % (len(body) - pos))
            break
        except ValueError as e:
            out = "decode error: %s" % e
    stamp = os.path.basename(path).split("-")[0]
    return "%s %s.%s %d %s" % (stamp[-7:], cls, method, len(body), out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", help="request files, or a data dir with -n")
    ap.add_argument("-n", type=int, help="the last N requests of DATA_DIR/requests")
    args = ap.parse_args()
    files = args.paths
    if args.n:
        files = [f for f in sorted(glob.glob(os.path.join(args.paths[0], "requests", "*")))
                 if f.rsplit("-", 1)[-1] not in POLLING][-args.n:]
    for f in files:
        print(decode_file(f))


if __name__ == "__main__":
    main()

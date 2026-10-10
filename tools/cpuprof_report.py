#!/usr/bin/env python3
"""Summarize a CPU profile written by src/debug/cpu_profile.cpp (PROF:START / PROF:STOP).

Usage: cpuprof_report.py CPUPROF.txt [--top N] [--thread SUBSTRING]

Symbolizes "count tid thread module offset" lines with addr2line (one batch per module),
then prints the CPU time per thread and the hottest functions overall and per busy
thread. Recompiled guest functions show as sub_XXXXXXXX (__imp__sub_... is the same
function's body); runtime and GPU plugin code show with their C++ names.
"""
import argparse
import collections
import os
import shutil
import subprocess


def symbolize(module, offsets):
    tool = shutil.which("llvm-addr2line") or "/home/linuxbrew/.linuxbrew/bin/llvm-addr2line"
    if not os.path.exists(tool):
        tool = "addr2line"
    if not os.path.exists(module):
        return {o: os.path.basename(module) + "+" + o for o in offsets}
    out = subprocess.run([tool, "-f", "-C", "-e", module], input="\n".join(offsets) + "\n",
                         capture_output=True, text=True).stdout.splitlines()
    names = {}
    for i, off in enumerate(offsets):
        name = out[2 * i] if 2 * i < len(out) else "??"
        if name in ("??", ""):
            name = os.path.basename(module) + "+" + off
        names[off] = name.replace("__imp__sub_", "sub_")
    return names


def short(name, width=110):
    return name if len(name) <= width else name[:width - 3] + "..."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--thread", default="")
    a = ap.parse_args()

    rows = []
    for line in open(a.profile):
        parts = line.split()
        if len(parts) != 5:
            continue
        count, tid, thread, module, offset = parts
        rows.append((int(count), int(tid), thread, module, offset))
    by_module = collections.defaultdict(set)
    for _, _, _, module, offset in rows:
        by_module[module].add(offset)
    names = {}
    for module, offsets in by_module.items():
        for off, name in symbolize(module, sorted(offsets)).items():
            names[(module, off)] = name

    total = sum(r[0] for r in rows)
    threads = collections.Counter()
    funcs = collections.Counter()
    per_thread = collections.defaultdict(collections.Counter)
    modules = collections.Counter()
    for count, tid, thread, module, offset in rows:
        key = f"{thread}[{tid}]"
        if a.thread and a.thread not in key:
            continue
        threads[key] += count
        name = names[(module, offset)]
        funcs[name] += count
        per_thread[key][name] += count
        modules[os.path.basename(module)] += count
    print(f"{total} samples (1 ms of CPU each)")
    print("\nBy thread:")
    for key, n in threads.most_common(15):
        print(f"  {n:7d} {100.0 * n / total:5.1f}%  {key}")
    print("\nBy module:")
    for m, n in modules.most_common(8):
        print(f"  {n:7d} {100.0 * n / total:5.1f}%  {m}")
    print(f"\nTop {a.top} functions (self):")
    for name, n in funcs.most_common(a.top):
        print(f"  {n:7d} {100.0 * n / total:5.1f}%  {short(name)}")
    for key, _ in threads.most_common(6):
        c = per_thread[key]
        t = sum(c.values())
        print(f"\n{key}: {t} samples")
        for name, n in c.most_common(10):
            print(f"  {n:7d} {100.0 * n / t:5.1f}%  {short(name)}")


if __name__ == "__main__":
    main()

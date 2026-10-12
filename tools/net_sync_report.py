#!/usr/bin/env python3
"""net_sync_report.py A_CARS B_CARS: how each console's own car appears on the other console
in an online race (docs/framerate.md, mixed frame rates). Both files are tools/carlog.py
output from two games on one machine (host monotonic time, the same clock for both).
For X's own car (kind 0 in X's file) finds, in the other file, the car that follows it
(smallest mean distance), and prints the distance between X's true position and the copy
at the same instant (mean, p50, p95, max) and the time shift that best aligns them (the
copy's delay), while the car moves."""
import bisect, math, sys
from collections import defaultdict


def load(p):
    cars = defaultdict(list)  # slot -> [(t, x, z)], kind
    kinds = {}
    for line in open(p):
        t, kind, slot, x, z = line.split()
        cars[slot].append((float(t), float(x), float(z)))
        kinds[slot] = int(kind)
    return cars, kinds


def interp(track, t):
    ts = [s[0] for s in track]
    i = bisect.bisect_left(ts, t)
    if i == 0 or i >= len(track):
        return None
    a, b = track[i - 1], track[i]
    if b[0] - a[0] > 0.5:
        return None
    f = (t - a[0]) / (b[0] - a[0])
    return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]))


def compare(truth, copy, shift=0.0):
    ds = []
    for i in range(0, len(truth), 3):
        t, x, z = truth[i]
        p = interp(copy, t + shift)
        if p:
            ds.append(math.hypot(p[0] - x, p[1] - z))
    return ds


def moving(track):
    out = []
    for a, b in zip(track, track[1:]):
        if b[0] > a[0] and math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0]) > 3:
            out.append(b)
    return out


def report(name, own_file, other_file):
    own, okind = load(own_file)
    other, kinds = load(other_file)
    me = [s for s, k in okind.items() if k == 0]
    if not me:
        print(name, "no own car")
        return
    truth = max((moving(own[s]) for s in me), key=len)
    if len(truth) < 50:
        print(name, "own car hardly moved")
        return
    best = None
    for slot, track in other.items():
        if kinds[slot] == 0 or len(track) < 20:
            continue
        ds = compare(truth, track)
        if len(ds) > len(truth) / 10:
            m = sum(ds) / len(ds)
            if best is None or m < best[0]:
                best = (m, slot, ds)
    if not best:
        print(name, "no copy found")
        return
    m, slot, ds = best
    ds.sort()
    speeds = []
    for a, b in zip(truth, truth[1:]):
        if b[0] - a[0] > 0:
            speeds.append(math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0]))
    shifts = [k * 0.01 for k in range(-30, 41)]
    sm = min(shifts, key=lambda s: (lambda d: sum(d) / max(1, len(d)))(compare(truth, other[slot], s)))
    ds2 = sorted(compare(truth, other[slot], sm))
    print("%s: copy slot %s (kind %d), %d samples, speed mean %.1f m/s; distance at the same time: "
          "mean %.2f p50 %.2f p95 %.2f max %.2f m; best shift %+.0f ms -> mean %.2f p95 %.2f m"
          % (name, slot, kinds[slot], len(ds), sum(speeds) / len(speeds), m, ds[len(ds) // 2],
             ds[int(len(ds) * .95)], ds[-1], sm * 1000, sum(ds2) / len(ds2), ds2[int(len(ds2) * .95)]))


report("A's car on B", sys.argv[1], sys.argv[2])
report("B's car on A", sys.argv[2], sys.argv[1])

#!/usr/bin/env python3
"""frametime_report.py DIR: summarize a run's frame time and car motion (docs/framerate.md).
- DIR/frametime.csv (FORZA_FRAMETIME_CSV: t,dt,game_ms,on_target,x,z per main-loop frame):
  dt statistics while the player's car moves, and how evenly it moves: the sd of each
  frame's displacement over the mean of its neighbours (0 = even), and of displacement / dt.
- DIR/cars.txt (tools/carlog.py): the player's car's distance from the launch at fixed
  times, 0-100 km/h, and the time it comes back to the launch point (a lap).
"""
import math, os, statistics, sys

D = sys.argv[1]


def frametime():
    p = os.path.join(D, "frametime.csv")
    if not os.path.exists(p):
        return
    rows = []
    for line in open(p):
        try:
            t, dt, gms, paced, x, z = line.strip().split(",")
            rows.append((float(t), float(dt), int(gms), int(paced), float(x), float(z)))
        except ValueError:
            pass
    # moving frames: displacement between consecutive frames, paired with the previous dt
    seg = []
    for a, b in zip(rows, rows[1:]):
        d = math.hypot(b[4] - a[4], b[5] - a[5])
        if a[4] == 0 and a[5] == 0:
            continue
        seg.append((b[0], a[1], d, a[2], a[3]))
    mv = [s for s in seg if 0.02 < s[2] < 5]
    if len(mv) < 50:
        print("frametime: %d frames, %d moving" % (len(rows), len(mv)))
        return
    dts = [s[1] for s in mv]
    gms = [s[3] for s in mv]
    # smoothness: displacement / (5-frame centered mean displacement), and speed = d/dt
    rel, relg = [], []
    for i in range(2, len(mv) - 2):
        win = [mv[j][2] for j in range(i - 2, i + 3)]
        m = sum(win) / 5
        if m > 0:
            rel.append(mv[i][2] / m)
    sp = [s[2] / (s[1] / 1000) for s in mv if s[1] > 0]
    print("frametime: frames=%d moving=%d dt mean=%.3f sd=%.3f | game ms sd=%.3f | on_target=%.1f%%"
          % (len(rows), len(mv), statistics.mean(dts), statistics.pstdev(dts), statistics.pstdev(gms),
             100 * sum(s[4] for s in mv) / len(mv)))
    print("  per-frame displacement / local mean: sd=%.4f (motion judder; 0 = even)"
          % statistics.pstdev(rel))
    # speed consistency d/dt vs local mean of d/dt
    rs = []
    for i in range(2, len(sp) - 2):
        m = sum(sp[i - 2:i + 3]) / 5
        if m > 0:
            rs.append(sp[i] / m)
    print("  speed d/dt / local mean: sd=%.4f (0 = displacement follows dt)" % statistics.pstdev(rs))


def cars():
    p = os.path.join(D, "cars.txt")
    if not os.path.exists(p):
        return
    own = []
    for line in open(p):
        t, kind, slot, x, z = line.split()
        if kind == "0":
            own.append((float(t), float(x), float(z)))
    if len(own) < 10:
        print("cars: no samples")
        return
    t0, x0, z0 = own[0]
    launch = None
    for t, x, z in own:
        if math.hypot(x - x0, z - z0) > 0.3:
            launch = t
            break
    if launch is None:
        print("cars: never moved")
        return
    # distance along the path
    dist = [(own[0][0], 0.0)]
    for a, b in zip(own, own[1:]):
        dist.append((b[0], dist[-1][1] + math.hypot(b[1] - a[1], b[2] - a[2])))

    def at(T):
        for t, d in dist:
            if t >= launch + T:
                return d
        return float("nan")

    def speed(T, w=0.25):
        return (at(T + w) - at(T - w)) / (2 * w) * 3.6

    t100 = None
    for t, _ in dist:
        if t > launch + 0.3 and speed(t - launch) >= 100:
            t100 = t - launch
            break
    lap = ""
    if dist[-1][1] > 2500:
        lx, lz = next((x, z) for t, x, z in own if t >= launch)
        cands = [(math.hypot(x - lx, z - lz), t) for (t, x, z), (_, d) in zip(own, dist) if d > 2000]
        dmin, tl = min(cands)
        if dmin < 25:
            lap = "; back at the launch point after %.2f s (%.1f m off)" % (tl - launch, dmin)
    print("cars: distance from launch at 1/2/3/5/8/12/20 s: " +
          " ".join("%.1f" % at(T) for T in (1, 2, 3, 5, 8, 12, 20)) +
          " m; speed at 2/5/10 s: %.0f/%.0f/%.0f km/h; 0-100 km/h %.2f s"
          % (speed(2), speed(5), speed(10), t100 or float("nan")) + lap)


frametime()
cars()

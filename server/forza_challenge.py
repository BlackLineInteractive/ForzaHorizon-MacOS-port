"""Head-to-head challenges between players in the Horizon World (docs/online_vision.md,
phase 3).

In the world's free roam a player drives up behind another player and presses X: the
client sends REQUEST, the server finds the player close ahead of it in the same world and
asks that player (PROMPT); the challenged player accepts (X) or declines (B) within 10 s.
On accept both get START: a destination, a landmark of the map a few km away (the
endpoints of the game's own A-to-B free roam challenges, FreeRoamChallenges.xml), and a
3 s countdown. Each client checks its own car against the finish and sends FINISH; the
first one wins (END to both). Nobody leaves the world: the race runs inside the free roam
and the other players are not disturbed.

The clients (src/hooks/world_challenge.cpp) send their car's position (POS) four times a
second while they drive in the world, so the "behind" check, the destination and the
forfeits (a racer who left the world or the server) are decided here.

Message CHALLENGE (UDP kind 19), body op u8 then (big endian):
  client -> server
    1 POS      x, y, z, heading x, heading z, speed (f32 each; y is up, m and m/s)
    2 REQUEST  (X pressed)
    3 ANSWER   challenge id u32, accept u8
    4 FINISH   challenge id u32, race time ms u32
    5 LEFT     (the client left the world's free roam)
  server -> client
    16 NOTICE  seconds u8, text (u16 length + UTF-8; first line is the title)
    17 PROMPT  challenge id u32, seconds u8, challenger (u8 length + UTF-8)
    18 START   challenge id u32, countdown ms u16, x f32, y f32, z f32, radius f32,
               opponent (u8 length + UTF-8), destination (u8 length + UTF-8)
    19 END     challenge id u32, outcome u8 (1 won, 2 lost, 3 no winner, 4 called off),
               text (u16 length + UTF-8)
    20 CONFIG  range f32, any direction u8: the client offers X only for a car this close
               (and ahead): the game gets X otherwise (it opens the leaderboards)
"""

import logging
import math
import struct
import time

log = logging.getLogger("forza-live")

KIND = 19
POS, REQUEST, ANSWER, FINISH, LEFT = 1, 2, 3, 4, 5
NOTICE, PROMPT, START, END, CONFIG = 16, 17, 18, 19, 20
WON, LOST, NO_WINNER, CALLED_OFF = 1, 2, 3, 4

ANSWER_SECONDS = 10       # the challenged player's time to answer
COUNTDOWN_MS = 3000
RACE_SECONDS = 600        # no winner after this
POS_STALE = 3.0           # a position older than this doesn't count for a REQUEST
GONE_SECONDS = 15.0       # a racer without positions this long has left the race
LEFT_GRACE = 3.0          # both racers leaving the free roam this close together (an event
                          # started in the world) calls the race off instead of a forfeit

# Settings (add_arguments / configure).
RANGE = 40.0              # how close behind the other car the challenger must be (m)
ANY_DIRECTION = False     # tests: the other car need not be ahead
TEST_FINISH = 0.0         # tests: the finish this far ahead of the challenged car (m)
MIN_DISTANCE, BEST_DISTANCE, MAX_DISTANCE = 1200.0, 2500.0, 5000.0

# Landmarks of Colorado: the endpoints of the game's DriveFromAToBFreeRoamChallenge
# entries in media/gametunablesettings.zip FreeRoamChallenges.xml (world x, z, then the
# height y; y is up).
DESTINATIONS = [
    ("Carson Warehouses", -4404, 1410, -9),
    ("Red Foot Ranch", -2358, -4981, 19),
    ("Red Rock Outpost", -5668, -5279, 350),
    ("Finley Dam Tunnel", 6235, 184, 100),
    ("Finley Dam", 6482, 156, 300),
    ("KH Outpost", 2159, -6070, 228),
    ("the Steelworks", -1515, 2613, 42),
    ("the Bunker", 4454, 1103, 170),
    ("the Media Centre", -3387, -1305, 9),
    ("the Lakeside Diner", 1567, -1904, 117),
    ("the Carson fountain", -4093, 832, -11),
    ("the Wind Farm", -1768, -2248, 73),
    ("the Beaumont cable car station", 3089, 3244, 161),
    ("Beaumont Outpost", 3396, 2750, 128),
]
FINISH_RADIUS = 40.0


def add_arguments(parser):
    g = parser.add_argument_group("head-to-head challenges in the Horizon World")
    g.add_argument("--challenge-range", type=float, default=RANGE,
                   help="how close behind another car a challenger must be, in m (default 40)")
    g.add_argument("--challenge-any-direction", action="store_true",
                   help="tests: challenge the closest car in range, ahead or not")
    g.add_argument("--challenge-test-finish", type=float, default=0.0,
                   help="tests: put the finish this many m ahead of the challenged car instead "
                        "of at a landmark")
    g.add_argument("--challenge-finish-radius", type=float, default=FINISH_RADIUS,
                   help="how close to the destination counts as there, in m (default 40)")


def configure(args):
    global RANGE, ANY_DIRECTION, TEST_FINISH, FINISH_RADIUS
    FINISH_RADIUS = args.challenge_finish_radius
    RANGE = args.challenge_range
    ANY_DIRECTION = args.challenge_any_direction
    TEST_FINISH = args.challenge_test_finish


def text16(s):
    b = s.encode()[:1000]
    return struct.pack(">H", len(b)) + b


def text8(s):
    b = s.encode()[:255]
    return bytes([len(b)]) + b


def pick_destination(x, z):
    """The landmark whose distance from (x, z) is closest to BEST_DISTANCE, preferring
    those between MIN_DISTANCE and MAX_DISTANCE."""
    def score(d):
        dist = math.hypot(d[1] - x, d[2] - z)
        return (not MIN_DISTANCE <= dist <= MAX_DISTANCE, abs(dist - BEST_DISTANCE))
    return min(DESTINATIONS, key=score)


class Challenge:
    def __init__(self, cid, a, b):
        self.id, self.a, self.b = cid, a, b   # peer ids: challenger, challenged
        self.state = "asked"
        self.since = time.monotonic()
        self.start = 0.0
        self.dest = None
        self.left = {}  # peer id -> when it left the free roam (racing)

    def other(self, pid):
        return self.b if pid == self.a else self.a

    def info(self, names):
        return {"id": self.id, "challenger": names.get(self.a), "challenged": names.get(self.b),
                "state": self.state, "destination": self.dest[0] if self.dest else None,
                "seconds": int(time.monotonic() - self.since)}


class Challenges:
    """The server side. `send(peer_id, body)` sends a CHALLENGE message, `world(peer_id)`
    gives the world session id a player is in (or None), `name(peer_id)` its gamertag
    (None when it left the server)."""

    def __init__(self, send, world, name):
        self.send, self.world, self.name = send, world, name
        self.pos = {}           # peer id -> (x, y, z, hx, hz, speed, time)
        self.by_peer = {}       # peer id -> Challenge
        self.next_id = 1

    def notice(self, pid, text, seconds=4):
        self.send(pid, bytes([NOTICE, seconds]) + text16(text))

    def end(self, c, results):
        """Ends challenge c: results {peer id: (outcome, text)}."""
        for pid in (c.a, c.b):
            out, text = results.get(pid, (CALLED_OFF, "Challenge called off"))
            self.send(pid, bytes([END]) + struct.pack(">IB", c.id, out) + text16(text))
            self.by_peer.pop(pid, None)

    def on_message(self, pid, body):
        op = body[0]
        if op == POS:
            if pid not in self.pos:
                self.send(pid, bytes([CONFIG]) + struct.pack(">fB", RANGE, ANY_DIRECTION))
            self.pos[pid] = struct.unpack_from(">6f", body, 1) + (time.monotonic(),)
        elif op == REQUEST:
            self.request(pid)
        elif op == ANSWER:
            cid, accept = struct.unpack_from(">IB", body, 1)
            self.answer(pid, cid, bool(accept))
        elif op == FINISH:
            cid, ms = struct.unpack_from(">II", body, 1)
            self.finish(pid, cid, ms)
        elif op == LEFT:
            self.pos.pop(pid, None)
            c = self.by_peer.get(pid)
            if c and c.state == "racing":
                c.left[pid] = time.monotonic()  # decided in tick (LEFT_GRACE)
            else:
                self.left(pid, "left the free roam")

    def request(self, pid):
        if pid in self.by_peer:
            return  # already challenging, challenged or racing
        me = self.pos.get(pid)
        now = time.monotonic()
        world = self.world(pid)
        if not me or now - me[6] > POS_STALE or world is None:
            self.notice(pid, "Head-to-head\nDrive in the Horizon World to challenge someone")
            return
        hx, hz = me[3], me[4]
        hl = math.hypot(hx, hz) or 1.0
        best = None
        for other, p in self.pos.items():
            if other == pid or now - p[6] > POS_STALE or self.world(other) != world:
                continue
            dx, dz = p[0] - me[0], p[2] - me[2]
            dist = math.hypot(dx, dz)
            if dist > RANGE:
                continue
            ahead = (dx * hx + dz * hz) / (hl * dist) if dist > 0.1 else 1.0
            if not ANY_DIRECTION and ahead < 0.5:
                continue
            if best is None or dist < best[0]:
                best = (dist, other)
        if best is None:
            self.notice(pid, "Head-to-head\nGet right behind another driver, then press X")
            log.info("challenge: #%d %r: nobody close ahead", pid, self.name(pid))
            return
        other = best[1]
        if other in self.by_peer:
            self.notice(pid, f"Head-to-head\n{self.name(other)} is busy with another challenge")
            return
        c = Challenge(self.next_id, pid, other)
        self.next_id += 1
        self.by_peer[pid] = self.by_peer[other] = c
        log.info("challenge %d: #%d %r challenges #%d %r (%.0f m)", c.id, pid, self.name(pid),
                 other, self.name(other), best[0])
        self.send(other, bytes([PROMPT]) + struct.pack(">IB", c.id, ANSWER_SECONDS) +
                  text8(self.name(pid) or "?"))
        self.notice(pid, f"Head-to-head\nChallenge sent to {self.name(other)}...",
                    ANSWER_SECONDS)

    def answer(self, pid, cid, accept):
        c = self.by_peer.get(pid)
        if not c or c.id != cid or c.b != pid or c.state != "asked":
            return
        if not accept:
            log.info("challenge %d: declined", c.id)
            self.end(c, {c.a: (CALLED_OFF, f"{self.name(c.b)} declined your challenge"),
                         c.b: (CALLED_OFF, "Challenge declined")})
            return
        a, b = self.pos.get(c.a), self.pos.get(c.b)
        if not a or not b:
            self.end(c, {})
            return
        if TEST_FINISH > 0:
            hl = math.hypot(b[3], b[4]) or 1.0
            c.dest = ("the test finish", b[0] + b[3] / hl * TEST_FINISH,
                      b[2] + b[4] / hl * TEST_FINISH, b[1])
        else:
            c.dest = pick_destination((a[0] + b[0]) / 2, (a[2] + b[2]) / 2)
        c.state = "racing"
        c.start = time.monotonic() + COUNTDOWN_MS / 1000
        dist = math.hypot(c.dest[1] - b[0], c.dest[2] - b[2])
        log.info("challenge %d: accepted, race to %s (%.0f, %.0f), %.0f m", c.id, c.dest[0],
                 c.dest[1], c.dest[2], dist)
        for me, other in ((c.a, c.b), (c.b, c.a)):
            self.send(me, bytes([START]) + struct.pack(">IHffff", c.id, COUNTDOWN_MS, c.dest[1],
                                                       c.dest[3], c.dest[2], FINISH_RADIUS) +
                      text8(self.name(other) or "?") + text8(c.dest[0]))

    def finish(self, pid, cid, ms):
        c = self.by_peer.get(pid)
        if not c or c.id != cid or c.state != "racing":
            return
        t = f"{ms // 60000}:{ms // 1000 % 60:02d}.{ms // 100 % 10}"
        log.info("challenge %d: #%d %r wins in %s", c.id, pid, self.name(pid), t)
        self.end(c, {pid: (WON, f"You beat {self.name(c.other(pid))} to {c.dest[0]} ({t})"),
                     c.other(pid): (LOST, f"{self.name(pid)} got to {c.dest[0]} first ({t})")})

    def left(self, pid, why):
        c = self.by_peer.get(pid)
        if not c:
            return
        other = c.other(pid)
        name = self.name(pid) or "Your rival"
        log.info("challenge %d: #%d %s", c.id, pid, why)
        self.by_peer.pop(pid, None)
        if c.state == "racing":
            self.end(c, {other: (WON, f"{name} left: you win the head-to-head")})
        else:
            self.end(c, {other: (CALLED_OFF, f"{name} left: challenge called off")})

    def drop(self, pid):
        """The player left the server."""
        self.pos.pop(pid, None)
        self.left(pid, "left the server")

    def tick(self):
        now = time.monotonic()
        for c in {id(c): c for c in self.by_peer.values()}.values():
            if c.state == "asked" and now - c.since > ANSWER_SECONDS + 1:
                log.info("challenge %d: no answer", c.id)
                self.end(c, {c.a: (CALLED_OFF, f"{self.name(c.b)} didn't answer your challenge"),
                             c.b: (CALLED_OFF, "Challenge expired")})
            elif c.state == "racing" and c.left:
                if len(c.left) == 2:
                    log.info("challenge %d: both left the free roam: called off", c.id)
                    self.end(c, {pid: (CALLED_OFF, "Race called off") for pid in (c.a, c.b)})
                elif now - min(c.left.values()) > LEFT_GRACE:
                    self.left(next(iter(c.left)), "left the free roam")
            elif c.state == "racing":
                for pid in (c.a, c.b):
                    p = self.pos.get(pid)
                    if not p or now - p[6] > GONE_SECONDS:
                        self.left(pid, "stopped driving in the world")
                        break
                else:
                    if now - c.start > RACE_SECONDS:
                        self.end(c, {pid: (NO_WINNER, "Time's up: no winner") for pid in (c.a, c.b)})

    def status(self):
        names = {}
        for c in self.by_peer.values():
            names[c.a], names[c.b] = self.name(c.a), self.name(c.b)
        seen = {id(c): c for c in self.by_peer.values()}
        return {"challenges": [c.info(names) for c in seen.values()],
                "positions": {str(pid): [round(v, 1) for v in p[:6]] + [round(time.monotonic() - p[6], 1)]
                              for pid, p in self.pos.items()}}

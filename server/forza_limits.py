"""Abuse limits for a public Forza Live server: every upload is untrusted.

accept() is called before any blob (ghost, shared car, livery, thumbnail, auction or gift
car) is written: one blob may not exceed MAX_BLOB bytes and the server's blobs together
stay under DISK_CAP (env FORZA_DISK_CAP_MB, default 4096). A ValueError becomes a "bad
parameters" failure for the game, which carries on without the upload.
"""

import os
import time

MAX_BLOB = 2 << 20
DISK_CAP = int(os.environ.get("FORZA_DISK_CAP_MB", "4096")) << 20
MAX_PLAYERS = int(os.environ.get("FORZA_MAX_PLAYERS", "20000"))  # player records on disk
PER_PLAYER = {"auctions": 30, "shared_cars": 100, "gifts": 50}  # open items per player
BLOB_DIRS = ("ghosts", "market", "clubs")

_data_dir = "forza_live_data"
_cache = [0.0, 0]  # time of the last scan, bytes found
_added = [0]       # bytes accepted since


def configure(data_dir):
    global _data_dir
    _data_dir = data_dir


def usage():
    now = time.monotonic()
    if now - _cache[0] > 30:
        total = 0
        for sub in BLOB_DIRS:
            for root, _, names in os.walk(os.path.join(_data_dir, sub)):
                for name in names:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        pass
        _cache[0], _cache[1], _added[0] = now, total, 0
    return _cache[1] + _added[0]


def accept(nbytes):
    if nbytes > MAX_BLOB:
        raise ValueError("upload of %d bytes refused" % nbytes)
    if usage() + nbytes > DISK_CAP:
        raise ValueError("server disk quota reached")
    _added[0] += nbytes

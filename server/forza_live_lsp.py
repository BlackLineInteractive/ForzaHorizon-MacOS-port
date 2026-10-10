"""Forza Live title servers ("LSP"): HTTP requests the game makes to Turn 10's services.

forza_live_server.py calls handle() for every HTTP request on --http-port that isn't the
status page. Forza Horizon's title services are not mapped yet, so this logs every
request (and with --dump-requests saves it under DATA_DIR/requests) and answers 404,
which a game treats as "file not there" or "service unavailable". Files an operator puts
under DATA_DIR/storage/<request path> are served as they are.
"""

import logging
import os
import time
import urllib.parse

log = logging.getLogger("forza-live")

DATA_DIR = "forza_live_data"
DUMP = False


def add_arguments(parser):
    parser.add_argument("--data-dir", default=os.environ.get("FORZA_LIVE_DATA", "forza_live_data"),
                        help="player data and operator-provided title storage files "
                             "(default ./forza_live_data)")
    parser.add_argument("--dump-requests", action="store_true",
                        help="save every title server request to DATA_DIR/requests")


def configure(args):
    global DATA_DIR, DUMP
    DATA_DIR = args.data_dir
    DUMP = args.dump_requests
    os.makedirs(DATA_DIR, exist_ok=True)


def dump(method, path, headers, body):
    folder = os.path.join(DATA_DIR, "requests")
    os.makedirs(folder, exist_ok=True)
    name = "%d-%s-%s" % (int(time.time() * 1000), method,
                         urllib.parse.quote(path, safe="")[:100])
    with open(os.path.join(folder, name), "wb") as f:
        f.write(("\r\n".join(f"{k}: {v}" for k, v in headers.items()) + "\r\n\r\n").encode())
        f.write(body)


def stored_file(path):
    rel = os.path.normpath(path.lstrip("/"))
    if rel.startswith(".."):
        return None
    full = os.path.join(DATA_DIR, rel)
    if os.path.isfile(full):
        with open(full, "rb") as f:
            return f.read()
    return None


def handle(server, method, path, headers, body, peer):
    """Returns (HTTP status, content type, body bytes)."""
    if DUMP:
        dump(method, path, headers, body)
    log.info("LSP request %s %s (%d bytes, headers %s)", method, path, len(body),
             ", ".join(f"{k}={v}" for k, v in headers.items()))
    url = urllib.parse.urlsplit(path)
    if url.path.startswith("/storage/") and method == "GET":
        data = stored_file(url.path)
        if data is not None:
            return 200, "application/octet-stream", data
    return 404, "text/plain", b"not found"

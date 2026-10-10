#!/usr/bin/env python3
"""Install DLC packages (STFS marketplace content) where the runtime looks for them.

Usage: install_dlc.py [--user-data DIR] PACKAGE_OR_DIR [...]

Each package is extracted to DIR/0000000000000000/<title id>/00000002/<package name>/ and
gets a content header in DIR/0000000000000000/<title id>/Headers/00000002/<name>.header
(XCONTENT_AGGREGATE_DATA, 0x148 bytes, plus a license mask of 0xFFFFFFFF: all offers
unlocked). That is the layout of the ReXGlue SDK's ContentManager, the same as Xenia's
content folder. A directory argument installs every package in it. DIR defaults to
~/.local/share/forza (the game's user data root). Packages are only read.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcontent_extract  # noqa: E402

MARKETPLACE = 2
DEVICE_HDD = 1


def header_bytes(name, display_name, title_id):
    data = struct.pack(">II", DEVICE_HDD, MARKETPLACE)
    data += display_name.encode("utf-16-be")[:254].ljust(256, b"\0")
    data += name.encode("ascii")[:42].ljust(42, b"\0") + b"\0\0"
    data += b"\0" * 4  # alignment before the 64-bit XUID
    data += struct.pack(">QI", 0, title_id) + b"\0" * 4
    assert len(data) == 0x148
    return data + struct.pack("<I", 0xFFFFFFFF)  # the runtime reads it in host order


def install(path, user_data):
    pkg = xcontent_extract.open_package(path)
    h = pkg.hdr
    if h.content_type != MARKETPLACE:
        print(f"skipping {path}: content type 0x{h.content_type:X} is not marketplace content")
        return
    name = os.path.basename(path)
    root = os.path.join(user_data, "0000000000000000", f"{h.title_id:08X}")
    dest = os.path.join(root, "00000002", name)
    total = 0
    for entry in pkg.entries():
        xcontent_extract.extract(pkg, entry, dest)
        total += entry.size
    headers = os.path.join(root, "Headers", "00000002")
    os.makedirs(headers, exist_ok=True)
    with open(os.path.join(headers, name + ".header"), "wb") as f:
        f.write(header_bytes(name, h.display_name, h.title_id))
    print(f"{h.display_name}: {total} bytes -> {dest}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("packages", nargs="+")
    ap.add_argument("--user-data", default=os.path.expanduser("~/.local/share/forza"))
    a = ap.parse_args()
    for p in a.packages:
        if os.path.isdir(p):
            for n in sorted(os.listdir(p)):
                if os.path.isfile(os.path.join(p, n)):
                    install(os.path.join(p, n), a.user_data)
        else:
            install(p, a.user_data)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""List references to a guest address in a XEX image: direct branches (b/bl/bc) to it,
lis+addi/ori pairs that build it, and 32-bit words in data sections equal to it.

Usage: xrefs.py ADDR [ADDR ...] [--xex extracted/game/default.xex]
A quick stand-in for Ghidra's xrefs; indirect calls through registers are not found.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xex_image  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", nargs="+")
    ap.add_argument("--xex", default="extracted/game/default.xex")
    a = ap.parse_args()
    targets = {int(x, 16) for x in a.addrs}
    load, image = xex_image.load_image(a.xex)
    for name, start, end, executable in xex_image.sections(load, image):
        if name in (".reloc", ".pdata"):
            continue
        data = image[start - load:end - load]
        words = struct.unpack(f">{len(data) // 4}I", data[:len(data) // 4 * 4])
        for i, w in enumerate(words):
            addr = start + 4 * i
            if w in targets:
                print(f"{addr:08X} data word in {name}")
            if not executable:
                continue
            op = w >> 26
            if op == 18:
                off = w & 0x03FFFFFC
                off -= 0x04000000 if off & 0x02000000 else 0
                tgt = (off if w & 2 else addr + off) & 0xFFFFFFFF
                if tgt in targets:
                    print(f"{addr:08X} {'bl' if w & 1 else 'b'} {tgt:08X}")
            elif op == 16:
                off = w & 0xFFFC
                off -= 0x10000 if off & 0x8000 else 0
                tgt = (off if w & 2 else addr + off) & 0xFFFFFFFF
                if tgt in targets:
                    print(f"{addr:08X} bc{'l' if w & 1 else ''} {tgt:08X}")
            elif op == 15 and ((w >> 16) & 31) == 0:
                rt, hi = (w >> 21) & 31, w & 0xFFFF
                for k in range(1, 9):
                    if i + k >= len(words):
                        break
                    w2 = words[i + k]
                    op2, lo = w2 >> 26, w2 & 0xFFFF
                    src = (w2 >> 16) & 31 if op2 == 14 else (w2 >> 21) & 31
                    if op2 in (14, 24) and src == rt:
                        v = ((hi << 16) + (lo - 0x10000 if (op2 == 14 and lo & 0x8000) else lo)) & 0xFFFFFFFF
                        if v in targets:
                            print(f"{addr:08X} lis/{'addi' if op2 == 14 else 'ori'} {v:08X}")
                        break


if __name__ == "__main__":
    main()

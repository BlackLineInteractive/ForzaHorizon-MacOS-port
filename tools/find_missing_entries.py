#!/usr/bin/env python3
"""Find guest function entry points that ReXGlue codegen missed.

Candidates are code addresses that are taken indirectly (32-bit big-endian
pointers in data sections, or lis/addi|ori constant pairs in code), are not
registered by the generated code, and sit right after an unconditional
terminator (blr / bctr / b / zero padding), which is where the scanner tends
to glue a vtable-only function onto its predecessor. Addresses right after a
`bl` count too when a data table points at them: the compiler places the next
function directly behind a call to a no-return function (e.g. the fatal error
handler), and return addresses never appear in static data.

Usage: find_missing_entries.py REGISTER_CPP OUT_TOML [--xex extracted/game/default.xex]
Memory comes from the decoded XEX image (tools/xex_image.py). Adapted from
RecompiledHaloReach, where it read memory from a GhidraMCP server.
"""
import argparse
import bisect
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xex_image  # noqa: E402


def load_memory(xex):
    """{section name: (start, bytes, executable)} for the initialized PE sections."""
    load_address, image = xex_image.load_image(xex)
    mem = {}
    for name, start, end, executable in xex_image.sections(load_address, image):
        mem[name] = (start, image[start - load_address:end - load_address], executable)
    return mem


def is_call(w):
    return (w >> 26) == 18 and (w & 3) == 1


def is_terminator(w):
    if w in (0x4E800020, 0x4E800420, 0x00000000):
        return True
    return (w >> 26) == 18 and (w & 3) == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("register_cpp")
    ap.add_argument("out_toml")
    ap.add_argument("--xex", default="extracted/game/default.xex")
    a = ap.parse_args()

    known = {int(m, 16) for m in re.findall(r"SetFunction\(0x([0-9A-Fa-f]+)", open(a.register_cpp).read())}
    mem = load_memory(a.xex)

    text = [(st, st + len(b), b) for st, b, x in mem.values() if x]

    def word_at(addr):
        for st, en, b in text:
            if st <= addr < en - 3:
                return struct.unpack_from(">I", b, addr - st)[0]
        return None

    known_sorted = sorted(known)

    def func_of(addr):
        return known_sorted[bisect.bisect_right(known_sorted, addr) - 1] if addr >= known_sorted[0] else None

    def in_text(v):
        return any(st <= v < en for st, en, _ in text)

    cands = {}
    for name, (st, b, x) in mem.items():
        # .reloc holds relocation records and .pdata function ranges, whose words only
        # look like pointers.
        if x or name in (".reloc", ".pdata"):
            continue
        words = struct.unpack(f">{len(b) // 4}I", b[: len(b) // 4 * 4])
        is_code = [w & 3 == 0 and in_text(w) for w in words]
        i = 0
        while i < len(words):
            if not is_code[i]:
                i += 1
                continue
            j = i
            while j < len(words) and is_code[j]:
                j += 1
            run = words[i:j]
            # Jump tables are runs of interior labels with no real function start;
            # vtables and callback tables nearly always contain known entries.
            if len(run) >= 2 and not any(w in known for w in run):
                i = j
                continue
            for k, v in enumerate(run):
                if v in known:
                    continue
                cands.setdefault(v, set()).add(f"data:{name}:{st + (i + k) * 4:#x}")
            i = j

    for st, en, b in text:
        words = struct.unpack(f">{len(b) // 4}I", b[: len(b) // 4 * 4])
        for i, w in enumerate(words):
            if (w >> 26) != 15 or ((w >> 16) & 31) != 0:
                continue
            rt, hi = (w >> 21) & 31, w & 0xFFFF
            for w2 in words[i + 1 : i + 9]:
                op, lo = w2 >> 26, w2 & 0xFFFF
                src = (w2 >> 16) & 31 if op == 14 else (w2 >> 21) & 31
                if op in (14, 24) and src == rt:
                    if op == 14:
                        v = ((hi << 16) + (lo - 0x10000 if lo & 0x8000 else lo)) & 0xFFFFFFFF
                    else:
                        v = (hi << 16) | lo
                    src_addr = st + i * 4
                    if v & 3 == 0 and in_text(v) and v not in known and func_of(src_addr) != func_of(v):
                        cands.setdefault(v, set()).add(f"code:{src_addr:#x}")
                    break

    # Local (non-linking) branch targets: a label jumped to from inside its own
    # function is a case/EH label, not a separate entry point.
    local_targets = set()
    for st, en, b in text:
        words = struct.unpack(f">{len(b) // 4}I", b[: len(b) // 4 * 4])
        for i, w in enumerate(words):
            op, src = w >> 26, st + i * 4
            if op == 18 and (w & 3) == 0:
                disp = w & 0x03FFFFFC
                disp -= 0x04000000 if disp & 0x02000000 else 0
            elif op == 16 and (w & 3) == 0:
                disp = w & 0xFFFC
                disp -= 0x10000 if disp & 0x8000 else 0
            else:
                continue
            tgt = (src + disp) & 0xFFFFFFFF
            if func_of(tgt) == func_of(src):
                local_targets.add(tgt)

    hints = []
    for v in sorted(cands):
        prev, cur = word_at(v - 4), word_at(v)
        if prev is None or cur in (None, 0) or v in local_targets:
            continue
        from_data = any(why.startswith("data:") for why in cands[v])
        if is_terminator(prev) or (is_call(prev) and from_data):
            hints.append((v, sorted(cands[v])[:3]))

    with open(a.out_toml, "w") as f:
        f.write("[functions]\n")
        f.write("# Generated by tools/find_missing_entries.py: indirectly referenced entry points\n")
        f.write("# missed by codegen (address follows an unconditional terminator, or a call\n")
        f.write("# to a no-return function when a data table points at it).\n")
        for v, why in hints:
            f.write(f"0x{v:08X} = {{ name = \"sub_{v:08X}\" }}  # {', '.join(why)}\n")
    print(f"known={len(known)} candidates={len(cands)} hints={len(hints)} -> {a.out_toml}")


if __name__ == "__main__":
    main()

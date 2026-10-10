#!/usr/bin/env python3
"""Write the loaded memory image of a retail XEX2 (decrypted, decompressed) for analysis.

Usage:
  xex_image.py XEX OUT.bin        raw image, byte 0 = load address
  xex_image.py XEX OUT.elf --elf  the same wrapped in a 32-bit big-endian PowerPC ELF
                                  (one executable section at the load address) so that
                                  `llvm-objdump -d --start-address=...` can disassemble it

Handles AES-encrypted ("Normal") or plain images with "Basic" (zero-run) compression,
which is what Forza Horizon's default.xex and its facade DLLs use; LZX-compressed
images are refused. Decryption calls `openssl enc` (Python's standard library has no
AES). The XEX is only read.
"""
import struct
import subprocess
import sys

RETAIL_KEY = bytes.fromhex("20B185A59D28FDC340583FBB0896BF91")


def aes(mode, key, data):
    out = subprocess.run(
        ["openssl", "enc", "-d", f"-aes-128-{mode}", "-K", key.hex(), "-iv", "00" * 16, "-nopad"]
        if mode == "cbc" else
        ["openssl", "enc", "-d", "-aes-128-ecb", "-K", key.hex(), "-nopad"],
        input=data, capture_output=True, check=True)
    return out.stdout


def load_image(path):
    raw = open(path, "rb").read()
    if raw[:4] != b"XEX2":
        raise SystemExit(f"{path}: not an XEX2 file")
    _, _, pe_offset, _, sec_offset, opt_count = struct.unpack_from(">4sIIIII", raw, 0)
    opts = {}
    for i in range(opt_count):
        key, value = struct.unpack_from(">II", raw, 0x18 + i * 8)
        opts[key] = value
    if 0x3FF not in opts:
        raise SystemExit("no file format info header")
    ffi = opts[0x3FF]
    info_size, encryption, compression = struct.unpack_from(">IHH", raw, ffi)
    image_size, = struct.unpack_from(">I", raw, sec_offset + 4)
    load_address, = struct.unpack_from(">I", raw, sec_offset + 0x110)
    data = raw[pe_offset:]
    if encryption == 1:
        session_key = aes("ecb", RETAIL_KEY, raw[sec_offset + 0x150:sec_offset + 0x160])
        data = aes("cbc", session_key, data[:len(data) // 16 * 16])
    elif encryption != 0:
        raise SystemExit(f"unknown encryption type {encryption}")
    if compression == 1:
        image = bytearray()
        pos = 0
        for off in range(ffi + 8, ffi + info_size, 8):
            data_size, zero_size = struct.unpack_from(">II", raw, off)
            image += data[pos:pos + data_size]
            image += bytes(zero_size)
            pos += data_size
    elif compression == 0:
        image = bytearray(data)
    else:
        raise SystemExit(f"compression type {compression} (LZX) is not supported")
    image = bytes(image[:image_size]).ljust(image_size, b"\0")
    if image[:2] != b"MZ":
        raise SystemExit("decoded image has no MZ header (wrong key?)")
    return load_address, image


def sections(load_address, image):
    """PE sections of a loaded image: [(name, start, end, executable)]."""
    pe, = struct.unpack_from("<I", image, 0x3C)
    count, = struct.unpack_from("<H", image, pe + 6)
    opt_size, = struct.unpack_from("<H", image, pe + 20)
    table = pe + 24 + opt_size
    out = []
    for i in range(count):
        name, vsize, vaddr = struct.unpack_from("<8sII", image, table + i * 40)
        flags, = struct.unpack_from("<I", image, table + i * 40 + 36)
        start = load_address + vaddr
        out.append((name.rstrip(b"\0").decode("latin-1"), start, start + vsize, bool(flags & 0x20000000)))
    return out


def write_elf(path, load_address, image):
    # ELF32 big-endian, EM_PPC, one PROGBITS section .text (AX) at load_address.
    shstr = b"\0.text\0.shstrtab\0"
    ehsize, shentsize = 52, 40
    text_off = 0x100
    shstr_off = text_off + len(image)
    sh_off = (shstr_off + len(shstr) + 3) & ~3
    eh = struct.pack(">16sHHIIIIIHHHHHH",
                     b"\x7fELF\x01\x02\x01" + bytes(9), 2, 20, 1, load_address, 0, sh_off, 0,
                     ehsize, 0, 0, shentsize, 3, 2)
    sections = [bytes(shentsize),
                struct.pack(">IIIIIIIIII", 1, 1, 6, load_address, text_off, len(image), 0, 0, 4, 0),
                struct.pack(">IIIIIIIIII", 7, 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0)]
    with open(path, "wb") as f:
        f.write(eh.ljust(text_off, b"\0"))
        f.write(image)
        f.write(shstr)
        f.write(bytes(sh_off - shstr_off - len(shstr)))
        f.write(b"".join(sections))


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    load_address, image = load_image(sys.argv[1])
    if "--elf" in sys.argv[3:]:
        write_elf(sys.argv[2], load_address, image)
    else:
        open(sys.argv[2], "wb").write(image)
    print(f"{sys.argv[2]}: load address 0x{load_address:08X}, {len(image)} bytes")


if __name__ == "__main__":
    main()

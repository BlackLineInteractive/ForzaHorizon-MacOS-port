# unzip21.py ZIP MEMBER OUTDIR: extract a member of one of the game's zips (method 21 is
# XMemCompress LZX: decoded by tools/unxmem, built from tools/unxmem.c; see there).
# Example: tools/unzip21.py extracted/game/media/gametunablesettings.zip FreeRoamChallenges.xml /tmp
import sys, zipfile, struct, subprocess, os
z = zipfile.ZipFile(sys.argv[1])
i = z.getinfo(sys.argv[2])
f = open(sys.argv[1], 'rb'); f.seek(i.header_offset)
h = f.read(30); n, m = struct.unpack('<HH', h[26:30]); f.seek(i.header_offset + 30 + n + m)
raw = f.read(i.compress_size)
out = os.path.join(sys.argv[3], os.path.basename(i.filename))
if i.compress_type == 0: open(out, 'wb').write(raw)
else:
    open(out + '.lzx', 'wb').write(raw)
    subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unxmem'), out + '.lzx', out, str(i.file_size)])
    os.remove(out + '.lzx')
print(out)

// unxmem IN OUT SIZE: decode XMemCompress LZX data (zip method 21, the game's media/*.zip) to
// OUT (SIZE bytes). Used by tools/unzip21.py. Build with the SDK's libmspack:
//   gcc -O1 -I ~/rexglue-sdk-src-forza/sdk/thirdparty/libmspack/libmspack/mspack -o unxmem \
//       tools/unxmem.c ~/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64/lib/libmspack.a
// A block is FF, u16 uncompressed size, u16 compressed size, data (or u16 compressed size,
// data for a full 32 KB block); the blocks' data is one LZX stream with a 128 KB window.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mspack.h>
#include <lzx.h>
typedef struct { struct mspack_system sys; } S;
typedef struct { unsigned char* buf; long size, off; } MF;
static int rd(struct mspack_file* f, void* b, int n) { MF* m = (MF*)f; long r = m->size - m->off; if (n < r) r = n; memcpy(b, m->buf + m->off, r); m->off += r; return (int)r; }
static int wr(struct mspack_file* f, void* b, int n) { MF* m = (MF*)f; long r = m->size - m->off; if (n < r) r = n; memcpy(m->buf + m->off, b, r); m->off += r; return n; }
static void* al(struct mspack_system* s, size_t n) { return calloc(n, 1); }
static void fr(void* p) { free(p); }
static void cp(void* s, void* d, size_t n) { memcpy(d, s, n); }
int main(int argc, char** argv) {
  FILE* f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  unsigned char* in = malloc(n); fread(in, 1, n, f); fclose(f);
  long size = atol(argv[3]);
  unsigned char* cat = malloc(n); long cn = 0, pos = 0;
  while (pos < n) {
    long comp;
    if (in[pos] == 0xFF) { comp = (in[pos + 3] << 8) | in[pos + 4]; pos += 5; }
    else { comp = (in[pos] << 8) | in[pos + 1]; pos += 2; }
    if (comp == 0 || pos + comp > n) break;
    memcpy(cat + cn, in + pos, comp); cn += comp; pos += comp;
  }
  struct mspack_system sys = {0}; sys.read = rd; sys.write = wr; sys.alloc = al; sys.free = fr; sys.copy = cp;
  MF src = {cat, cn, 0}; unsigned char* out = calloc(size, 1); MF dst = {out, size, 0};
  struct lzxd_stream* z = lzxd_init(&sys, (struct mspack_file*)&src, (struct mspack_file*)&dst, 17, 0, 0x8000, size, 0);
  int r = lzxd_decompress(z, size);
  fprintf(stderr, "lzxd %d, %ld bytes in %ld compressed\n", r, dst.off, cn);
  FILE* o = fopen(argv[2], "wb"); fwrite(out, 1, dst.off, o); fclose(o);
  return r;
}

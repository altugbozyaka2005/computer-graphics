#!/usr/bin/env python3
"""Converts an 8-bit PNG (e.g. a photo) to a binary PPM texture, standard library only.

Usage: python3 png2ppm.py photo.png texture.ppm [max_size]
JPEG/HEIC photos: convert first on macOS with  sips -s format png photo.jpg --out photo.png
max_size (optional) downsamples so that the longer side is at most max_size pixels.
"""
import struct
import sys
import zlib


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat = 8, b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype, chunk = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or color not in (0, 2, 4, 6) or interlace:
                raise ValueError("only 8-bit, non-interlaced grey/RGB/RGBA PNGs are supported "
                                 "(re-export with: sips -s format png in.png --out out.png)")
            bpp = {0: 1, 2: 3, 4: 2, 6: 4}[color]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    rows, p = [], 0
    for _ in range(h):
        ft, line = raw[p], bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) if bpp >= 3 else (line[x * bpp],) * 3 for x in range(w)])
        prev = line
    return w, h, rows


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    w, h, rows = read_png(sys.argv[1])
    step = 1
    if len(sys.argv) > 3:
        m = int(sys.argv[3])
        while max(w, h) / step > m:
            step += 1
    ow, oh = w // step, h // step
    out = bytearray()
    for y in range(oh):
        for x in range(ow):
            acc = [0, 0, 0]
            for yy in range(y * step, y * step + step):
                for xx in range(x * step, x * step + step):
                    for k in range(3):
                        acc[k] += rows[yy][xx][k]
            out += bytes(v // (step * step) for v in acc)
    with open(sys.argv[2], "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (ow, oh))
        f.write(out)
    print("wrote %s (%dx%d)" % (sys.argv[2], ow, oh))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Runs every test in this folder (test1, test2, ...) against a renderer and checks the results.

Python 3 standard library only. Usage (from anywhere):

  python3 studentTests/runAllTests.py                         # renderer ../output/CGR26_renderer
  python3 studentTests/runAllTests.py --renderer /path/to/CGR26_renderer
  python3 studentTests/runAllTests.py --tests 1,7,12          # a subset
  python3 studentTests/runAllTests.py --outdir DIR            # where the renderer writes its images/logs

Each testN/test.json describes one test: the scene (testscene_N.pbrt), its category and how the
renderer's output is compared with the reference (testsuite_ref_N.pfm, rendered by pbrt-v4, or an
analytic image where pbrt-v4 has no equivalent). For every test the renderer is started as

  <renderer> <abs path>/testN/testscene_N.pbrt  [extra args]      (working directory testN/)

and its image is looked up in --outdir (default: the renderer's directory, which the coursework
requires to be output/) as testsuite_my_N.{pfm,png,ppm} or testscene_N.{pfm,png,ppm}, and its log as
testsuite_my_N.log or testscene_N.log (stdout/stderr are used when there is no log file).

Categories and pass criteria (thresholds are in each test.json):
  camera   coverage: the object silhouettes, as per-pixel coverage (pixel value / object value);
                     fails if more than `max_mismatch` of the pixels are on the wrong side of the
                     edge (ignoring pixels the reference shows as partly covered) or if the mean
                     signed edge offset exceeds `max_offset` pixels, or (optional) if the mean
                     |coverage difference| on edge pixels exceeds `max_edge_abs_diff` (e.g. defocus
                     blur of the wrong width). A difference image is written.
           centroids: the centroids of small markers near the image border; fails if any moves by
                     more than `max_centroid_error` pixels (checks the field of view / framing).
  shading  pixels:   (2w+1)^2-pixel means at listed pixels; error = max over channels of
                     |mine - ref| / max(luminance of ref, floor); fails above `max_rel_error`.
  error    the scene has a deliberate error: passes if the renderer neither crashes nor hangs and
           its log (or console output) reports an error/warning that mentions one of `keywords`.

Results: studentTests/runAllTests.log (summary), studentTests/results/testN/ (outputs, console
output, comparable PNGs of mine/ref with the same display mapping, difference images).
Exit status: 0 if every test passed, 1 otherwise.
"""
import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE_EXTS = (".pfm", ".png", ".ppm")


# ================================================================ images (linear RGB, top row first)
class Image:
    def __init__(self, w, h, data):
        self.w, self.h, self.data = w, h, data  # data: flat list r,g,b,...

    def rgb(self, x, y):
        i = 3 * (y * self.w + x)
        return self.data[i], self.data[i + 1], self.data[i + 2]

    def lum(self, x, y):
        r, g, b = self.rgb(x, y)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b


def read_pfm(path):
    with open(path, "rb") as f:
        kind = f.readline().strip()
        if kind not in (b"PF", b"Pf"):
            raise ValueError("not a PFM file")
        dims = f.readline().split()
        while len(dims) < 2:
            dims += f.readline().split()
        w, h = int(dims[0]), int(dims[1])
        scale = float(f.readline())
        ch = 3 if kind == b"PF" else 1
        raw = f.read(w * h * ch * 4)
    vals = struct.unpack(("<" if scale < 0 else ">") + "%df" % (w * h * ch), raw)
    data = [0.0] * (w * h * 3)
    for y in range(h):  # PFM rows go bottom to top
        src = (h - 1 - y) * w * ch
        dst = y * w * 3
        for x in range(w):
            for c in range(3):
                data[dst + 3 * x + c] = vals[src + x * ch + (c if ch == 3 else 0)]
    return Image(w, h, data)


def write_pfm(path, img):
    rows = []
    for y in range(img.h - 1, -1, -1):
        rows.append(struct.pack("<%df" % (img.w * 3), *img.data[3 * y * img.w:3 * (y + 1) * img.w]))
    with open(path, "wb") as f:
        f.write(b"PF\n%d %d\n-1.0\n" % (img.w, img.h))
        f.write(b"".join(rows))


def read_png(path):
    """8/16-bit greyscale, grey+alpha, RGB, RGBA (non-interlaced, no palette) -> values in [0,1]."""
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG file")
        idat, w = b"", 0
        while True:
            n = struct.unpack(">I", f.read(4))[0]
            typ = f.read(4)
            chunk = f.read(n)
            f.read(4)
            if typ == b"IHDR":
                w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            elif typ == b"IDAT":
                idat += chunk
            elif typ == b"IEND":
                break
    if interlace or ctype == 3 or depth not in (8, 16):
        raise ValueError("unsupported PNG (interlaced, palette or bit depth %d)" % depth)
    nch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    bpp = nch * depth // 8
    stride = w * bpp
    raw = zlib.decompress(idat)
    out = bytearray(h * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
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
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    maxv = 255.0 if depth == 8 else 65535.0
    data = [0.0] * (w * h * 3)
    for y in range(h):
        for x in range(w):
            o = y * stride + x * bpp
            vals = []
            for c in range(nch):
                if depth == 8:
                    vals.append(out[o + c] / maxv)
                else:
                    vals.append((out[o + 2 * c] * 256 + out[o + 2 * c + 1]) / maxv)
            rgb = (vals[0], vals[0], vals[0]) if nch <= 2 else vals[:3]
            data[3 * (y * w + x):3 * (y * w + x) + 3] = rgb
    return Image(w, h, data)


def read_ppm(path):
    with open(path, "rb") as f:
        content = f.read()
    tokens, pos = [], 0
    while len(tokens) < 4:  # magic, width, height, maxval (comments allowed)
        while content[pos:pos + 1].isspace():
            pos += 1
        if content[pos:pos + 1] == b"#":
            while content[pos:pos + 1] not in (b"\n", b""):
                pos += 1
            continue
        start = pos
        while pos < len(content) and not content[pos:pos + 1].isspace():
            pos += 1
        tokens.append(content[start:pos])
    magic, w, h, maxv = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
    if magic == b"P6":
        pos += 1
        if maxv < 256:
            vals = list(content[pos:pos + w * h * 3])
        else:
            vals = list(struct.unpack(">%dH" % (w * h * 3), content[pos:pos + w * h * 6]))
    elif magic == b"P3":
        vals = [int(v) for v in content[pos:].split()[:w * h * 3]]
    else:
        raise ValueError("unsupported PPM type %r" % magic)
    return Image(w, h, [v / float(maxv) for v in vals])


def srgb_to_linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def load_image(path, ldr_encoding="srgb"):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pfm":
        return read_pfm(path)
    img = read_png(path) if ext == ".png" else read_ppm(path)
    if ldr_encoding == "srgb":
        img.data = [srgb_to_linear(v) for v in img.data]
    return img


def write_png(path, w, h, rgb8):
    """8-bit RGB PNG from a flat list of 0..255 ints."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += bytes(rgb8[3 * y * w:3 * (y + 1) * w])

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def to_srgb8(v):
    v = max(0.0, min(1.0, v))
    v = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return int(round(v * 255))


def display_png(path, img, exposure):
    """Same display mapping for mine and ref: scale by `exposure`, clamp, sRGB."""
    write_png(path, img.w, img.h, [to_srgb8(v * exposure) for v in img.data])


# ================================================================ metrics
def percentile(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def object_level(img):
    """Value of a fully covered object pixel: a high percentile of the non-background pixels."""
    vals = [img.lum(x, y) for y in range(img.h) for x in range(img.w)]
    nz = [v for v in vals if v > 1e-6]
    return percentile(nz, 0.98) or 1.0


def coverage_metric(t, ref, mine, resdir, n):
    lr, lm = object_level(ref), object_level(mine)
    W, H = ref.w, ref.h
    mismatch, edge, net, absd, inter, union = 0, 0, 0.0, 0.0, 0.0, 0.0
    diff = [0] * (W * H * 3)
    for y in range(H):
        for x in range(W):
            cr = min(1.0, ref.lum(x, y) / lr)
            cm = min(1.0, max(0.0, mine.lum(x, y) / lm))
            inter += min(cr, cm)
            union += max(cr, cm)
            if 0.02 < cr < 0.98:
                edge += 1
            if (cr < 0.25 and cm >= 0.5) or (cr > 0.75 and cm < 0.5):
                mismatch += 1
            net += cm - cr
            absd += abs(cm - cr)
            # difference image: grey = both, red = only mine, cyan = only reference
            i = 3 * (y * W + x)
            g = int(255 * min(cr, cm) * 0.6)
            diff[i:i + 3] = [min(255, g + int(255 * max(0.0, cm - cr))), min(255, g + int(255 * max(0.0, cr - cm))),
                             min(255, g + int(255 * max(0.0, cr - cm)))]
    write_png(os.path.join(resdir, "diff_%d.png" % n), W, H, diff)
    frac = mismatch / float(W * H)
    offset = net / max(1, edge)  # area difference / edge length (in pixels): mean outward shift of edges
    mean_abs = absd / max(1, edge)
    ok = frac <= t["max_mismatch"] and abs(offset) <= t["max_offset"] and mean_abs <= t.get("max_edge_abs_diff", 1e9)
    detail = ("wrong-side pixels %d (%.3f%%, max %.3f%%), mean edge offset %+.3f px (max %.2f), "
              "coverage IoU %.4f, mean |coverage diff| on edges %.3f%s" %
              (mismatch, 100 * frac, 100 * t["max_mismatch"], offset, t["max_offset"], inter / max(union, 1e-9),
               mean_abs, " (max %.3f)" % t["max_edge_abs_diff"] if "max_edge_abs_diff" in t else ""))
    return ok, detail, {"mismatch_pct": 100 * frac, "edge_offset_px": offset, "iou": inter / max(union, 1e-9)}


def blob_centroid(img, cx, cy, r, level):
    sx = sy = sw = 0.0
    for y in range(max(0, int(cy - r)), min(img.h, int(cy + r) + 1)):
        for x in range(max(0, int(cx - r)), min(img.w, int(cx + r) + 1)):
            w = max(0.0, img.lum(x, y) - 0.02 * level)
            sx += w * (x + 0.5)
            sy += w * (y + 0.5)
            sw += w
    return (sx / sw, sy / sw) if sw > 0 else (float("nan"), float("nan"))


def centroid_metric(t, ref, mine, resdir, n):
    lr, lm = object_level(ref), object_level(mine)
    errs, lines = [], []
    for m in t["markers"]:
        rx, ry = blob_centroid(ref, m["x"], m["y"], t["radius"], lr)
        mx, my = blob_centroid(mine, m["x"], m["y"], t["radius"], lm)
        e = math.hypot(mx - rx, my - ry) if mx == mx else float("inf")
        errs.append(e)
        lines.append("%s ref (%.2f, %.2f) mine (%.2f, %.2f) err %.3f px" % (m["label"], rx, ry, mx, my, e))
    worst = max(errs)
    ok = worst <= t["max_centroid_error"]
    detail = "marker centroid error: max %.3f px, mean %.3f px (max allowed %.2f); " % (
        worst, sum(errs) / len(errs), t["max_centroid_error"]) + "; ".join(lines)
    return ok, detail, {"max_centroid_err_px": worst, "mean_centroid_err_px": sum(errs) / len(errs)}


def window_mean(img, x, y, w):
    s, n = [0.0, 0.0, 0.0], 0
    for yy in range(max(0, y - w), min(img.h, y + w + 1)):
        for xx in range(max(0, x - w), min(img.w, x + w + 1)):
            c = img.rgb(xx, yy)
            for k in range(3):
                s[k] += c[k]
            n += 1
    return [v / n for v in s]


def pixel_metric(t, ref, mine, resdir, n):
    w = t.get("window", 1)
    mean_lum = sum(ref.lum(x, y) for y in range(ref.h) for x in range(ref.w)) / (ref.w * ref.h)
    floor = max(t.get("floor", 0.05) * mean_lum, 1e-6)
    rels, lines = [], []
    for p in t["pixels"]:
        r = window_mean(ref, p["x"], p["y"], w)
        m = window_mean(mine, p["x"], p["y"], w)
        lumr = 0.2126 * r[0] + 0.7152 * r[1] + 0.0722 * r[2]
        rel = max(abs(m[k] - r[k]) for k in range(3)) / max(lumr, floor)
        rels.append(rel)
        lines.append("%s (%d,%d): ref %.4f %.4f %.4f mine %.4f %.4f %.4f |d| %.4f %.4f %.4f rel %.2f%%" % (
            p["label"], p["x"], p["y"], r[0], r[1], r[2], m[0], m[1], m[2],
            abs(m[0] - r[0]), abs(m[1] - r[1]), abs(m[2] - r[2]), 100 * rel))
    # Whole-image relative RMSE (information only).
    se = sum((mine.data[i] - ref.data[i]) ** 2 for i in range(len(ref.data))) / len(ref.data)
    rms_ref = math.sqrt(sum(v * v for v in ref.data) / len(ref.data)) or 1.0
    worst = max(rels)
    ok = worst <= t["max_rel_error"]
    detail = "pixel error: max %.2f%%, mean %.2f%% (max allowed %.1f%%), whole-image relative RMSE %.2f%%; " % (
        100 * worst, 100 * sum(rels) / len(rels), 100 * t["max_rel_error"], 100 * math.sqrt(se) / rms_ref) + "; ".join(lines)
    return ok, detail, {"max_rel_err_pct": 100 * worst, "mean_rel_err_pct": 100 * sum(rels) / len(rels),
                        "image_rel_rmse_pct": 100 * math.sqrt(se) / rms_ref}


METRICS = {"coverage": coverage_metric, "centroids": centroid_metric, "pixels": pixel_metric}


# ================================================================ running
def find_file(outdir, stems, exts):
    for stem in stems:
        for ext in exts:
            p = os.path.join(outdir, stem + ext)
            if os.path.exists(p):
                return p
    return None


def run_test(n, t, args, logf):
    tdir = os.path.join(HERE, "test%d" % n)
    resdir = os.path.join(HERE, "results", "test%d" % n)
    os.makedirs(resdir, exist_ok=True)
    stems = ["testsuite_my_%d" % n, os.path.splitext(t["scene"])[0]]
    for stem in stems:  # remove stale outputs of an earlier run
        for ext in IMAGE_EXTS + (".log",):
            p = os.path.join(args.outdir, stem + ext)
            if os.path.exists(p):
                os.remove(p)
    cmd = [args.renderer, os.path.join(tdir, t["scene"])] + args.extra
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=tdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=args.timeout)
        code, console, hung = proc.returncode, proc.stdout.decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired as e:
        code, console, hung = None, (e.stdout or b"").decode("utf-8", "replace"), True
    except OSError as e:
        code, console, hung = None, "could not start renderer: %s" % e, False
    secs = time.time() - t0
    with open(os.path.join(resdir, "console.txt"), "w") as f:
        f.write(console)
    log_path = find_file(args.outdir, stems, (".log",))
    log_text = open(log_path, errors="replace").read() if log_path else ""
    if log_path:
        shutil.copy(log_path, os.path.join(resdir, "testsuite_my_%d.log" % n))
    crashed = hung or code is None or code < 0 or code >= 128
    status = "timeout" if hung else ("signal %d" % -code if code is not None and code < 0 else "exit %s" % code)
    info = {"test": n, "category": t["category"], "name": t["name"], "seconds": round(secs, 2), "status": status}
    if t.get("group"):
        info["group"] = t["group"]

    if t["category"] == "error":
        text = log_text + "\n" + console
        flagged = [l for l in text.splitlines() if re.search(r"error|warn|invalid|unknown|cannot|missing|fail", l, re.I)]
        hit = [l for l in flagged if any(k.lower() in l.lower() for k in t["keywords"])]
        ok = not crashed and bool(hit)
        detail = "%s, %s; %s" % (status, "log " + os.path.basename(log_path) if log_path else "no log file (console used)",
                                  ("reported: " + hit[0].strip()) if hit else
                                  ("no error/warning mentioning any of %s" % t["keywords"]))
        return ok, detail, info

    if crashed:
        return False, "renderer %s (no image compared)" % status, info
    img_path = find_file(args.outdir, stems, IMAGE_EXTS)
    if not img_path:
        return False, "%s, but no output image %s.{pfm,png,ppm} in %s" % (status, stems[0], args.outdir), info
    shutil.copy(img_path, os.path.join(resdir, os.path.basename(img_path).replace(stems[1], stems[0])))
    ref = load_image(os.path.join(tdir, t["reference"]))
    mine = load_image(img_path, args.ldr_encoding)
    if (mine.w, mine.h) != (ref.w, ref.h):
        return False, "image is %dx%d, reference %dx%d" % (mine.w, mine.h, ref.w, ref.h), info
    exposure = t.get("display_exposure", 1.0)
    display_png(os.path.join(resdir, "testsuite_ref_%d.png" % n), ref, exposure)
    display_png(os.path.join(resdir, "testsuite_my_%d.png" % n), mine, exposure)
    ok, detail, values = METRICS[t["metric"]](t, ref, mine, resdir, n)
    info.update(values)
    return ok, "%s, %s; %s" % (status, os.path.basename(img_path), detail), info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renderer", default=os.path.join(HERE, "..", "output", "CGR26_renderer"))
    ap.add_argument("--outdir", default=None, help="where the renderer writes images and logs (default: its directory)")
    ap.add_argument("--tests", default="", help="comma-separated test numbers (default: all)")
    ap.add_argument("--timeout", type=float, default=900, help="seconds per test")
    ap.add_argument("--ldr-encoding", choices=("srgb", "linear"), default="srgb",
                    help="how to decode 8-bit PNG/PPM outputs (default sRGB); PFM is always linear")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[], help="extra renderer arguments (put last)")
    args = ap.parse_args()
    args.renderer = os.path.abspath(args.renderer)
    args.outdir = os.path.abspath(args.outdir or os.path.dirname(args.renderer))
    numbers = sorted(int(d[4:]) for d in os.listdir(HERE) if re.fullmatch(r"test\d+", d))
    if args.tests:
        want = {int(s) for s in args.tests.split(",") if s.strip()}
        numbers = [n for n in numbers if n in want]

    log_lines = []

    def say(s=""):
        print(s)
        sys.stdout.flush()
        log_lines.append(s)

    say("==== runAllTests ====")
    say("date:     " + time.strftime("%Y-%m-%d %H:%M:%S"))
    say("renderer: " + args.renderer)
    say("outdir:   " + args.outdir)
    if not os.path.exists(args.renderer):
        say("ERROR: renderer not found (build it first, or pass --renderer)")
        return 2
    results = []
    for n in numbers:
        with open(os.path.join(HERE, "test%d" % n, "test.json")) as f:
            t = json.load(f)
        ok, detail, info = run_test(n, t, args, None)
        info["pass"] = ok
        results.append(info)
        say("test%-3d %-6s %-5s %-58s %6.1fs  %s" % (n, t["category"], "PASS" if ok else "FAIL", t["name"][:58],
                                                    info["seconds"], detail))
    say("")
    say("==== summary ====")
    for cat in ("camera", "shading", "error"):
        rs = [r for r in results if r["category"] == cat]
        if not rs:
            continue
        npass = sum(r["pass"] for r in rs)
        extra = ""
        if cat == "camera":
            cov = [r for r in rs if "mismatch_pct" in r]
            cen = [r for r in rs if "max_centroid_err_px" in r]
            if cov:
                extra += "; silhouettes: max wrong-side pixels %.3f%%, max |edge offset| %.3f px, min IoU %.4f" % (
                    max(r["mismatch_pct"] for r in cov), max(abs(r["edge_offset_px"]) for r in cov),
                    min(r["iou"] for r in cov))
            if cen:
                extra += "; framing: max centroid error %.3f px" % max(r["max_centroid_err_px"] for r in cen)
        elif cat == "shading":
            px = [r for r in rs if "max_rel_err_pct" in r]
            if px:
                extra += "; pixel error: max %.2f%%, mean of test means %.2f%%" % (
                    max(r["max_rel_err_pct"] for r in px), sum(r["mean_rel_err_pct"] for r in px) / len(px))
        elif cat == "error":
            groups = []
            for r in rs:
                if r.get("group") and r["group"] not in groups:
                    groups.append(r["group"])
            if groups:
                extra += "; by kind: " + ", ".join("%s %d/%d" % (g, sum(r["pass"] for r in rs if r.get("group") == g),
                                                                 sum(1 for r in rs if r.get("group") == g)) for g in groups)
        say("%-8s %d/%d passed (%.0f%%)%s" % (cat, npass, len(rs), 100.0 * npass / len(rs), extra))
    total = sum(r["pass"] for r in results)
    say("total    %d/%d passed" % (total, len(results)))
    with open(os.path.join(HERE, "runAllTests.log"), "w") as f:
        f.write("\n".join(log_lines) + "\n")
    with open(os.path.join(HERE, "results", "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    return 0 if total == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

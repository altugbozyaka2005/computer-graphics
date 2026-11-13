#!/usr/bin/env python3
"""Annotated figures and tables for the Module 3 report (Python 3 standard library only).

Reads the acceleration study (output/module3/*.csv), the student test suite and its last results
(studentTests/, studentTests/results/) and the test-suite sensitivity check
(output/module3/validation/suite_sensitivity.json, written by validate_module3.py), and writes
output/figures/module3/:

  Acceleration
    acc_timing.png            render time and intersection tests per ray: brute force / per-object boxes / BVH
    acc_split.png             BVH split methods (SAH, middle, equal counts): render time, SAH cost, tests per ray
    acc_bvh_table.png         table: primitives, BVH nodes, depth, SAH cost, build time, tests per ray, speed-ups
  Test suite
    testsuite_<n>.png         every image test: reference | mine | difference, with
                                camera (coverage): an 8x zoom of the busiest edges
                                camera (framing):  each marker enlarged with both centroids
                                shading:           numbered pixels and a table of their values and errors
    testsuite_table.png       all tests by category: what each checks, metric, threshold, measured, result
    testsuite_shading_errors.png  relative error at every labelled pixel against each test's threshold
    testsuite_convergence.png     error against samples per pixel (Monte Carlo noise as a discrepancy source)
    testsuite_tonemap.png     error when the tone-mapped 8-bit PNG is compared instead of the linear PFM
    testsuite_errors.png      error-handling scenes: the deliberate error, CGR26_renderer's log line,
                              pbrt-v4's message, exit status, result
    testsuite_sensitivity.png deliberately broken scenes and fake renderers: does each test fail?
  FIGURES.txt                 what every figure shows

  python3 scenes/tools/make_report_figures_m3.py [--no-convergence]
"""
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures as mf  # noqa: E402
import make_figures_m2 as m2  # noqa: E402
import make_figures_m3 as m3  # noqa: E402

ROOT = m3.ROOT
OUT, M3, FIG, ST = m3.OUT, m3.M3, m3.FIG, m3.ST
rt = m3.rt
INK, INK2, MUTED, GRID, SURFACE = m2.INK, m2.INK2, m2.MUTED, m2.GRID, m2.SURFACE
SERIES = m2.SERIES
GOOD, BAD = (27, 140, 90), (200, 40, 40)
REF_COL, MINE_COL = (0, 200, 230), (235, 40, 40)
INDEX = []


def num(v):
    """Readable number: thousands separators, 3 significant digits for small values."""
    if v >= 100:
        return "{:,.0f}".format(v)
    return "%.3g" % v


def save(img, name, what):
    m3.save(img, name)
    INDEX.append((name, what))


# ================================================================ drawing helpers
def text_block(width, lines, px=15, col=INK2, pad=8, bold=False):
    """Wrapped paragraph(s) as an image."""
    wrapped = []
    for para in lines:
        wrapped += mf.wrap_text(para, px, width - 2 * pad, bold) or [""]
    lh = mf.line_height(px)
    img = mf.new_image(width, 2 * pad + lh * len(wrapped))
    for k, l in enumerate(wrapped):
        mf.draw_text(img, pad, pad + k * lh, l, px, col, bold)
    return img


def titled(img, title, sub=None, px=20):
    """Bold title and a wrapped grey subtitle above an image (never cut off)."""
    parts = [text_block(img[0], [title], px, INK, 6, True)]
    if sub:
        parts.append(text_block(img[0], [sub], px - 4, INK2, 6))
    return m2.vstack(parts + [img], gap=0)


def table(headers, rows, widths, px=14, colors=None, title=None, sub=None, bold_first=False):
    """Table with wrapped cells, a header row and zebra stripes. colors[r][c] = text colour (optional)."""
    pad, lh = 7, mf.line_height(px)
    W = sum(widths)
    cells = []
    for r, row in enumerate([headers] + rows):
        wr = [mf.wrap_text(str(v), px, widths[c] - 2 * pad, r == 0) or [""] for c, v in enumerate(row)]
        cells.append((wr, 2 * pad + lh * max(len(w) for w in wr)))
    H = sum(h for _, h in cells)
    img = mf.new_image(W, H)
    y = 0
    for r, (wr, h) in enumerate(cells):
        bg = (233, 236, 241) if r == 0 else ((247, 247, 245) if r % 2 == 0 else (255, 255, 255))
        mf.fill_rect(img, 0, y, W, y + h, bg)
        x = 0
        for c, lines in enumerate(wr):
            col = INK
            if r > 0 and colors and colors[r - 1] and colors[r - 1][c]:
                col = colors[r - 1][c]
            for k, l in enumerate(lines):
                mf.draw_text(img, x + pad, y + pad + k * lh, l, px, col, r == 0 or (bold_first and c == 0))
            x += widths[c]
        y += h
        mf.draw_line(img, 0, y - 0.5, W, y - 0.5, GRID, 1)
    x = 0
    for wdt in widths[:-1]:
        x += wdt
        mf.draw_line(img, x - 0.5, 0, x - 0.5, H, GRID, 1)
    mf.draw_rect(img, 0.5, 0.5, W - 0.5, H - 0.5, (180, 180, 176), 1)
    if title:
        img = titled(img, title, sub)
    return img


def hbars(groups, names, title, xlabel, log=True, fmt=lambda v: "%g" % v, notes=None, width=1100, ref=None,
          xmax=None):
    """Horizontal grouped bar chart. groups: [(label, [v per series])]; notes: text right of each group;
    ref: (value, label) dashed vertical line."""
    bh, gap, ggap = 18, 3, 16
    lab_w = max(mf.text_width(g[0], 15, True) for g in groups) + 24
    note_w = 320 if notes else 20
    L, R = lab_w, note_w
    T = 12 + 2 * mf.line_height(15) + 10
    gh = len(names) * (bh + gap) - gap
    H = T + len(groups) * (gh + ggap) + 50
    img = mf.new_image(width, H, SURFACE)
    lx = L
    for k, n in enumerate(names):
        mf.fill_rect(img, lx, 14, lx + 14, 28, SERIES[k % 4])
        lx += 22 + mf.draw_text(img, lx + 20, 12, n, 15, INK2) + 18
    pw = width - L - R
    vals = [v for _, vs in groups for v in vs if v and v > 0]
    if log:
        lo = 10 ** math.floor(math.log10(min(vals)))
        hi = 10 ** math.ceil(math.log10(max(vals) * 1.05))
        X = lambda v: L + (math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * pw
        ticks = [10 ** e for e in range(int(round(math.log10(lo))), int(round(math.log10(hi))) + 1)]
    else:
        hi = xmax or max(vals) * 1.15
        X = lambda v: L + v / hi * pw
        ticks = m2.nice_ticks(0, hi)
    y0 = T
    for t in ticks:
        x = X(t)
        if L - 1 <= x <= L + pw + 1:
            mf.draw_line(img, x, T - 4, x, H - 44, GRID, 1)
            s = num(t) if log else m2.fmt_tick(t)
            mf.draw_text(img, x - mf.text_width(s, 13) / 2, H - 40, s, 13, INK2)
    mf.draw_text(img, L + pw / 2 - mf.text_width(xlabel, 15) / 2, H - 22, xlabel, 15, INK2)
    for gi, (glab, vs) in enumerate(groups):
        mf.draw_text(img, 10, y0 + gh / 2 - 10, glab, 15, INK, True)
        for k, v in enumerate(vs):
            y = y0 + k * (bh + gap)
            if v is None:
                continue
            x1 = X(v) if v > 0 else L
            mf.fill_rect(img, L, y, max(L + 1, x1), y + bh, SERIES[k % 4])
            s = fmt(v)
            mf.draw_text(img, x1 + 5, y + 1, s, 13, INK)
        if notes and notes[gi]:
            for k, l in enumerate(notes[gi].split("\n")):
                mf.draw_text(img, width - R + 12, y0 + k * mf.line_height(14), l, 14, INK2)
        y0 += gh + ggap
    mf.draw_line(img, L, T - 4, L, H - 44, INK2, 1.5)
    if ref:
        x = X(ref[0])
        m2.dashed(img, x, T - 4, x, H - 44, BAD, 1.5)
        mf.draw_text(img, x + 4, T - 22, ref[1], 13, BAD)
    return titled(img, title)


def cross(img, cx, cy, r, col, w=2):
    mf.draw_line(img, cx - r, cy, cx + r, cy, col, w)
    mf.draw_line(img, cx, cy - r, cx, cy + r, col, w)


def pfm_display(img_pfm, exposure):
    """Linear image -> 8-bit sRGB image structure for drawing."""
    out = mf.new_image(img_pfm.w, img_pfm.h)
    d = out[2]
    for y in range(img_pfm.h):
        for x in range(img_pfm.w):
            c = img_pfm.rgb(x, y)
            i = 3 * (y * img_pfm.w + x)
            d[i:i + 3] = bytes(rt.to_srgb8(v * exposure) for v in c)
    return out


def err_colorbar(width, label):
    h = 54
    img = mf.new_image(width, h)
    x0, x1 = 20, width - 20
    for x in range(x0, x1):
        mf.fill_rect(img, x, 6, x + 1, 22, m3.cmap((x - x0) / (x1 - x0)))
    mf.draw_rect(img, x0, 6, x1, 22, (0, 0, 0), 1)
    for f, s in ((0, "0"), (0.5, "2.5%"), (1, ">= 5%")):
        x = x0 + f * (x1 - x0)
        mf.draw_text(img, x - mf.text_width(s, 13) / 2, 24, s, 13, INK2)
    mf.draw_text(img, width / 2 - mf.text_width(label, 13) / 2, 38, label, 13, INK2)
    return img


# ================================================================ acceleration
def acc_figures():
    rows = m3.read_csv("acc_main.csv")
    if not rows:
        print("skip acceleration figures (output/module3/acc_main.csv missing)")
        return
    short = {"best": "acc_best", "worst": "acc_worst", "complex": "acc_complex"}
    name = lambda r: short[r["scene"]] if r["scene"] in short else r["scene"].split(" (")[1].rstrip(")").replace(
        "Module 1 ", "")
    groups = [(name(r) + "  " +
               "{:,}".format(int(r["primitives"])) + " prims",
               [float(r["none_s"]), float(r["objects_s"]), float(r["bvh_s"])]) for r in rows]
    notes = ["BVH x%s vs brute force\nx%s vs per-object boxes\nBVH build %.3f s" % (
        num(float(r["speedup_vs_none"])), num(float(r["speedup_vs_objects"])), float(r["bvh_build_s"]))
        for r in rows]
    t1 = hbars(groups, ["brute force (every ray vs every primitive)", "per-object boxes (Module 1/2 checkpoint)",
                        "BVH (SAH)"], "Render time by acceleration structure (1 spp, timing resolution; log scale)",
               "render time (s), log scale", fmt=lambda v: num(v) + " s", notes=notes)
    groups2 = [(g[0], [float(r["prim_tests_per_ray_none"]), float(r["prim_tests_per_ray_objects"]),
                       float(r["prim_tests_per_ray_bvh"]) + float(r["box_tests_per_ray_bvh"])])
               for g, r in zip(groups, rows)]
    notes2 = ["BVH: %s primitive\n+ %s box tests per ray" % (r["prim_tests_per_ray_bvh"], r["box_tests_per_ray_bvh"])
              for r in rows]
    t2 = hbars(groups2, ["brute force", "per-object boxes (primitive tests)", "BVH (box + primitive tests)"],
               "Intersection tests per ray (log scale)", "tests per ray, log scale", fmt=num,
               notes=notes2)
    save(m2.vstack([t1, t2], gap=24), "acc_timing.png",
         "Render time and intersection tests per ray for the three acceleration scenes and two Module 1 scenes, "
         "brute force vs per-object boxes vs BVH, with speed-ups (from acc_main.csv).")

    sp = m3.read_csv("acc_split.csv")
    if sp:
        scenes = []
        for r in sp:
            if r["scene"] not in scenes:
                scenes.append(r["scene"])
        meths = ["sah", "middle", "equal"]
        get = lambda s, m, k: float([r for r in sp if r["scene"] == s and r["splitmethod"] == m][0][k])
        g1 = [(s, [get(s, m, "render_s") / get(s, "sah", "render_s") for m in meths]) for s in scenes]
        n1 = ["SAH cost: %s / %s / %s\nbox tests/ray: %s / %s / %s" % (
            tuple(m2.fnum(get(s, m, "sah_cost")) for m in meths) + tuple(m2.fnum(get(s, m, "box_tests_per_ray")) for m in meths))
            for s in scenes]
        img = hbars(g1, ["SAH (12 buckets)", "middle (centroid midpoint)", "equal counts (median)"],
                    "BVH split method: render time relative to SAH (lower is better)", "render time / SAH render time",
                    log=False, fmt=lambda v: "%.2f" % v, notes=n1, ref=(1.0, "SAH"), xmax=1.8)
        tab = table(["scene", "split", "build (s)", "nodes", "depth", "SAH cost", "render (s)", "prim tests/ray",
                     "box tests/ray"],
                    [[r["scene"], r["splitmethod"], r["build_s"], "{:,}".format(int(r["nodes"])), r["depth"], r["sah_cost"],
                      r["render_s"], r["prim_tests_per_ray"], r["box_tests_per_ray"]] for r in sp],
                    [130, 90, 90, 100, 70, 90, 100, 120, 120],
                    colors=[[None, GOOD if r["splitmethod"] == "sah" else None] + [None] * 7 for r in sp])
        save(m2.vstack([img, tab], gap=20), "acc_split.png",
             "BVH split methods compared on the three acceleration scenes: render time relative to SAH, SAH cost, "
             "tests per ray, and the full numbers (from acc_split.csv).")

    tab = table(["scene", "resolution", "primitives", "objects", "BVH nodes", "depth", "SAH cost", "build (s)",
                 "brute force (s)", "boxes (s)", "BVH (s)", "speed-up vs brute / boxes", "BVH tests per ray (prim + box)"],
                [[{"best": "acc_best", "worst": "acc_worst", "complex": "acc_complex"}.get(r["scene"],
                  r["scene"].replace("(Module 1 ", "(M1 ")), r["resolution"], "{:,}".format(int(r["primitives"])),
                  "{:,}".format(int(r["objects"])), "{:,}".format(int(r["bvh_nodes"])), r["bvh_depth"], r["bvh_sah_cost"],
                  r["bvh_build_s"], r["none_s"], r["objects_s"], r["bvh_s"],
                  "x%s / x%s" % (num(float(r["speedup_vs_none"])), num(float(r["speedup_vs_objects"]))),
                  "%s + %s" % (r["prim_tests_per_ray_bvh"], r["box_tests_per_ray_bvh"])] for r in rows],
                [190, 90, 90, 75, 85, 55, 70, 70, 95, 80, 70, 120, 130], px=13,
                title="Acceleration summary (1 spp; times in seconds)",
                sub="brute force = every ray against every primitive; boxes = the Module 1/2 per-object bounding boxes; "
                    "BVH = SAH-built bounding volume hierarchy. The BVH images are byte-identical to brute force.")
    save(tab, "acc_bvh_table.png", "Table of the acceleration study: scene sizes, BVH statistics, times and speed-ups.")


# ================================================================ test suite
def tests():
    out = []
    for d in os.listdir(ST):
        if d.startswith("test") and d[4:].isdigit():
            n = int(d[4:])
            out.append((n, json.load(open(os.path.join(ST, d, "test.json")))))
    return sorted(out, key=lambda t: t[0])


def results():
    p = os.path.join(ST, "results", "results.json")
    return {r["test"]: r for r in json.load(open(p))} if os.path.exists(p) else {}


def log_lines():
    p = os.path.join(ST, "runAllTests.log")
    out = {}
    if os.path.exists(p):
        for l in open(p):
            m = re.match(r"test(\d+)\s", l)
            if m:
                out[int(m.group(1))] = l.rstrip("\n")
    return out


def my_pfm(n):
    p = os.path.join(ST, "results", "test%d" % n, "testsuite_my_%d.pfm" % n)
    return rt.read_pfm(p) if os.path.exists(p) else None


def busiest_window(ref, lr, ww, wh):
    """The ww x wh window with the most partly covered pixels (edges) in the reference."""
    part = [[1 if 0.05 < min(1.0, ref.lum(x, y) / lr) < 0.95 else 0 for x in range(ref.w)] for y in range(ref.h)]
    best, bx, by = -1, 0, 0
    for y in range(0, ref.h - wh + 1, 4):
        for x in range(0, ref.w - ww + 1, 4):
            s = sum(sum(part[yy][x:x + ww]) for yy in range(y, y + wh))
            if s > best:
                best, bx, by = s, x, y
    return bx, by


def pixel_rows(t, ref, mine):
    w = t.get("window", 1)
    mean_lum = sum(ref.lum(x, y) for y in range(ref.h) for x in range(ref.w)) / (ref.w * ref.h)
    floor = max(t.get("floor", 0.05) * mean_lum, 1e-6)
    out = []
    for p in t["pixels"]:
        r = rt.window_mean(ref, p["x"], p["y"], w)
        m = rt.window_mean(mine, p["x"], p["y"], w)
        lumr = 0.2126 * r[0] + 0.7152 * r[1] + 0.0722 * r[2]
        d = [abs(m[k] - r[k]) for k in range(3)]
        out.append((p, r, m, d, max(d) / max(lumr, floor)))
    return out


def testsuite_figures():
    res = results()
    for n, t in tests():
        if t["category"] == "error":
            continue
        d = os.path.join(ST, "test%d" % n)
        ref = rt.read_pfm(os.path.join(d, t["reference"]))
        mine = my_pfm(n)
        if mine is None:
            print("skip test %d (run studentTests/runAllTests.py first)" % n)
            continue
        exp = t.get("display_exposure", 1.0)
        scale = 2 if ref.w <= 320 else max(1, int(round(420 / ref.w)))
        if ref.w * scale > 680:
            scale = max(1, scale - 1)
        a, b = pfm_display(ref, exp), pfm_display(mine, exp)
        big = [mf.crop_scaled(i, 0, 0, i[0], i[1], scale) for i in (a, b)]
        src = "analytic closed form" if "pbrt_scene" not in t else "pbrt-v4"
        extra = []
        if t["metric"] == "coverage":
            diff = mf.load_png(os.path.join(ST, "results", "test%d" % n, "diff_%d.png" % n))
            third = mf.crop_scaled(diff, 0, 0, diff[0], diff[1], scale)
            sub3 = "coverage: grey both, red mine only, cyan reference only"
            lr = rt.object_level(ref)
            ww, wh = 40, 26
            bx, by = busiest_window(ref, lr, ww, wh)
            for im in big + [third]:
                m2.frame(im, (bx * scale, by * scale, (bx + ww) * scale, (by + wh) * scale))
            z = 9
            lm = rt.object_level(mine)
            amp = mf.new_image(ref.w, ref.h)
            for y in range(ref.h):
                for x in range(ref.w):
                    dv = abs(min(1.0, mine.lum(x, y) / lm) - min(1.0, ref.lum(x, y) / lr))
                    amp[2][3 * (y * ref.w + x):3 * (y * ref.w + x) + 3] = bytes(m3.cmap(10 * dv))
            zooms = [m2.captioned(mf.crop_scaled(im, bx, by, bx + ww, by + wh, z), cap, sub, px=16) for im, cap, sub in
                     ((a, "reference, 9x", None), (b, "mine, 9x", None), (diff, "difference, 9x", "grey both, red mine, cyan ref"),
                      (amp, "|coverage difference| x10", "yellow = 10% of a pixel or more"))]
            r = res.get(n, {})
            extra.append(titled(m2.hstack(zooms, gap=10), "Zoom on the busiest edges (yellow box): each square is one pixel",
                                "wrong-side pixels %.3f%%, mean edge offset %+.3f px, coverage IoU %.4f" % (
                                    r.get("mismatch_pct", 0), r.get("edge_offset_px", 0), r.get("iou", 0)), px=17))
        elif t["metric"] == "centroids":
            em = mf.new_image(ref.w, ref.h)
            for y in range(ref.h):
                for x in range(ref.w):
                    v = max(abs(p - q) for p, q in zip(ref.rgb(x, y), mine.rgb(x, y))) / 0.05
                    em[2][3 * (y * ref.w + x):3 * (y * ref.w + x) + 3] = bytes(m3.cmap(v))
            third = mf.crop_scaled(em, 0, 0, em[0], em[1], scale)
            sub3 = "|mine - ref|, full scale = 0.05"
            lr, lm = rt.object_level(ref), rt.object_level(mine)
            rad = t["radius"]
            z = max(6, int(120 / (2 * rad + 1)))
            tiles = []
            for mk in t["markers"]:
                rx, ry = rt.blob_centroid(ref, mk["x"], mk["y"], rad, lr)
                mx, my = rt.blob_centroid(mine, mk["x"], mk["y"], rad, lm)
                x0, y0 = int(mk["x"]) - rad, int(mk["y"]) - rad
                tile = mf.crop_scaled(b, x0, y0, x0 + 2 * rad + 1, y0 + 2 * rad + 1, z)
                cross(tile, (rx - x0) * z, (ry - y0) * z, 0.4 * tile[0], REF_COL, 3)
                cross(tile, (mx - x0) * z, (my - y0) * z, 0.25 * tile[0], MINE_COL, 2)
                tiles.append(m2.captioned(tile, mk["label"], "err %.3f px" % math.hypot(mx - rx, my - ry), px=14))
            rows_ = [m2.hstack(tiles[i:i + 9], gap=8) for i in range(0, len(tiles), 9)]
            extra.append(titled(m2.vstack(rows_), "Markers enlarged %dx: cyan cross = reference centroid, red = mine" % z,
                                "markers at 5/50/95%% of the width and 6/50/94%% of the height; max centroid error "
                                "%.3f px (threshold %.2f px)" % (res.get(n, {}).get("max_centroid_err_px", 0),
                                                                 t["max_centroid_error"]), px=17))
            for im in big:
                for mk in t["markers"]:
                    m2.frame(im, ((mk["x"] - rad) * scale, (mk["y"] - rad) * scale, (mk["x"] + rad) * scale,
                                  (mk["y"] + rad) * scale), m2.YELLOW, 2)
        else:  # pixels
            em = mf.new_image(ref.w, ref.h)
            lums = sorted(ref.lum(x, y) for y in range(ref.h) for x in range(ref.w))
            s99 = lums[int(0.99 * (len(lums) - 1))] or 1
            for y in range(ref.h):
                for x in range(ref.w):
                    v = max(abs(p - q) for p, q in zip(ref.rgb(x, y), mine.rgb(x, y))) / (0.05 * s99)
                    em[2][3 * (y * ref.w + x):3 * (y * ref.w + x) + 3] = bytes(m3.cmap(v))
            third = mf.crop_scaled(em, 0, 0, em[0], em[1], scale)
            sub3 = "|mine - ref| per pixel (noise and edges)"
            for im in big:
                m3.marker_overlay(im, scale, t["pixels"])
            rows_, cols = [], []
            for k, (p, r, m, dd, rel) in enumerate(pixel_rows(t, ref, mine), 1):
                ok = rel <= t["max_rel_error"]
                rows_.append([str(k), p["label"], "(%d, %d)" % (p["x"], p["y"]), "%.4f %.4f %.4f" % tuple(r),
                              "%.4f %.4f %.4f" % tuple(m), "%.4f %.4f %.4f" % tuple(dd), "%.2f%%" % (100 * rel)])
                cols.append([None] * 6 + [GOOD if ok else BAD])
            w = t.get("window", 1)
            extra.append(table(["#", "pixel", "(x, y)", "reference r g b", "mine r g b", "|difference| r g b",
                                "rel. error"], rows_, [40, 330, 90, 190, 190, 190, 90], px=14, colors=cols,
                               title="Labelled pixels (%s; threshold %.0f%%)" % (
                                   "single pixels" if w == 0 else "mean over %dx%d pixels" % (2 * w + 1, 2 * w + 1),
                                   100 * t["max_rel_error"]),
                               sub="rel. error = max over r,g,b of |mine - ref| / max(luminance of ref, 5% of the "
                                   "reference's mean luminance). Linear radiance from the PFM outputs."))
        row = m2.hstack([m2.captioned(big[0], "testsuite_ref_%d (%s)" % (n, src)),
                         m2.captioned(big[1], "testsuite_my_%d (CGR26_renderer)" % n),
                         m2.captioned(third, "difference", sub3)])
        if t["metric"] == "pixels":
            row = m2.vstack([row, m2.hstack([mf.new_image(big[0][0] * 2 + 32, 10),
                                             err_colorbar(third[0], "|mine - ref| / 99th percentile of ref")])], gap=0)
        r = res.get(n, {})
        verdict = "PASS" if r.get("pass") else "FAIL"
        fig = titled(row, "Test %d (%s): %s  [%s]" % (n, t["category"], t["name"], verdict), t["description"])
        fig = m2.vstack([fig] + [m2.hstack([e]) for e in extra], gap=14)
        save(fig, "testsuite_%d.png" % n, "Test %d (%s): reference, mine and difference%s." % (
            n, t["name"], {"coverage": ", plus an 8-9x zoom on the busiest edges",
                           "centroids": ", plus each marker enlarged with both centroids",
                           "pixels": ", with the labelled pixels and a table of their values and errors"}[t["metric"]]))


def threshold_text(t):
    if t["metric"] == "coverage":
        s = "wrong-side <= %.2f%%, |offset| <= %.2f px" % (100 * t["max_mismatch"], t["max_offset"])
        if "max_edge_abs_diff" in t:
            s += ", edge |diff| <= %.2f" % t["max_edge_abs_diff"]
        return s
    if t["metric"] == "centroids":
        return "centroid error <= %.2f px" % t["max_centroid_error"]
    if t["metric"] == "pixels":
        return "rel. error <= %.0f%%" % (100 * t["max_rel_error"])
    return "no crash/hang; log mentions one of: " + ", ".join(t["keywords"])


def measured_text(r):
    if "mismatch_pct" in r:
        return "wrong-side %.3f%%, offset %+.3f px, IoU %.4f" % (r["mismatch_pct"], r["edge_offset_px"], r["iou"])
    if "max_centroid_err_px" in r:
        return "max %.3f px, mean %.3f px" % (r["max_centroid_err_px"], r["mean_centroid_err_px"])
    if "max_rel_err_pct" in r:
        return "max %.2f%%, mean %.2f%% (image RMSE %.2f%%)" % (r["max_rel_err_pct"], r["mean_rel_err_pct"],
                                                               r["image_rel_rmse_pct"])
    return r.get("status", "")


def suite_table():
    res = results()
    T = tests()
    blocks = []
    for cat, title in (("camera", "Camera and intersections (compared with pbrt-v4)"),
                       ("shading", "Shading: Phong BRDF (compared with pbrt-v4; test 9 with the closed form)"),
                       ("error", "Error handling (one deliberate error per scene)")):
        rows_, cols = [], []
        for n, t in T:
            if t["category"] != cat:
                continue
            r = res.get(n, {})
            ok = r.get("pass")
            if cat == "error":
                rows_.append([str(n), t.get("group", ""), t["name"], threshold_text(t), r.get("status", ""),
                              "PASS" if ok else "FAIL"])
            else:
                rows_.append([str(n), t["name"], t["metric"], threshold_text(t), measured_text(r), "PASS" if ok else "FAIL"])
            cols.append([None] * 5 + [GOOD if ok else BAD])
        if not rows_:
            continue
        npass = sum(1 for r in rows_ if r[-1] == "PASS")
        hdr = (["#", "group", "deliberate error", "pass criterion", "renderer", "result"] if cat == "error" else
               ["#", "scene: what it checks", "metric", "pass criterion", "measured", "result"])
        wd = [40, 110, 380, 420, 90, 70] if cat == "error" else [40, 420, 90, 260, 300, 70]
        blocks.append(table(hdr, rows_, wd, px=13, colors=cols, title="%s: %d/%d passed (%.0f%%)" % (
            title, npass, len(rows_), 100.0 * npass / len(rows_))))
    save(m2.vstack(blocks, gap=22), "testsuite_table.png",
         "All tests by category with pass criteria, measured errors and results (the tabulation asked for in 2.3.2).")


def shading_error_chart():
    T = [(n, t) for n, t in tests() if t["metric"] == "pixels"]
    panels = []
    for n, t in T:
        ref = rt.read_pfm(os.path.join(ST, "test%d" % n, t["reference"]))
        mine = my_pfm(n)
        if mine is None:
            continue
        pr = pixel_rows(t, ref, mine)
        groups = [("%d %s" % (k, p["label"]), [100 * rel]) for k, (p, r, m, d, rel) in enumerate(pr, 1)]
        panels.append(hbars(groups, ["relative error at the pixel (%)"], "Test %d: %s" % (n, t["name"]),
                            "relative error (%)", log=False, fmt=lambda v: "%.2f%%" % v,
                            ref=(100 * t["max_rel_error"], "threshold %.0f%%" % (100 * t["max_rel_error"])),
                            xmax=100 * t["max_rel_error"] * 1.25, width=1000))
    if panels:
        save(m2.vstack(panels, gap=18), "testsuite_shading_errors.png",
             "Relative error at every labelled pixel of the shading tests, against each test's threshold.")


def convergence(skip):
    """Error at the labelled pixels against samples per pixel (renders the shading tests at several spp)."""
    R = os.path.join(OUT, "CGR26_renderer")
    cdir = os.path.join(M3, "convergence")
    csvp = os.path.join(M3, "testsuite_convergence.csv")
    T = [(n, t) for n, t in tests() if t["metric"] == "pixels" and "pbrt_scene" in t]
    if not skip and os.path.exists(R):
        os.makedirs(cdir, exist_ok=True)
        rows_ = []
        for n, t in T:
            ref = rt.read_pfm(os.path.join(ST, "test%d" % n, t["reference"]))
            for spp in (1, 4, 16, 64, 256, 1024):
                stem = "test%d_spp%d" % (n, spp)
                subprocess.run([R, os.path.join(ST, "test%d" % n, t["scene"]), "--quiet", "--spp", str(spp),
                                "--outdir", cdir, "--out", stem], cwd=os.path.join(ST, "test%d" % n),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p = os.path.join(cdir, stem + ".pfm")
                if not os.path.exists(p):
                    continue
                rels = [rel for *_, rel in pixel_rows(t, ref, rt.read_pfm(p))]
                rows_.append([n, spp, "%.4f" % (100 * max(rels)), "%.4f" % (100 * sum(rels) / len(rels))])
                print("convergence test %d spp %d: max %.2f%% mean %.2f%%" % (n, spp, 100 * max(rels), 100 * sum(rels) / len(rels)))
        with open(csvp, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["test", "spp", "max_rel_err_pct", "mean_rel_err_pct"])
            wr.writerows(rows_)
    if not os.path.exists(csvp):
        return
    data = list(csv.DictReader(open(csvp)))
    series, guides = [], []
    for n, t in T:
        rs = [r for r in data if int(r["test"]) == n]
        if not rs:
            continue
        pts_ = [(int(r["spp"]), float(r["mean_rel_err_pct"])) for r in rs]
        series.append(("test %d mean" % n, pts_))
    if series:
        a = series[0][1][0]
        guides.append(("1/sqrt(spp)", [(a[0], a[1]), (1024, a[1] / math.sqrt(1024 / a[0]))]))
    img = m2.plot(series, "Shading tests: mean relative error at the labelled pixels against samples per pixel",
                  "camera samples per pixel (--spp; lightsamples as in the scene)", "mean relative error (%)",
                  xlog=True, ylog=True, guides=guides, hline=(3.0, "3% threshold"), size=(1000, 560))
    note = text_block(img[0], [
        "Tests 6-8 rendered by CGR26_renderer with --spp 1, 4, 16, 64, 256, 1024 (lightsamples as in each scene) "
        "and compared with the same pbrt-v4 reference (64x64 or 128x128 spp). Dashed: slope 1/sqrt(spp). "
        "The scenes themselves use 64 (test 6), 256 (test 7) and 1024 (test 8) spp. Test 9 (analytic "
        "reference) is not included."], 15)
    save(m2.vstack([img, note], gap=0), "testsuite_convergence.png",
         "Shading error against samples per pixel (Monte Carlo noise as a source of discrepancy), from "
         "output/module3/testsuite_convergence.csv.")


def tonemap_figure():
    T = [(n, t) for n, t in tests() if t["metric"] == "pixels"]
    groups, names = [], ["linear PFM (what the runner compares)", "tone-mapped 8-bit PNG (Reinhard + sRGB)"]
    for n, t in T:
        ref = rt.read_pfm(os.path.join(ST, "test%d" % n, t["reference"]))
        mine = my_pfm(n)
        png = os.path.join(ST, "results", "test%d" % n, "testsuite_my_%d.png" % n)
        raw_png = os.path.join(OUT, "testsuite_my_%d.png" % n)
        if mine is None or not os.path.exists(raw_png):
            continue
        ldr = rt.load_image(raw_png)
        e1 = max(rel for *_, rel in pixel_rows(t, ref, mine))
        e2 = max(rel for *_, rel in pixel_rows(t, ref, ldr))
        groups.append(("test %d" % n, [100 * e1, 100 * e2]))
    if not groups:
        return
    chart = hbars(groups, names, "Largest pixel error: linear output vs the tone-mapped display image",
                  "max relative error at the labelled pixels (%), log scale", log=True, fmt=lambda v: num(v) + "%",
                  ref=(3.0, "3% threshold"))
    n, t = T[0]
    ref = rt.read_pfm(os.path.join(ST, "test%d" % n, t["reference"]))
    exp = t.get("display_exposure", 1.0)
    a = pfm_display(ref, exp)
    b = pfm_display(my_pfm(n), exp)
    c = mf.load_png(os.path.join(OUT, "testsuite_my_%d.png" % n))
    W = 360
    tiles = [m2.captioned(mf.resize_box(i, W, int(W * i[1] / i[0])), cap, sub, px=15) for i, cap, sub in (
        (a, "reference (pbrt-v4), linear", "same display mapping"), (b, "mine, linear PFM", "same display mapping"),
        (c, "mine, PNG as written", "Reinhard tone mapping + sRGB, 8 bit"))]
    note = text_block(chart[0], [
        "Same renders, same labelled pixels and same metric; blue: the linear PFM; orange: the PNG the renderer "
        "writes for display (Reinhard tone mapping on luminance, sRGB encoding, 8 bits), decoded from sRGB to "
        "linear before comparing."], 15)
    save(m2.vstack([chart, titled(m2.hstack(tiles), "Test %d displayed three ways" % n), note], gap=14),
         "testsuite_tonemap.png", "Tone mapping as a source of discrepancy: error when the tone-mapped PNG "
                                  "is compared instead of the linear PFM, with the three images side by side.")


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def pbrt_message(n):
    p = os.path.join(ST, "test%d" % n, "testsuite_ref_%d.log" % n)
    if not os.path.exists(p):
        return ""
    for l in open(p, errors="replace"):
        l = ANSI.sub("", l).strip()
        if ("Error" in l or "Warning" in l) and "Output filename" not in l:
            return re.sub(r"^\S*?(testscene_\d+_pbrt\.pbrt)", r"\1", l)
    return "(no message: pbrt-v4 renders without comment)"


def errors_figure():
    lines = log_lines()
    rows_, cols = [], []
    for n, t in tests():
        if t["category"] != "error":
            continue
        bad = [l for l in t.get("error_lines", []) if l != 'Shape "sphere" "float radius" [ 0.3 ]']
        if len(bad) > 1:
            bad = [l for l in bad if l not in ("AttributeBegin", "AttributeEnd")] or bad
        mine = lines.get(n, "")
        m = re.search(r"reported: (.*)$", mine)
        msg = m.group(1) if m else mine
        msg = re.sub(r"^\[(ERROR|WARNING)\] \S*?(testscene_\d+\.pbrt)", r"[\1] \2", msg).replace(ROOT + "/", "")
        status = re.search(r"(exit \d+|signal \d+|timeout)", mine)
        ok = " PASS " in mine
        rows_.append([str(n), t.get("group", ""), t["name"], " / ".join(b.strip() for b in bad[:2]), msg,
                      pbrt_message(n), (status.group(1) if status else "") + ("\nPASS" if ok else "\nFAIL")])
        cols.append([None] * 6 + [GOOD if ok else BAD])
    if not rows_:
        return
    img = table(["#", "group", "error", "line in the scene", "CGR26_renderer log (testsuite_my_N.log)",
                 "pbrt-v4 (testsuite_ref_N.log)", "exit, result"], rows_, [36, 85, 200, 230, 460, 330, 80], px=12,
                colors=cols, title="Error handling: every deliberate error is detected, located and described",
                sub="Each scene is a complete still life with one error. Passing requires no crash (signal or exit "
                    ">= 128) and no hang, and an error/warning line naming the problem. 'file:line:column' locates "
                    "the error; the action taken (ignored, default used, parsing aborted) is stated.")
    npass = sum(1 for c in cols if c[-1] == GOOD)
    groups = {}
    for r in rows_:
        g = groups.setdefault(r[1], [0, 0])
        g[1] += 1
        g[0] += r[-1].endswith("PASS")
    summ = table(["group"] + list(groups) + ["total"],
                 [["passed"] + ["%d/%d" % tuple(v) for v in groups.values()] + ["%d/%d (%.0f%%)" % (
                     npass, len(rows_), 100.0 * npass / len(rows_))]],
                 [90] + [110] * len(groups) + [150], px=14)
    save(m2.vstack([img, summ], gap=14), "testsuite_errors.png",
         "Error-handling scenes: the deliberate error, CGR26_renderer's log line, pbrt-v4's message for the same "
         "scene, exit status and result, with the success rate per group.")


def sensitivity_figure():
    p = os.path.join(M3, "validation", "suite_sensitivity.json")
    if not os.path.exists(p):
        print("skip testsuite_sensitivity.png (run scenes/tools/validate_module3.py)")
        return
    s = json.load(open(p))
    names = {n: t["name"] for n, t in tests()}
    rows_, cols = [], []
    for m in s["mutations"]:
        det = re.sub(r"^.*?;\s*", "", m.get("detail", ""))
        det = re.sub(r", mean \|coverage diff\|.*$", "", det.split("; ")[0])
        det = det.replace("max inf px, mean inf px", "marker lost (moved out of its search window)")
        rows_.append([str(m["test"]), names.get(m["test"], ""), m["mutation"],
                      "FAIL (caught)" if m["caught"] else "PASS (not caught)", det])
        cols.append([None] * 3 + [GOOD if m["caught"] else BAD, None])
    rows_.append(["10-%d" % (9 + s["error_tests"]), "error tests", "fake renderer that crashes (SIGSEGV)",
                  "%d of %d passed" % (s["crashing_passed"], s["error_tests"]), "a crash must fail every error test"])
    rows_.append(["10-%d" % (9 + s["error_tests"]), "error tests", "fake renderer that exits 0 and logs nothing",
                  "%d of %d passed" % (s["silent_passed"], s["error_tests"]), "silence must fail every error test"])
    cols += [[None] * 3 + [GOOD if s["crashing_passed"] == 0 else BAD, None],
             [None] * 3 + [GOOD if s["silent_passed"] == 0 else BAD, None]]
    img = table(["test", "scene", "deliberate change", "outcome", "what the runner measured"], rows_,
                [60, 400, 300, 130, 500], px=13, colors=cols,
                title="Sensitivity of the test suite: small deliberate changes must make the test fail",
                sub="Each scene is copied and changed slightly (a 1% fov change, a light 5% brighter, one bounce "
                    "fewer, ...) and the test is run again with CGR26_renderer; the unchanged scenes all pass "
                    "(scenes/tools/validate_module3.py).")
    save(img, "testsuite_sensitivity.png",
         "Deliberately broken scenes and fake renderers: every change is caught, so a pass is meaningful.")


def write_index():
    with open(os.path.join(FIG, "FIGURES.txt"), "w") as f:
        f.write("Module 3 report figures (scenes/tools/make_figures_m3.py, make_report_figures_m3.py)\n\n")
        for name, what in INDEX:
            f.write("%-32s %s\n" % (name, what))
        for name, what in (("acc_overview.png", "Final acceleration renders with BVH and per-object-box cost maps."),
                           ("acc_scaling_time.png", "Render time against primitive count, brute force vs BVH (log-log)."),
                           ("acc_scaling_tests.png", "Intersection tests per ray against primitive count (log-log)."),
                           ("acc_leaf.png", "Render time against BVH leaf size (maxnodeprims)."),
                           ("testsuite_overview.png", "All image tests, reference above mine.")):
            if os.path.exists(os.path.join(FIG, name)):
                f.write("%-32s %s\n" % (name, what))
    print("wrote output/figures/module3/FIGURES.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-convergence", action="store_true", help="reuse output/module3/testsuite_convergence.csv")
    args = ap.parse_args()
    os.makedirs(FIG, exist_ok=True)
    acc_figures()
    testsuite_figures()
    suite_table()
    shading_error_chart()
    convergence(args.no_convergence)
    tonemap_figure()
    errors_figure()
    sensitivity_figure()
    write_index()


if __name__ == "__main__":
    main()

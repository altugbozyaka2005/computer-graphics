#!/usr/bin/env python3
"""Figures for Module 3 (Python 3 standard library only).

Reads output/acc_*.png, the cost maps and CSVs of module3_study.py (output/module3/) and the test-suite
results of studentTests/runAllTests.py (studentTests/results/), and writes output/figures/module3/:

  acc_overview.png          acc_best / acc_worst / acc_complex beside their BVH cost maps (tests per
                            camera ray, log colour scale) and, for acc_complex, the per-object boxes
  acc_scaling_time.png      render time against primitive count, brute force vs BVH (log-log)
  acc_scaling_tests.png     intersection tests per ray against primitive count (log-log)
  acc_leaf.png              render time and tests per ray against maxnodeprims
  testsuite_<n>.png         every image test: reference | mine | difference, compared pixels numbered
  testsuite_overview.png    all image tests, reference above mine
and copies the reference images to output/testsuite_ref_<n>.png (the renderer writes testsuite_my_<n>).

  python3 scenes/tools/make_figures_m3.py
"""
import csv
import json
import math
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures as mf  # noqa: E402
import make_figures_m2 as m2  # noqa: E402  (plot, hstack, vstack, captioned, frame)

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "output")
M3 = os.path.join(OUT, "module3")
FIG = os.path.join(OUT, "figures", "module3")
ST = os.path.join(ROOT, "studentTests")
sys.path.insert(0, ST)
import runAllTests as rt  # noqa: E402

YELLOW = (255, 214, 0)
# Sequential colour map (dark blue -> teal -> yellow), perceptually ordered.
CMAP = [(13, 8, 135), (84, 2, 163), (139, 10, 165), (185, 50, 137), (219, 92, 104), (244, 136, 73),
        (254, 188, 43), (240, 249, 33)]


def save(img, name):
    os.makedirs(FIG, exist_ok=True)
    mf.save_png(os.path.join(FIG, name), img)
    print("wrote output/figures/module3/%s" % name)


def cmap(t):
    t = max(0.0, min(1.0, t)) * (len(CMAP) - 1)
    i = min(int(t), len(CMAP) - 2)
    f = t - i
    return tuple(int(CMAP[i][k] * (1 - f) + CMAP[i + 1][k] * f) for k in range(3))


def costmap_image(path, lo, hi, width):
    """Tests per camera ray (box + primitive) on a log scale [lo, hi], resized to `width`."""
    c = rt.read_pfm(path)
    img = mf.new_image(c.w, c.h)
    d = img[2]
    vals = []
    for y in range(c.h):
        for x in range(c.w):
            r, g, _ = c.rgb(x, y)
            v = r + g
            vals.append(v)
            col = cmap((math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))
            i = 3 * (y * c.w + x)
            d[i:i + 3] = bytes(col)
    mean = sum(vals) / len(vals)
    return mf.resize_box(img, width, int(round(width * c.h / c.w))), mean, max(vals)


def colorbar(width, lo, hi, label):
    h = 64
    img = mf.new_image(width, h)
    x0, x1 = 20, width - 20
    for x in range(x0, x1):
        col = cmap((x - x0) / (x1 - x0))
        mf.fill_rect(img, x, 8, x + 1, 26, col)
    mf.draw_rect(img, x0, 8, x1, 26, (0, 0, 0), 1)
    e0, e1 = int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi)))
    for e in range(e0, e1 + 1):
        v = 10 ** e
        if lo <= v <= hi:
            x = x0 + (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (x1 - x0)
            mf.draw_line(img, x, 26, x, 32, (0, 0, 0), 1)
            s = "%g" % v
            mf.draw_text(img, x - mf.text_width(s, 14) / 2, 33, s, 14, (60, 60, 60))
    mf.draw_text(img, width / 2 - mf.text_width(label, 14) / 2, 47, label, 14, (60, 60, 60))
    return img


def acc_overview():
    lo, hi = 1.0, 1e4
    rows = []
    W = 520
    for scene in ("acc_best", "acc_worst", "acc_complex"):
        png = os.path.join(OUT, scene + ".png")
        title = scene
        try:  # "scene: N primitives (...), ..., M objects" from the renderer's log
            m = re.search(r"scene: (\d+) primitives.*?(\d+) area lights, (\d+) objects", open(os.path.join(OUT, scene + ".log")).read())
            title = "%s: %s primitives, %s objects" % (scene, "{:,}".format(int(m.group(1))), "{:,}".format(int(m.group(3))))
            if int(m.group(2)):
                title += ", %s area lights" % m.group(2)
        except (OSError, AttributeError):
            pass
        cpath = os.path.join(M3, "acc", "%s_costmap_bvh_cost.pfm" % scene)
        if not (os.path.exists(png) and os.path.exists(cpath)):
            print("skip %s (not rendered)" % scene)
            continue
        img = mf.load_png(png)
        img = mf.resize_box(img, W, int(round(W * img[1] / img[0])))
        cm, mean, mx = costmap_image(cpath, lo, hi, W)
        tiles = [m2.captioned(img, title), m2.captioned(cm, "BVH cost per camera ray",
                                                        "mean %.0f tests (box + primitive), max %.0f" % (mean, mx))]
        opath = os.path.join(M3, "acc", "%s_costmap_objects_cost.pfm" % scene)
        if os.path.exists(opath):
            co, mo, mxo = costmap_image(opath, lo, hi, W)
            tiles.append(m2.captioned(co, "Per-object boxes (Module 1/2) cost",
                                      "mean %.0f tests (box + primitive), max %.0f" % (mo, mxo)))
        rows.append(m2.hstack(tiles))
    if rows:
        save(m2.vstack(rows + [colorbar(min(r[0] for r in rows), lo, hi,
                                        "ray-box + ray-primitive tests per camera ray, including the shadow and "
                                        "secondary rays it causes (log scale)")]), "acc_overview.png")


def read_csv(name):
    p = os.path.join(M3, name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return list(csv.DictReader(f))


def scaling_plots():
    rows = read_csv("acc_scaling.csv")
    if not rows:
        return
    series_t, series_c = [], []
    for layout, name in (("marbles", "marbles"), ("straws", "straws")):
        rs = [r for r in rows if r["layout"] == layout]
        series_t.append(("%s, brute force" % name, [(int(r["primitives"]), float(r["none_s"])) for r in rs]))
        series_t.append(("%s, BVH" % name, [(int(r["primitives"]), float(r["bvh_s"])) for r in rs]))
        series_c.append(("%s, brute force" % name, [(int(r["primitives"]), float(r["prim_tests_per_ray_none"])) for r in rs]))
        series_c.append(("%s, BVH" % name,
                         [(int(r["primitives"]), float(r["prim_tests_per_ray_bvh"]) + float(r["box_tests_per_ray_bvh"]))
                          for r in rs]))
    save(m2.plot(series_t, "Render time against primitive count (400x300, 1 spp, Whitted)", "primitives",
                 "render time (s)", xlog=True, ylog=True), "acc_scaling_time.png")
    save(m2.plot(series_c, "Intersection tests per ray against primitive count (BVH: box + primitive tests)", "primitives",
                 "tests per ray", xlog=True, ylog=True), "acc_scaling_tests.png")


def leaf_plot():
    rows = read_csv("acc_leaf.csv")
    if not rows:
        return
    series = []
    for scene in ("acc_best", "acc_complex"):
        rs = [r for r in rows if r["scene"] == scene]
        base = float(rs[0]["render_s"]) if rs else 1
        series.append(("%s render time" % scene, [(int(r["maxnodeprims"]), float(r["render_s"]) / base) for r in rs]))
    save(m2.plot(series, "BVH leaf size: render time relative to maxnodeprims 1", "maxnodeprims",
                 "relative render time", xlog=True), "acc_leaf.png")


def marker_overlay(img, scale, pts, numbers=True):
    for k, p in enumerate(pts, 1):
        cx, cy = (p["x"] + 0.5) * scale, (p["y"] + 0.5) * scale
        r = 2.2 * scale
        m2.frame(img, (int(cx - r), int(cy - r), int(cx + r), int(cy + r)), YELLOW, 2)
        if numbers:
            mf.badge(img, cx + r + 10, cy - r - 10, 9, k)


def testsuite_figures(per_test=False):
    """The overview of all image tests (and, with per_test, simple per-test figures; the annotated
    per-test figures are written by make_report_figures_m3.py)."""
    res = os.path.join(ST, "results")
    tiles = []
    for d in sorted((x for x in os.listdir(ST) if x.startswith("test") and x[4:].isdigit()), key=lambda s: int(s[4:])):
        n = int(d[4:])
        t = json.load(open(os.path.join(ST, d, "test.json")))
        if t["category"] == "error":
            continue
        ref_png = os.path.join(res, d, "testsuite_ref_%d.png" % n)
        my_png = os.path.join(res, d, "testsuite_my_%d.png" % n)
        if not (os.path.exists(ref_png) and os.path.exists(my_png)):
            print("skip test %d (run studentTests/runAllTests.py first)" % n)
            continue
        shutil.copy(os.path.join(ST, d, "testsuite_ref_%d.png" % n), os.path.join(OUT, "testsuite_ref_%d.png" % n))
        ref, mine = mf.load_png(ref_png), mf.load_png(my_png)
        scale = max(1, int(round(300 / max(ref[0], ref[1]) * 1.5)))
        big = [mf.crop_scaled(i, 0, 0, i[0], i[1], scale) for i in (ref, mine)]
        if t["metric"] == "coverage":
            third = mf.crop_scaled(mf.load_png(os.path.join(res, d, "diff_%d.png" % n)), 0, 0, ref[0], ref[1], scale)
            sub3 = "grey both, red mine only, cyan reference only"
        else:
            # |mine - ref| per pixel, scaled so that 5% of the reference's 99th percentile is white
            R_ = rt.read_pfm(os.path.join(ST, d, t["reference"]))
            M_ = None
            for ext in (".pfm",):
                p = os.path.join(res, d, "testsuite_my_%d%s" % (n, ext))
                if os.path.exists(p):
                    M_ = rt.read_pfm(p)
            lums = sorted(R_.lum(x, y) for y in range(R_.h) for x in range(R_.w))
            s99 = lums[int(0.99 * (len(lums) - 1))] or 1
            e = mf.new_image(R_.w, R_.h)
            for y in range(R_.h):
                for x in range(R_.w):
                    a = R_.rgb(x, y)
                    b = M_.rgb(x, y) if M_ else a
                    v = max(abs(a[k] - b[k]) for k in range(3)) / (0.05 * s99)
                    c = cmap(v)
                    i = 3 * (y * R_.w + x)
                    e[2][i:i + 3] = bytes(c)
            third = mf.crop_scaled(e, 0, 0, R_.w, R_.h, scale)
            sub3 = "|mine - ref|, full scale = 5% of the reference's 99th percentile"
        if t["metric"] == "pixels":
            for im in big:
                marker_overlay(im, scale, t["pixels"])
        elif t["metric"] == "centroids":
            for im in big:
                marker_overlay(im, scale, [{"x": int(m["x"]), "y": int(m["y"])} for m in t["markers"]], numbers=False)
        cap = "test %d: %s" % (n, t["name"])
        row = m2.hstack([m2.captioned(big[0], "testsuite_ref_%d (%s)" % (n, "analytic" if "pbrt_scene" not in t else "pbrt-v4")),
                         m2.captioned(big[1], "testsuite_my_%d (CGR26_renderer)" % n),
                         m2.captioned(third, "difference", sub3)])
        fig = m2.captioned(row, cap, t["description"][:150] + ("..." if len(t["description"]) > 150 else ""))
        if t["metric"] == "pixels":
            keys = ["%d  %s" % (k, p["label"]) for k, p in enumerate(t["pixels"], 1)]
            kh = mf.line_height(15) * ((len(keys) + 1) // 2) + 12
            key = mf.new_image(fig[0], kh)
            for k, s in enumerate(keys):
                mf.draw_text(key, 8 + (k % 2) * fig[0] // 2, 6 + (k // 2) * mf.line_height(15), s, 15, (30, 30, 30))
            fig = m2.vstack([fig, key], gap=0)
        if per_test:
            save(fig, "testsuite_%d.png" % n)
        th = 150
        sm = [mf.resize_box(i, int(round(th * i[0] / i[1])), th) for i in (ref, mine)]
        tiles.append(m2.captioned(m2.vstack(sm, gap=4), "test %d" % n))
    if tiles:
        rows = [m2.hstack(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]
        save(m2.captioned(m2.vstack(rows), "Image tests: pbrt-v4 (or analytic) reference above, CGR26_renderer below"),
             "testsuite_overview.png")


def main():
    acc_overview()
    scaling_plots()
    leaf_plot()
    testsuite_figures()


if __name__ == "__main__":
    main()

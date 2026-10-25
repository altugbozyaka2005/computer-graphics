#!/usr/bin/env python3
"""Quantitative checks of the Module 2 features (Python 3 standard library only).

Each check renders scenes from scenes/module2/validation/ and compares the result with an exact or
independent answer; it prints PASS/FAIL with the numbers and writes output/module2/validation.log.

  python3 scenes/tools/validate_module2.py [--renderer output/CGR26_renderer]

  1  orthographic camera vs pbrt-v4 (object boundaries and shading)       val_ortho_pbrt.pbrt
  2  orthographic size invariance (and perspective 1/z falloff)            val_ortho_size*.pbrt
  3  perspective field of view: disc radius f_px tan(asin(r/d))            val_fov_{20,40,80}.pbrt
  4  pixel samplers vs exact pixel coverage of an edge                     val_edge.pbrt
  5  area-light sample patterns vs the analytic form factor                val_rect_light.pbrt
  6  grid / stratified light sampling rounds N to a square (logged)        val_rect_light.pbrt
  7  branching factor: same expected value, noise / sqrt(BF)               val_bf_furnace.pbrt
  8  dielectric splitting (BF >= 2) vs stochastic choice (BF = 1)          val_bf_glass.pbrt
  9  ray tree: exactly BF^d rays at depth d in a closed box                val_ray_tree.pbrt
 10  1 thread vs all threads: identical images for every new sampler       val_edge / val_rect_light / val_bf_glass
"""
import argparse
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import module2_study as st  # noqa: E402  (PFM loading, log parsing)

ROOT = st.ROOT
VAL = os.path.join(ROOT, "scenes", "module2", "validation")
LINES = []
RESULTS = []
R = st.RENDERER
TMP = os.path.join(st.M2OUT, "validation")


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def check(name, ok, detail):
    RESULTS.append((name, ok))
    say("%s  %s" % ("PASS" if ok else "FAIL", name))
    for line in detail.strip().split("\n"):
        say("      " + line)


def run(scene, out, *opts):
    os.makedirs(TMP, exist_ok=True)
    cmd = [R, os.path.join(VAL, scene), "--quiet", "--outdir", TMP, "--out", out] + list(opts)
    r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if r.returncode != 0:
        raise RuntimeError("render failed: " + " ".join(cmd) + "\n" + r.stderr)
    base = os.path.join(TMP, out)
    w, h, rgb = st.load_pfm(base + ".pfm")
    return w, h, rgb, st.parse_log(base + ".log"), base


def lum_img(rgb):
    return st.luminance(rgb)


# ---------------------------------------------------------------- 1
def check_ortho_pbrt():
    w, h, rgb, _, _ = run("val_ortho_pbrt.pbrt", "val_ortho_pbrt")
    rw, rh, ref = st.load_pfm(os.path.join(VAL, "reference", "val_ortho_pbrt.pfm"))
    a, b = lum_img(rgb), lum_img(ref)
    mism = sum(1 for x, y in zip(a, b) if (x > 0.01) != (y > 0.01))
    errs = sorted(abs(x - y) / y for x, y in zip(a, b) if y > 0.05)
    med = errs[len(errs) // 2]
    check("orthographic camera matches pbrt-v4", (w, h) == (rw, rh) and mism / (w * h) < 0.005 and med < 0.02,
          "lit/unlit boundary mismatch %d of %d pixels (%.3f %%; limit 0.5 %%), median relative shading error %.4f "
          "(limit 0.02)" % (mism, w * h, 100 * mism / (w * h), med))


# ---------------------------------------------------------------- 2
def row_width(lum, w, y, x0, x1):
    return sum(1 for x in range(x0, x1) if lum[y * w + x] > 1e-4)


def check_ortho_size():
    w, h, rgb, _, _ = run("val_ortho_size.pbrt", "val_ortho_size")
    lum = lum_img(rgb)
    # spheres at x = -2 and +2 on the axis y = 0: image rows through their centres = h / 2
    near = row_width(lum, w, h // 2, 0, w // 2)
    far = row_width(lum, w, h // 2, w // 2, w)
    pred = 2 * 1.0 / 8.0 * w
    w2, h2, rgb2, _, _ = run("val_ortho_size_persp.pbrt", "val_ortho_size_persp")
    lum2 = lum_img(rgb2)
    pn, pf = row_width(lum2, w2, h2 // 2, 0, w2 // 2), row_width(lum2, w2, h2 // 2, w2 // 2, w2)
    check("orthographic size does not depend on depth", abs(near - pred) <= 1 and abs(far - pred) <= 1,
          "orthographic: sphere 2 units away %d px, 12 units away %d px, predicted 2r/8*320 = %.0f px\n"
          "perspective (fov 90): %d px vs %d px (ratio %.2f; the spheres are 2 and 12 units away)"
          % (near, far, pred, pn, pf, pn / max(1, pf)))


# ---------------------------------------------------------------- 3
def check_fov():
    lines, ok = [], True
    for fov in (20, 40, 80):
        w, h, rgb, _, _ = run("val_fov_%d.pbrt" % fov, "val_fov_%d" % fov)
        lum = lum_img(rgb)
        area = sum(1 for v in lum if v > 1e-4)
        fpx = (h / 2) / math.tan(math.radians(fov) / 2)
        rpred = fpx * math.tan(math.asin(1 / 10))
        rmeas = math.sqrt(area / math.pi)
        ok = ok and abs(rmeas - rpred) < 0.5 + 0.01 * rpred
        lines.append("fov %2d: f_px %.1f, disc radius %.2f px measured (from its area), %.2f predicted" % (fov, fpx, rmeas, rpred))
    check("perspective field of view: apparent size proportional to 1/tan(fov/2)", ok, "\n".join(lines))


# ---------------------------------------------------------------- 4
def edge_exact(W=64, H=64):
    def f(p):
        return 64 * (p[1] - 10) - 40.3 * p[0]

    def clip(poly):
        out = []
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            fa, fb = f(a), f(b)
            if fa > 0:
                out.append(a)
            if (fa > 0) != (fb > 0):
                t = fa / (fa - fb)
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        return out

    def area(poly):
        n = len(poly)
        return abs(sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))) / 2 if n > 2 else 0
    return [area(clip([(px, H - py - 1), (px + 1, H - py - 1), (px + 1, H - py), (px, H - py)])) for py in range(H) for px in range(W)]


def check_edge():
    exact = edge_exact()
    edge = [i for i, v in enumerate(exact) if 0 < v < 1]
    res = {}
    lines = ["edge-pixel RMSE (%d pixels cut by the edge) against the exact coverage:" % len(edge)]
    off_err = 0.0
    for name, opts in (("independent", ["--sampler", "independent"]), ("regular grid", ["--sampler", "stratified", "--nojitter"]),
                       ("jittered", ["--sampler", "stratified"]), ("halton", ["--sampler", "halton"])):
        row = []
        for n in (1, 2, 4, 8, 16):
            _, _, rgb, _, _ = run("val_edge.pbrt", "val_edge", *(opts + ["--spp", str(n * n)]))
            v = rgb[0::3]
            e = math.sqrt(sum((v[i] - exact[i]) ** 2 for i in edge) / len(edge))
            off_err = max(off_err, max(abs(v[i] - exact[i]) for i in range(len(v)) if exact[i] in (0.0, 1.0)))
            res[(name, n * n)] = e
            row.append("%3d: %.4f" % (n * n, e))
        lines.append("  %-13s %s" % (name, "  ".join(row)))
    ok = off_err == 0 and all(res[(k, 256)] < 0.03 for k in ("independent", "regular grid", "jittered", "halton"))
    ok = ok and all(res[(k, s)] < res[("independent", s)] for k in ("jittered", "halton") for s in (16, 64, 256))
    lines.append("pixels entirely on one side of the edge: max error %.1e (must be 0)" % off_err)
    lines.append("order of convergence (log-log slope 16 -> 256 spp): " + ", ".join(
        "%s %.2f" % (k, math.log(res[(k, 256)] / res[(k, 16)]) / math.log(16)) for k in ("independent", "regular grid", "jittered", "halton")))
    check("supersampling converges to the exact pixel coverage; stratified and Halton beat random", ok, "\n".join(lines))


# ---------------------------------------------------------------- 5, 6
def form_factor():
    def corner(X, Y):
        return (X / math.sqrt(1 + X * X) * math.atan(Y / math.sqrt(1 + X * X)) +
                Y / math.sqrt(1 + Y * Y) * math.atan(X / math.sqrt(1 + Y * Y))) / (2 * math.pi)
    h, px, pz = 1.5, 0.3, -0.2
    return sum(corner(a / h, b / h) for a in (1 - px, 1 + px) for b in (1 - pz, 1 + pz))


def check_light_patterns(trials=16):
    F = form_factor()
    lines = ["analytic value (form factor, rho = L = 1): %.6f; relative RMSE over %d seeds:" % (F, trials)]
    res = {}
    for strat in ("uniform", "grid", "stratified", "halton"):
        row = []
        for n in (1, 16, 256, 4096):
            vals = []
            for s in range(trials if strat != "grid" else 1):
                _, _, rgb, _, _ = run("val_rect_light.pbrt", "val_rect", "--lightsampling", strat, "--lightsamples", str(n),
                                      "--seed", str(s + 1))
                vals.append(rgb[1])
            e = math.sqrt(sum((v - F) ** 2 for v in vals) / len(vals)) / F
            res[(strat, n)] = e
            row.append("%4d: %.1e" % (n, e))
        lines.append("  %-10s %s   slope %.2f" % (strat, "  ".join(row), math.log(res[(strat, 4096)] / res[(strat, 16)]) / math.log(256)))
    ok = all(res[(k, 4096)] < 5e-3 for k in ("uniform", "grid", "stratified", "halton"))
    ok = ok and all(res[(k, 256)] < res[("uniform", 256)] for k in ("grid", "stratified", "halton"))
    check("area-light sample patterns converge to the analytic irradiance", ok, "\n".join(lines))
    _, _, _, _, base = run("val_rect_light.pbrt", "val_rect", "--lightsampling", "grid", "--lightsamples", "10")
    log = open(base + ".log").read()
    ok = "lightsamples 9 (grid)" in log
    check("grid light sampling uses n x n samples (10 requested -> 3 x 3)", ok,
          [l for l in log.split("\n") if "integrator:" in l][0].split("] ", 1)[-1])


# ---------------------------------------------------------------- 7
def check_bf_furnace():
    lines, stats = [], {}
    for bf in (1, 4, 16):
        _, _, a, _, _ = run("val_bf_furnace.pbrt", "furn_a", "--bf", str(bf), "--seed", "1")
        _, _, b, _, _ = run("val_bf_furnace.pbrt", "furn_b", "--bf", str(bf), "--seed", "2")
        w = 100
        idx = [y * w + x for y in range(w) for x in range(w) if (x - 49.5) ** 2 + (y - 49.5) ** 2 < 30 ** 2]
        va, vb = [a[3 * i] for i in idx], [b[3 * i] for i in idx]
        m = (sum(va) + sum(vb)) / (2 * len(idx))
        sig = math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)) / (2 * len(idx)))
        stats[bf] = (m, sig, len(idx))
        lines.append("BF %2d: mean %.5f (expected 0.5), per-pixel std dev %.4f" % (bf, m, sig))
    ok = all(abs(stats[b][0] - 0.5) < 4 * stats[b][1] / math.sqrt(2 * stats[b][2]) + 2e-3 for b in stats)
    r4, r16 = stats[1][1] / stats[4][1], stats[1][1] / stats[16][1]
    ok = ok and 1.7 < r4 < 2.3 and 3.3 < r16 < 4.7
    lines.append("std dev ratio BF1/BF4 = %.2f (sqrt 4 = 2), BF1/BF16 = %.2f (sqrt 16 = 4)" % (r4, r16))
    check("branching factor keeps the expected value and divides the noise by sqrt(BF)", ok, "\n".join(lines))


# ---------------------------------------------------------------- 8
def check_bf_glass():
    _, _, a, ia, _ = run("val_bf_glass.pbrt", "glass1", "--bf", "1", "--spp", "1024")
    _, _, b, ib, _ = run("val_bf_glass.pbrt", "glass2", "--bf", "2", "--spp", "256")
    la, lb = lum_img(a), lum_img(b)
    ma, mb = sum(la) / len(la), sum(lb) / len(lb)
    check("dielectric splitting (BF 2) gives the same image as the Fresnel choice (BF 1)", abs(mb / ma - 1) < 0.01,
          "mean radiance: BF 1 at 1024 spp %.5f, BF 2 (both lobes) at 256 spp %.5f (difference %.2f %%; limit 1 %%)"
          % (ma, mb, 100 * (mb / ma - 1)))


# ---------------------------------------------------------------- 9
def check_ray_tree():
    lines, ok = [], True
    for bf, md in ((1, 5), (3, 5), (5, 3)):
        _, _, _, info, _ = run("val_ray_tree.pbrt", "tree", "--bf", str(bf), "--maxdepth", str(md))
        d = info["depth"]
        cam = d[0]
        per = [d.get(k, 0) / cam for k in range(md + 1)]
        exp = [bf ** k for k in range(md)] + [0]
        ok = ok and all(abs(p - e) < 1e-9 for p, e in zip(per, exp))
        lines.append("BF %d, MD %d: rays per camera ray at depth 0..%d = %s (expected %s)" % (
            bf, md, md, " ".join("%g" % p for p in per), " ".join(str(e) for e in exp)))
    check("ray tree: BF^d rays at depth d (the last level is not traced without an environment)", ok, "\n".join(lines))


# ---------------------------------------------------------------- 10
def check_threads():
    lines, ok = [], True
    for scene, opts in (("val_edge.pbrt", ["--sampler", "stratified", "--spp", "16"]), ("val_edge.pbrt", ["--sampler", "halton", "--spp", "16"]),
                        ("val_bf_glass.pbrt", ["--bf", "3", "--spp", "4", "--lightsampling", "halton"]),
                        ("val_bf_glass.pbrt", ["--spp", "4", "--lightsampling", "stratified"])):
        _, _, a, _, _ = run(scene, "thr1", *(opts + ["--threads", "1"]))
        _, _, b, _, _ = run(scene, "thrN", *opts)
        same = a == b
        ok = ok and same
        lines.append("%s %s: %s" % (scene, " ".join(opts), "identical" if same else "DIFFERENT"))
    check("deterministic: 1 thread and all threads give identical images", ok, "\n".join(lines))


def main():
    global R
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renderer", default=R)
    args = ap.parse_args()
    R = os.path.abspath(args.renderer)
    say("Module 2 validation (%s)" % os.path.relpath(R, ROOT))
    for fn in (check_ortho_pbrt, check_ortho_size, check_fov, check_edge, check_light_patterns, check_bf_furnace,
               check_bf_glass, check_ray_tree, check_threads):
        try:
            fn()
        except Exception as e:  # a crash is a failed check, not an aborted run
            check(fn.__name__, False, "exception: %s" % e)
    n_ok = sum(1 for _, ok in RESULTS if ok)
    say("== %d of %d checks passed" % (n_ok, len(RESULTS)))
    os.makedirs(st.M2OUT, exist_ok=True)
    with open(os.path.join(st.M2OUT, "validation.log"), "w") as f:
        f.write("\n".join(LINES) + "\n")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()

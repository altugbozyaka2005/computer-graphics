#!/usr/bin/env python3
"""Quantitative checks behind the numbers in the Module 1 report (Python 3 standard library only).

Usage (from the project root, after ./renderReportedImages.sh has rendered the images):
    python3 scenes/tools/validate_module1.py [--renderer output/CGR26_renderer] [--outdir output]

Reads the linear .pfm images and .log files in output/ and writes
    output/validation.log          a readable summary of every check (PASS / FAIL / INFO)
    output/validation/*.csv        data series plotted in the report
Checks:
  1  WSRT point light vs the analytic value  L = Kd I cos(theta) / d^2   (val_wsrt_pointlight)
  2  DRT white furnace: Phong-lobe albedo vs numerical integration       (val_drt_furnace)
  3  pbrt-v4 comparisons: object masks and pixel windows                  (scenes/validation/pbrt)
  4  WSRT maxdepth sweep: pixels that change between depths              (WSRT_simple_md*)
  5  DRT shadow-ray count: error in the penumbra vs the 256 spp render   (DRT_simple_ls*)
  6  Thin lens: size of a defocused wall lamp vs the circle of confusion (WSRT/DRT_creative)
  7  Error handling: the 18 broken scenes are logged, without a crash     (scenes/validation/errors)
  8  Snell's window: Fresnel transmission and total internal reflection  (val_wsrt_snell)
  9  Area-light noise vs shadow rays: sigma ~ 1/sqrt(N)                  (val_drt_penumbra_ls*_s1/2)
 10  Filtered shadow through a glass slab: Kd I/d^2 (1-F)^2              (val_wsrt_filteredshadow)
"""
import argparse
import array
import json
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_LINES = []


def say(s=""):
    print(s)
    OUT_LINES.append(s)


# ------------------------------------------------------------------ images
class Img:
    def __init__(self, w, h, data):
        self.w, self.h, self.d = w, h, data  # data: flat RGB floats, top row first

    def px(self, x, y):
        i = 3 * (y * self.w + x)
        return self.d[i], self.d[i + 1], self.d[i + 2]

    def lum(self, x, y):
        r, g, b = self.px(x, y)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b


def read_pfm(path):
    with open(path, "rb") as f:
        if f.readline().strip() != b"PF":
            raise ValueError(path + ": not an RGB PFM")
        dims = f.readline().split()
        w, h = int(dims[0]), int(dims[1])
        scale = float(f.readline())
        a = array.array("f")
        a.frombytes(f.read(w * h * 12))
    if (scale < 0) != (sys.byteorder == "little"):
        a.byteswap()
    rows = [a[(h - 1 - y) * w * 3:(h - y) * w * 3] for y in range(h)]  # PFM rows run bottom-to-top
    flat = array.array("f")
    for r in rows:
        flat.extend(r)
    return Img(w, h, flat)


def srgb8(v):
    v = min(1.0, max(0.0, v))
    v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return int(v * 255 + 0.5)


# ------------------------------------------------------------------ camera (pbrt-v4 LookAt + perspective)
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a): return mul(a, 1 / math.sqrt(dot(a, a)))


class Camera:
    def __init__(self, eye, look, up, fov, xres, yres):
        self.eye = eye
        self.dir = norm(sub(look, eye))
        self.right = norm(cross(norm(up), self.dir))
        self.up = cross(self.dir, self.right)
        self.xres, self.yres = xres, yres
        aspect = xres / yres
        self.win = (-aspect, aspect, -1, 1) if aspect > 1 else (-1, 1, -1 / aspect, 1 / aspect)
        self.t = math.tan(math.radians(fov) / 2)

    def ray(self, fx, fy):  # film position in pixels (pixel centre = x + 0.5)
        sx = self.win[0] + fx / self.xres * (self.win[1] - self.win[0])
        sy = self.win[3] - fy / self.yres * (self.win[3] - self.win[2])
        d = add(add(mul(self.right, sx * self.t), mul(self.up, sy * self.t)), self.dir)
        return self.eye, norm(d)

    def project(self, p):  # world point -> (film x, film y, depth along the optical axis)
        v = sub(p, self.eye)
        z = dot(v, self.dir)
        sx = dot(v, self.right) / z / self.t
        sy = dot(v, self.up) / z / self.t
        fx = (sx - self.win[0]) / (self.win[1] - self.win[0]) * self.xres
        fy = (self.win[3] - sy) / (self.win[3] - self.win[2]) * self.yres
        return fx, fy, z

    def units_per_pixel_at(self, depth):  # pixel size on a plane at this depth
        return (self.win[1] - self.win[0]) * self.t * depth / self.xres


def hit_sphere(o, d, c, r):
    oc = sub(o, c)
    b = dot(oc, d)
    disc = b * b - (dot(oc, oc) - r * r)
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


def write_csv(outdir, name, header, rows):
    os.makedirs(os.path.join(outdir, "validation"), exist_ok=True)
    with open(os.path.join(outdir, "validation", name), "w") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(("%.6g" % v) if isinstance(v, float) else str(v) for v in r) + "\n")


def verdict(ok):
    return "PASS" if ok else "FAIL"


# ------------------------------------------------------------------ 1 point light
def check_pointlight(outdir):
    say("== 1  WSRT point light vs analytic value (val_wsrt_pointlight)")
    img = read_pfm(os.path.join(outdir, "val_wsrt_pointlight.pfm"))
    cam = Camera((0, 6, -6), (0, 0, 0), (0, 1, 0), 50, img.w, img.h)
    light, I, kd = (1, 3, 0.5), 10.0, 0.5
    worst, n, worst_at = 0.0, 0, None
    rows = []
    for y in range(img.h):
        for x in range(img.w):
            o, d = cam.ray(x + 0.5, y + 0.5)
            if d[1] >= 0:
                continue
            p = add(o, mul(d, -o[1] / d[1]))
            l = sub(light, p)
            d2 = dot(l, l)
            expect = kd * I * (l[1] / math.sqrt(d2)) / d2
            got = img.px(x, y)[0]
            err = abs(got - expect) / expect
            n += 1
            if err > worst:
                worst, worst_at = err, (x, y, got, expect, math.sqrt(d2))
            if y == img.h // 2 and x % 10 == 0:
                rows.append((x, math.sqrt(d2), expect, got))
    write_csv(outdir, "pointlight_row.csv", ["x", "d", "expected", "rendered"], rows)
    x, y, got, expect, dist = worst_at
    say("   %d pixels compared; worst relative error %.2e at pixel (%d,%d): rendered %.6f, analytic %.6f (d = %.3f)"
        % (n, worst, x, y, got, expect, dist))
    say("   %s (threshold 1e-4)" % verdict(worst < 1e-4))
    return worst


def check_filtered_shadow(outdir):
    say("== 10 WSRT filtered shadow through a glass slab (val_wsrt_filteredshadow)")
    img = read_pfm(os.path.join(outdir, "val_wsrt_filteredshadow.pfm"))
    got = img.px(img.w // 2, img.h // 2)[0]
    f0 = fresnel_dielectric(1.0, 1.5)
    expect = 0.5 * 16 / 16 * (1 - f0) ** 2
    err = abs(got - expect) / expect
    say("   floor below the light: rendered %.6f, analytic Kd I/d^2 (1-F)^2 = %.6f (F = %.4f): rel. error %.1e -> %s"
        % (got, expect, f0, err, verdict(err < 1e-4)))
    return err


# ------------------------------------------------------------------ 2 furnace
def phong_lobe_albedo(n, cos_o, steps=360):
    """Directional albedo of ks (n+2)/(2pi) max(0, r.wi)^n with ks = 1, by midpoint quadrature."""
    so = math.sqrt(max(0.0, 1 - cos_o * cos_o))
    total = 0.0
    db, dp = (math.pi / 2) / steps, (2 * math.pi) / steps
    for i in range(steps):
        b = (i + 0.5) * db
        cb, sb = math.cos(b), math.sin(b)
        w = (n + 2) / (2 * math.pi) * cb ** n * sb * db * dp
        for j in range(steps):
            ci = cb * cos_o + sb * so * math.cos((j + 0.5) * dp)  # cos(theta_i) with r on the z axis
            if ci > 0:
                total += w * ci
    return total


def check_furnace(outdir):
    say("== 2  DRT white furnace (val_drt_furnace): mean reflected radiance vs analytic albedo")
    img = read_pfm(os.path.join(outdir, "val_drt_furnace.pfm"))
    cam = Camera((0, 0, -60), (0, 0, 0), (0, 1, 0), 4.772, img.w, img.h)
    rad = 1.0
    spheres = [("A diffuse 0.5", -18, lambda c: 0.5),
               ("B phong Kd 1", -6, lambda c: 1.0),
               ("C phong Ks 1 n 20", 6, lambda c: phong_lobe_albedo(20, c)),
               ("D phong Kd 0.8->0.5 Ks 0.5 n 50", 18, lambda c: 0.5 + 0.5 * phong_lobe_albedo(50, c))]
    nb = 10
    rows = []
    ok_all = True
    for name, cx, model in spheres:
        bins = [[0.0, 0] for _ in range(nb)]
        tot, cnt, mx = 0.0, 0, 0.0
        for y in range(img.h):
            for x in range(img.w):
                # only pixels that lie entirely on the sphere (all four corners hit it): pixels on the
                # silhouette average the sphere with the white background
                if any(hit_sphere(*cam.ray(x + i, y + j), (cx, 0, 0), rad) is None for i in (0, 1) for j in (0, 1)):
                    continue
                o, d = cam.ray(x + 0.5, y + 0.5)
                t = hit_sphere(o, d, (cx, 0, 0), rad)
                p = add(o, mul(d, t))
                nrm = norm(sub(p, (cx, 0, 0)))
                c = -dot(nrm, d)
                v = sum(img.px(x, y)) / 3
                k = min(nb - 1, int(c * nb))
                bins[k][0] += v
                bins[k][1] += 1
                tot += v
                cnt += 1
                mx = max(mx, v)
        say("   %-34s %6d px  mean %.4f   max pixel %.3f" % (name, cnt, tot / cnt, mx))
        for k in range(nb):
            if bins[k][1] < 20:
                continue
            c = (k + 0.5) / nb
            exp = model(c)
            got = bins[k][0] / bins[k][1]
            rows.append((name.split()[0], c, exp, got, bins[k][1]))
            if abs(got - exp) > 0.02 + 0.02 * exp:
                ok_all = False
            if got > 1.0 + 0.01:
                ok_all = False
    say("   binned by cos(theta_o) (10 bins):  sphere, cos, analytic, rendered")
    for r in rows:
        say("     %s  %.2f  %.4f  %.4f" % r[:4])
    write_csv(outdir, "furnace_profile.csv", ["sphere", "cos_o", "analytic", "rendered", "pixels"], rows)
    say("   %s (each bin within 2%% + 0.02 of the analytic albedo, and no bin above 1.01)" % verdict(ok_all))
    return rows


# ------------------------------------------------------------------ 3 pbrt comparisons
def check_pbrt(outdir):
    say("== 3  Comparison with pbrt-v4 (scenes/validation/pbrt, references rendered by pbrt-v4)")
    base = os.path.join(ROOT, "scenes", "validation", "pbrt")
    results = []
    for n in (1, 2, 4, 5, 6, 7, 8):
        t = json.load(open(os.path.join(base, "test%d.json" % n)))
        mine = read_pfm(os.path.join(outdir, "val_pbrt_%d.pfm" % n))
        ref = read_pfm(os.path.join(base, t["reference"]))
        if t["metric"] == "mask":
            lev = t.get("mask_level", 0.01)
            mism = inter = union = 0
            for y in range(ref.h):
                for x in range(ref.w):
                    a, b = mine.lum(x, y) > lev, ref.lum(x, y) > lev
                    mism += a != b
                    inter += a and b
                    union += a or b
            frac = mism / (ref.w * ref.h)
            say("   test%d  mask: %d of %d pixels differ (%.3f%%), IoU %.4f -> %s (threshold %.2f%%)"
                % (n, mism, ref.w * ref.h, 100 * frac, inter / max(1, union), verdict(frac <= t["threshold"]),
                   100 * t["threshold"]))
            results.append((n, "mask", frac, t["threshold"]))
        else:
            r = t.get("window", 1)
            worst = 0.0
            for (px, py) in t["pixels"]:
                ma, mb = [0.0] * 3, [0.0] * 3
                k = 0
                for yy in range(py - r, py + r + 1):
                    for xx in range(px - r, px + r + 1):
                        a, b = mine.px(xx, yy), ref.px(xx, yy)
                        for c in range(3):
                            ma[c] += a[c]
                            mb[c] += b[c]
                        k += 1
                ma = [v / k for v in ma]
                mb = [v / k for v in mb]
                errs = [abs(ma[c] - mb[c]) / max(mb[c], 1e-4) for c in range(3)]
                worst = max(worst, max(errs))
                say("   test%d  pixel (%d,%d) %dx%d mean: ours %.5f %.5f %.5f | pbrt %.5f %.5f %.5f | rel.err %.4f %.4f %.4f"
                    % ((n, px, py, 2 * r + 1, 2 * r + 1) + tuple(ma) + tuple(mb) + tuple(errs)))
            say("   test%d  worst relative error %.2f%% -> %s (threshold %.0f%%)"
                % (n, 100 * worst, verdict(worst <= t["threshold"]), 100 * t["threshold"]))
            results.append((n, "pixels", worst, t["threshold"]))
    write_csv(outdir, "pbrt_compare.csv", ["test", "metric", "value", "threshold"], results)
    return results


# ------------------------------------------------------------------ 4 maxdepth
def check_maxdepth(outdir):
    say("== 4  WSRT maxdepth sweep: pixels whose 8-bit display value changes between depths")
    names = ["WSRT_simple_md1", "WSRT_simple_md2", "WSRT_simple_md3", "WSRT_simple"]
    imgs = [read_pfm(os.path.join(outdir, s + ".pfm")) for s in names]
    rows = []
    for a, b, la, lb in ((0, 1, 1, 2), (1, 2, 2, 3), (2, 3, 3, 8)):
        A, B = imgs[a], imgs[b]
        changed, total, sad = 0, A.w * A.h, 0.0
        for i in range(total):
            ch = False
            for c in range(3):
                va, vb = A.d[3 * i + c], B.d[3 * i + c]
                sad += abs(va - vb)
                if abs(srgb8(va) - srgb8(vb)) > 1:
                    ch = True
            changed += ch
        say("   maxdepth %d -> %d: %.3f%% of pixels change by more than 1/255, mean |dL| %.2e"
            % (la, lb, 100 * changed / total, sad / (3 * total)))
        rows.append((la, lb, 100 * changed / total, sad / (3 * total)))
    write_csv(outdir, "maxdepth.csv", ["from", "to", "pct_changed", "mean_abs_diff"], rows)
    return rows


# ------------------------------------------------------------------ 5 light samples
def log_value(path, key):
    for line in open(path):
        if line.startswith(key):
            return float(line.split(":")[1])
    return float("nan")


def check_lightsamples(outdir):
    say("== 5  DRT shadow rays per sample (DRT_simple_ls1/4/16 at 4 spp) vs the 256 spp render")
    ref = read_pfm(os.path.join(outdir, "DRT_simple.pfm"))
    box = (240, 610, 600, 690)  # penumbra and umbra of the torus on the floor
    rows = []
    for n in (1, 4, 16):
        name = "DRT_simple_ls%d" % n
        img = read_pfm(os.path.join(outdir, name + ".pfm"))
        se, k = 0.0, 0
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                a, b = img.lum(x, y), ref.lum(x, y)
                se += (a - b) ** 2
                k += 1
        rmse = math.sqrt(se / k)
        t = log_value(os.path.join(outdir, name + ".log"), "render (s)")
        sh = log_value(os.path.join(outdir, name + ".log"), "shadow rays")
        rows.append((n, 4 * n, rmse, t, sh))
    say("   region x %d-%d, y %d-%d (torus shadow); luminance RMSE vs DRT_simple.pfm (256 spp, 4 shadow rays)"
        % (box[0], box[2], box[1], box[3]))
    say("   shadow rays/sample  per pixel   RMSE      RMSE / RMSE(N=1)       render s  shadow rays")
    for (n, pp, rmse, t, sh) in rows:
        say("   %5d              %5d       %.4f    %.3f                   %6.2f    %.3g"
            % (n, pp, rmse, rmse / rows[0][2], t, sh))
    write_csv(outdir, "lightsamples.csv", ["lightsamples", "per_pixel", "rmse", "render_s", "shadow_rays"], rows)
    return rows


def check_penumbra_variance(outdir):
    say("== 9  Area-light estimator noise vs shadow rays (val_drt_penumbra: direct light, pinhole, 1 spp)")
    rows = []
    for n in (1, 4, 16, 64, 256, 1024):
        a = read_pfm(os.path.join(outdir, "val_drt_penumbra_ls%d_s1.pfm" % n))
        b = read_pfm(os.path.join(outdir, "val_drt_penumbra_ls%d_s2.pfm" % n))
        # Two renders with independent seeds: E[(a - b)^2] = 2 sigma^2 per pixel.
        s2 = sum((a.lum(x, y) - b.lum(x, y)) ** 2 for y in range(a.h) for x in range(a.w)) / (2 * a.w * a.h)
        t = log_value(os.path.join(outdir, "val_drt_penumbra_ls%d_s1.log" % n), "render (s)")
        rows.append((n, math.sqrt(s2), math.sqrt(s2) * math.sqrt(n), t))
    say("   shadow rays N   sigma (RMS over %dx%d px)   sigma x sqrt(N)   render s" % (a.w, a.h))
    for r in rows:
        say("   %6d          %.5f                    %.5f           %.3f" % r)
    # least-squares slope of log sigma against log N
    xs = [math.log(r[0]) for r in rows]
    ys = [math.log(r[1]) for r in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    say("   log-log slope %.3f (Monte Carlo theory: -0.5) -> %s (within 0.05)" % (slope, verdict(abs(slope + 0.5) < 0.05)))
    write_csv(outdir, "penumbra_sigma.csv", ["N", "sigma", "sigma_sqrtN", "render_s"], rows)
    return rows


# ------------------------------------------------------------------ 6 thin lens
def blob_moments(img, cx, cy, half):
    xs = range(int(cx) - half, int(cx) + half + 1)
    ys = range(int(cy) - half, int(cy) + half + 1)
    border = sorted([img.lum(x, ys[0]) for x in xs] + [img.lum(x, ys[-1]) for x in xs]
                    + [img.lum(xs[0], y) for y in ys] + [img.lum(xs[-1], y) for y in ys])
    bg = border[len(border) // 2]
    s = sx = sy = sxx = syy = 0.0
    for y in ys:
        for x in xs:
            w = max(0.0, img.lum(x, y) - bg)
            s += w
            sx += w * (x + 0.5)
            sy += w * (y + 0.5)
    mx, my = sx / s, sy / s
    for y in ys:
        for x in xs:
            w = max(0.0, img.lum(x, y) - bg)
            sxx += w * (x + 0.5 - mx) ** 2
            syy += w * (y + 0.5 - my) ** 2
    return mx, my, sxx / s, syy / s


def check_thinlens(outdir):
    say("== 6  Thin lens: defocused wall lamps in DRT_creative vs the pinhole WSRT_creative")
    W = read_pfm(os.path.join(outdir, "WSRT_creative.pfm"))
    D = read_pfm(os.path.join(outdir, "DRT_creative.pfm"))
    cam = Camera((0, 9.2, 0), (0, 6.027, 9.4832), (0, 1, 0), 46.2, W.w, W.h)
    R, f = 0.2, 23.4
    rows = []
    for lx in (-130, -85, 30, 100):  # wall-lamp centres (x), y 22, z 469.8 (include/poolhall_spots_*.pbrt)
        fx, fy, z = cam.project((lx, 22.0, 469.8))
        if not (40 < fx < W.w - 40):
            continue
        coc = R * abs(z - f) / z / cam.units_per_pixel_at(f)  # circle-of-confusion radius in pixels
        _, _, wxx, wyy = blob_moments(W, fx, fy, 30)
        _, _, dxx, dyy = blob_moments(D, fx, fy, 30)
        # Convolution adds variances; a uniform disc of radius rho has variance rho^2 / 4 per axis.
        mx_ = 2 * math.sqrt(max(0.0, dxx - wxx))
        my_ = 2 * math.sqrt(max(0.0, dyy - wyy))
        rows.append((lx, fx, fy, z, coc, mx_, my_))
        say("   lamp x=%5.0f at pixel (%.0f,%.0f), depth %.1f: predicted CoC radius %.2f px; measured %.2f px (x), %.2f px (y)"
            % (lx, fx, fy, z, coc, mx_, my_))
    write_csv(outdir, "thinlens.csv", ["lamp_x", "px", "py", "depth", "coc_pred_px", "coc_meas_x", "coc_meas_y"], rows)
    if rows:
        err = max(max(abs(r[5] - r[4]), abs(r[6] - r[4])) / r[4] for r in rows)
        say("   worst deviation from the thin-lens prediction: %.1f%% -> %s (threshold 10%%)" % (100 * err, verdict(err < 0.1)))
    return rows


# ------------------------------------------------------------------ 8 Snell's window
def fresnel_dielectric(cos_i, eta):
    """Unpolarised Fresnel reflectance (pbrt-v4 FrDielectric); cos_i < 0: arriving from inside."""
    if cos_i < 0:
        eta, cos_i = 1 / eta, -cos_i
    sin2_t = (1 - cos_i * cos_i) / (eta * eta)
    if sin2_t >= 1:
        return 1.0
    cos_t = math.sqrt(1 - sin2_t)
    r_par = (eta * cos_i - cos_t) / (eta * cos_i + cos_t)
    r_perp = (cos_i - eta * cos_t) / (cos_i + eta * cos_t)
    return (r_par * r_par + r_perp * r_perp) / 2


def check_snell(outdir):
    say("== 8  Snell's window (val_wsrt_snell): Fresnel transmission and TIR through a water surface")
    img = read_pfm(os.path.join(outdir, "val_wsrt_snell.pfm"))
    cam = Camera((0, -1, 0), (0, 0, 0), (0, 0, 1), 130, img.w, img.h)
    eta, sky_b = 1.33, 0.5
    y = img.h // 2
    rows, worst, sq, edge, edge_exp = [], 0.0, 0.0, None, None
    for x in range(img.w // 2, img.w):
        # expected value averaged over an 8 x 8 grid of positions in the pixel (the render jitters)
        acc = 0.0
        for j in range(8):
            for i in range(8):
                o, d = cam.ray(x + (i + 0.5) / 8, y + (j + 0.5) / 8)
                # exit point on the water sphere (centre (0,-1000,0), radius 1000) and its outward normal
                oc = sub(o, (0, -1000, 0))
                b = dot(oc, d)
                t = -b + math.sqrt(b * b - (dot(oc, oc) - 1000.0 ** 2))
                nrm = norm(sub(add(o, mul(d, t)), (0, -1000, 0)))
                acc += 1 - fresnel_dielectric(-dot(d, nrm), eta)  # negative cosine: leaving the water
        expect = sky_b * eta * eta * acc / 64
        _, d = cam.ray(x + 0.5, y + 0.5)
        theta = math.degrees(math.acos(d[1]))
        got = img.px(x, y)[2]
        worst = max(worst, abs(got - expect))
        sq += (got - expect) ** 2
        if edge is None and got < 0.01 * sky_b * eta * eta:
            edge = theta
        if edge_exp is None and expect < 0.01 * sky_b * eta * eta:
            edge_exp = theta
        rows.append((x, theta, expect, got))
    write_csv(outdir, "snell_row.csv", ["x", "theta_deg", "expected_blue", "rendered_blue"], rows)
    crit = math.degrees(math.asin(1 / eta))
    rms = math.sqrt(sq / len(rows))
    say("   centre row, %d pixels: RMS |rendered - analytic| = %.5f, worst %.4f (blue at normal incidence %.4f)"
        % (len(rows), rms, worst, sky_b * eta * eta * (1 - fresnel_dielectric(-1, eta))))
    say("   window edge (first pixel with blue < 1%% of the sky): rendered %.2f deg, analytic %.2f deg; "
        "critical angle asin(1/%.2f) = %.2f deg" % (edge if edge is not None else float("nan"),
                                                  edge_exp if edge_exp is not None else float("nan"), eta, crit))
    ok = rms < 0.005 and worst < 0.05 and edge is not None and edge == edge_exp
    say("   %s (RMS < 0.005, every pixel within 0.05, same edge pixel)" % verdict(ok))
    return rows


# ------------------------------------------------------------------ 7 errors
def check_errors(outdir, renderer):
    say("== 7  Error handling: deliberately broken scenes (scenes/validation/errors)")
    base = os.path.join(ROOT, "scenes", "validation", "errors")
    files = sorted((f for f in os.listdir(base) if f.endswith(".pbrt")), key=lambda s: int(s.split("_")[1][:-5]))
    ok = 0
    for f in files:
        stem = "val_err_" + f[:-5].split("_")[1]
        p = subprocess.run([renderer, os.path.join(base, f), "--quiet", "--outdir", outdir, "--out", stem],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logp = os.path.join(outdir, stem + ".log")
        first = ""
        if os.path.exists(logp):
            for line in open(logp):
                if line.startswith("[ERROR]"):
                    first = line.strip()
                    first = first[:8] + first[first.find(f):] if f in first else first
                    break
        good = p.returncode in (0, 1) and first != ""
        ok += good
        say("   %-18s exit %d  %s  %s" % (f, p.returncode, verdict(good), first))
    say("   %d / %d broken scenes reported with a descriptive error and no crash" % (ok, len(files)))
    return ok, len(files)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renderer", default=os.path.join(ROOT, "output", "CGR26_renderer"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    a = ap.parse_args()
    for fn in (check_pointlight, check_filtered_shadow, check_snell, check_furnace, check_pbrt, check_maxdepth, check_lightsamples,
               check_penumbra_variance, check_thinlens):
        try:
            fn(a.outdir)
        except (OSError, ValueError) as e:
            say("   skipped: %s" % e)
        say()
    check_errors(a.outdir, a.renderer)
    with open(os.path.join(a.outdir, "validation.log"), "w") as f:
        f.write("\n".join(OUT_LINES) + "\n")
    print("wrote %s" % os.path.join(a.outdir, "validation.log"))


if __name__ == "__main__":
    main()

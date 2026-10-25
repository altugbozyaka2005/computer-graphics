#!/usr/bin/env python3
"""Module 2 renders and measurements (Python 3 standard library only).

Renders every Module 2 image with output/CGR26_renderer and computes the numbers behind them:

  output/<name>.png .pfm .log    the required images (camera_ortho, camera_fov1, aa_ss9, sampler_halton_16,
                                 param_large_high, ...), from scenes/<name>.pbrt
  output/module2/<study>/        the extra views and sweeps (scenes/module2/<study>/*.pbrt)
  output/module2/*.csv           the measurements, one file per study
  output/module2/module2.log     a readable summary of all measurements

  python3 scenes/tools/module2_study.py [--only camera,aa,sampler,param] [--trials N] [--pbrt PATH]

Repeated renders of the same scene use different --seed values (independent random streams); they
are deleted once their statistics have been accumulated. The pbrt-v4 reference of the sampler study
is rendered when pbrt is available (--pbrt, default ~/pbrt-v4/build/pbrt) and otherwise read from
scenes/module2/sampler/reference/sampler_ref_pbrt.pfm.
"""
import argparse
import csv
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SC = os.path.join(ROOT, "scenes")
OUT = os.path.join(ROOT, "output")
M2OUT = os.path.join(OUT, "module2")
RENDERER = os.path.join(OUT, "CGR26_renderer")
VIEWS = json.load(open(os.path.join(SC, "module2", "views.json")))
REPORT = []


def say(msg=""):
    print(msg, flush=True)
    REPORT.append(msg)


# ---------------------------------------------------------------- rendering and logs
def parse_log(path):
    info = {}
    with open(path) as f:
        for line in f:
            for key, name in (("render (s):", "render"), ("parse+load (s):", "parse"), ("camera rays:", "camera"),
                              ("secondary rays:", "secondary"), ("shadow rays:", "shadow"),
                              ("ray-primitive tests:", "tests")):
                if line.startswith(key):
                    info[name] = float(line.split(":", 1)[1])
            if line.startswith("rays by depth:"):
                info["depth"] = {int(a): int(b) for a, b in (t.split(":") for t in line.split(":", 1)[1].split())}
            if line.startswith("OK: errors:") or line.startswith("FAILED"):
                parts = line.replace(",", "").split()
                info["errors"] = int(parts[parts.index("errors:") + 1]) if "errors:" in parts else 1
                info["warnings"] = int(parts[parts.index("warnings:") + 1]) if "warnings:" in parts else 0
    info["rays"] = info.get("camera", 0) + info.get("secondary", 0) + info.get("shadow", 0)
    return info


def render(scene, outdir=OUT, out=None, opts=()):
    """Renders scenes/<scene>; returns (path of the .pfm without extension, log info)."""
    os.makedirs(outdir, exist_ok=True)
    stem = out or os.path.splitext(os.path.basename(scene))[0]
    cmd = [RENDERER, os.path.join(SC, scene), "--quiet", "--outdir", outdir, "--out", stem] + list(opts)
    r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    base = os.path.join(outdir, stem)
    info = parse_log(base + ".log")
    if r.returncode != 0 or info.get("errors", 1):
        raise RuntimeError("render failed: %s\n%s" % (" ".join(cmd), r.stderr))
    return base, info


def remove(base):
    for ext in (".png", ".pfm", ".log"):
        if os.path.exists(base + ext):
            os.remove(base + ext)


# ---------------------------------------------------------------- images
def load_pfm(path):
    """(w, h, [r, g, b, r, g, b, ...]) with row 0 at the top."""
    with open(path, "rb") as f:
        kind = f.readline().strip()
        w, h = map(int, f.readline().split())
        scale = float(f.readline())
        data = f.read()
    n = 3 if kind == b"PF" else 1
    vals = struct.unpack(("<" if scale < 0 else ">") + "%df" % (w * h * n), data[:4 * w * h * n])
    rows = [vals[(h - 1 - y) * w * n:(h - y) * w * n] for y in range(h)]
    flat = [v for row in rows for v in row]
    if n == 1:
        flat = [v for v in flat for _ in range(3)]
    return w, h, flat


def luminance(rgb):
    r, g, b = rgb[0::3], rgb[1::3], rgb[2::3]
    return [0.2126 * x + 0.7152 * y + 0.0722 * z for x, y, z in zip(r, g, b)]


def srgb(v):
    v = 0.0 if v <= 0 else (1.0 if v >= 1 else v)
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if len(s) % 2 else 0.5 * (s[len(s) // 2 - 1] + s[len(s) // 2])


def rmse(a, b, idx=None):
    if idx is None:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in idx) / len(idx)) if idx else float("nan")


# ---------------------------------------------------------------- cameras (same conventions as the renderer)
def _sub(a, b): return [a[i] - b[i] for i in range(3)]
def _dot(a, b): return sum(a[i] * b[i] for i in range(3))
def _cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _norm(a):
    L = math.sqrt(_dot(a, a)); return [x / L for x in a]


def cam_basis(cam):
    d = _norm(_sub(cam["look"], cam["eye"]))
    right = _norm(_cross(_norm(cam.get("up", (0, 1, 0))), d))
    return right, _cross(d, right), d


def screen_window(cam, W, H):
    if "window" in cam:
        return cam["window"]
    a = W / H
    return (-a, a, -1, 1) if a > 1 else (-1, 1, -1 / a, 1 / a)


def to_camera(cam, p):
    right, up, d = cam_basis(cam)
    v = _sub(p, cam["eye"])
    return _dot(v, right), _dot(v, up), _dot(v, d)


def project(cam, p, W, H):
    """World point -> raster (x, y) (continuous; pixel centres at +0.5)."""
    xc, yc, zc = to_camera(cam, p)
    x0, x1, y0, y1 = screen_window(cam, W, H)
    if cam["type"] == "orthographic":
        sx, sy = xc, yc
    else:
        t = math.tan(math.radians(cam["fov"]) / 2)
        sx, sy = xc / (zc * t), yc / (zc * t)
    return (sx - x0) / (x1 - x0) * W, (y1 - sy) / (y1 - y0) * H


def sphere_silhouette(cam, c, r, W, H, n=720):
    """Exact image outline of a sphere: the rim of its tangent cone (perspective) or its outline circle."""
    right, up, d = cam_basis(cam)
    pts = []
    if cam["type"] == "orthographic":
        for k in range(n):
            a = 2 * math.pi * k / n
            pts.append(project(cam, [c[i] + r * (math.cos(a) * right[i] + math.sin(a) * up[i]) for i in range(3)], W, H))
        return pts
    u = _sub(c, cam["eye"])
    dist = math.sqrt(_dot(u, u))
    u = [x / dist for x in u]
    a1 = _norm(_cross(u, up if abs(_dot(u, up)) < 0.9 else right))
    a2 = _cross(u, a1)
    alpha = math.asin(r / dist)
    for k in range(n):
        ph = 2 * math.pi * k / n
        dirv = [math.cos(alpha) * u[i] + math.sin(alpha) * (math.cos(ph) * a1[i] + math.sin(ph) * a2[i]) for i in range(3)]
        pts.append(project(cam, [cam["eye"][i] + dist * dirv[i] for i in range(3)], W, H))
    return pts


def extents(points, centre, W, H):
    """Extent of a point set along the radial direction (from the image centre) and across it."""
    cx, cy = centre
    rx, ry = cx - W / 2, cy - H / 2
    L = math.hypot(rx, ry)
    rx, ry = (rx / L, ry / L) if L > 1e-6 else (1.0, 0.0)
    tx, ty = -ry, rx
    pr = [(x - cx) * rx + (y - cy) * ry for x, y in points]
    pt = [(x - cx) * tx + (y - cy) * ty for x, y in points]
    return max(pr) - min(pr), max(pt) - min(pt)


def region_mask(w, h, rgb, seed, tol=0.07, keep=None):
    """4-connected pixels around seed with nearly the seed's chromaticity (shading-independent).
    keep(x, y), if given, limits the region (e.g. to the neighbourhood of a predicted outline)."""
    def chroma(i):
        r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
        s = r + g + b
        return (r / s, g / s) if s > 1e-6 else (0.0, 0.0)
    sx, sy = int(seed[0]), int(seed[1])
    c0 = chroma(sy * w + sx)
    seen, stack, out = {sy * w + sx}, [sy * w + sx], []
    while stack:
        i = stack.pop()
        out.append(i)
        x, y = i % w, i // w
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if j not in seen and (keep is None or keep(nx + 0.5, ny + 0.5)):
                    seen.add(j)
                    c = chroma(j)
                    if abs(c[0] - c0[0]) < tol and abs(c[1] - c0[1]) < tol and sum(rgb[3 * j:3 * j + 3]) > 0.01:
                        stack.append(j)
    return out


def components(w, h, flags, min_size=20):
    """4-connected components of the pixels where flags[i] is true."""
    seen = bytearray(w * h)
    comps = []
    for start in range(w * h):
        if not flags[start] or seen[start]:
            continue
        seen[start] = 1
        stack, comp = [start], []
        while stack:
            i = stack.pop()
            comp.append(i)
            x, y = i % w, i // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if flags[j] and not seen[j]:
                        seen[j] = 1
                        stack.append(j)
        if len(comp) >= min_size:
            comps.append(comp)
    return comps


def write_csv(name, header, rows):
    os.makedirs(M2OUT, exist_ok=True)
    with open(os.path.join(M2OUT, name), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        for r in rows:
            wr.writerow([("%.6g" % v) if isinstance(v, float) else v for v in r])
    say("  -> output/module2/%s" % name)


# ================================================================ 2.2.1 camera models
def camera_study():
    say("== 2.2.1 camera models")
    for name in ("camera_ortho", "camera_persp", "camera_fov1", "camera_fov2", "camera_fov3"):
        render(name + ".pbrt")
    for name in ("camera_ortho_as_persp", "camera_persp_as_ortho", "camera_fov1_dolly", "camera_fov2_dolly",
                 "camera_fov3_dolly"):
        render("module2/camera/%s.pbrt" % name, os.path.join(M2OUT, "camera"))
    rows = []

    # (a) identical houses: roof sizes in the orthographic and the perspective view
    say("  roof sizes of the 16 identical houses (connected red-roof regions, pixels):")
    for name, base in (("camera_ortho", OUT), ("camera_ortho_as_persp", os.path.join(M2OUT, "camera"))):
        w, h, rgb = load_pfm(os.path.join(base, name + ".pfm"))
        flags = [rgb[3 * i] > 0.05 and rgb[3 * i] > 2.2 * rgb[3 * i + 1] and rgb[3 * i] > 2.2 * rgb[3 * i + 2]
                 for i in range(w * h)]
        comps = [c for c in components(w, h, flags, 50)]
        areas = [len(c) for c in comps]
        widths = [max(i % w for i in c) - min(i % w for i in c) + 1 for c in comps]
        say("    %-22s %2d roofs  area %6.0f +- %5.0f px (min %d, max %d)  width %5.1f +- %4.1f px (min %d, max %d)" % (
            name, len(comps), mean(areas), math.sqrt(mean([(a - mean(areas)) ** 2 for a in areas])), min(areas), max(areas),
            mean(widths), math.sqrt(mean([(a - mean(widths)) ** 2 for a in widths])), min(widths), max(widths)))
        rows.append([name, "roof_area_px", len(comps), mean(areas), min(areas), max(areas)])
        rows.append([name, "roof_width_px", len(comps), mean(widths), min(widths), max(widths)])

    # (b) poles of the railway: predicted image heights (exact projection)
    cam_p = VIEWS["camera_persp"]["camera"]
    cam_o = VIEWS["camera_persp_as_ortho"]["camera"]
    W, H = VIEWS["camera_persp"]["res"]
    say("  telegraph pole (height 5.2) image heights, exact projection:  z: perspective px / orthographic px")
    line = []
    for z in (0, 10, 20, 40, 80):
        hp = project(cam_p, (-3.2, 0, z), W, H)[1] - project(cam_p, (-3.2, 5.2, z), W, H)[1]
        ho = project(cam_o, (-3.2, 0, z), W, H)[1] - project(cam_o, (-3.2, 5.2, z), W, H)[1]
        dist = to_camera(cam_p, (-3.2, 2.6, z))[2]
        line.append("%d: %.0f / %.0f" % (z, hp, ho))
        rows.append(["camera_persp", "pole_height_px_z%d" % z, dist, hp, ho, ""])
    say("    " + "   ".join(line))

    # (c) field of view: apparent size of the reference sphere, and stretching near the image edge
    say("  field of view: red reference sphere (r 0.5 at (0, 0.5, 4)), measured vs exact projection (px)")
    say("    %-18s %5s %9s %9s %10s %8s %14s" % ("image", "fov", "diam meas", "diam pred", "tan(fov/2)", "f_px",
                                                  "diam*tan(fov/2)"))
    red = VIEWS["camera_fov1"]["callouts"][0][1]
    for name in ("camera_fov1", "camera_fov2", "camera_fov3", "camera_fov1_dolly", "camera_fov2_dolly", "camera_fov3_dolly"):
        base = OUT if "dolly" not in name else os.path.join(M2OUT, "camera")
        v = VIEWS[name]
        cam, (W, H) = v["camera"], v["res"]
        w, h, rgb = load_pfm(os.path.join(base, name + ".pfm"))
        c = project(cam, red, W, H)
        pts = sphere_silhouette(cam, red, 0.5, W, H)
        mask = region_mask(w, h, rgb, c)
        mx = [(i % w + 0.5, i // w + 0.5) for i in mask]
        dmeas = max(x for x, _ in mx) - min(x for x, _ in mx) + 1
        dpred = max(x for x, _ in pts) - min(x for x, _ in pts)
        fpx = (H / 2) / math.tan(math.radians(cam["fov"] / 2))
        say("    %-18s %5.0f %9.1f %9.1f %10.3f %8.1f %14.1f" % (name, cam["fov"], dmeas, dpred, math.tan(math.radians(cam["fov"] / 2)),
                                                           fpx, dpred * math.tan(math.radians(cam["fov"] / 2))))
        rows.append([name, "ref_sphere_diameter_px", cam["fov"], dmeas, dpred, fpx])
    say("  wide-angle stretching of spheres away from the image centre (radial / tangential extent)")
    say("    %-18s %-16s %7s %7s %7s %7s" % ("image", "sphere", "angle", "meas", "pred", "1/cos"))
    for name in ("camera_fov1", "camera_fov2", "camera_fov3", "camera_fov3_dolly"):
        base = OUT if "dolly" not in name else os.path.join(M2OUT, "camera")
        v = VIEWS[name]
        cam, (W, H) = v["camera"], v["res"]
        w, h, rgb = load_pfm(os.path.join(base, name + ".pfm"))
        # spheres that no neighbour hides in any of the views (the back rows overlap in the image)
        for label, ctr in (("near-left", (-3.0, 0.5, -3.0)), ("near-right", (3.0, 0.5, -3.0)), ("reference", red)):
            xc, yc, zc = to_camera(cam, ctr)
            if zc <= 0.6:
                continue
            c = project(cam, ctr, W, H)
            if not (2 <= c[0] < W - 2 and 2 <= c[1] < H - 2):
                continue
            pts = sphere_silhouette(cam, ctr, 0.5, W, H)
            if min(x for x, _ in pts) < 0 or max(x for x, _ in pts) > W or min(y for _, y in pts) < 0 or max(y for _, y in pts) > H:
                continue  # cut by the image border
            cx, cy = mean([p[0] for p in pts]), mean([p[1] for p in pts])
            pr, pt = extents(pts, (cx, cy), W, H)
            # stay within 1.25x the predicted outline: a neighbour of similar colour can touch it in the image
            rad = 0.625 * max(pr, pt) + 2
            mask = region_mask(w, h, rgb, c, keep=lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad)
            if len(mask) < 30:
                continue
            mr, mt = extents([(i % w + 0.5, i // w + 0.5) for i in mask], (cx, cy), W, H)
            ang = math.degrees(math.acos(zc / math.sqrt(xc * xc + yc * yc + zc * zc)))
            say("    %-18s %-16s %6.1fd %7.3f %7.3f %7.3f" % (name, label, ang, (mr + 1) / (mt + 1), pr / pt, 1 / math.cos(math.radians(ang))))
            rows.append([name, "stretch_" + label, ang, (mr + 1) / (mt + 1), pr / pt, 1 / math.cos(math.radians(ang))])
    write_csv("camera.csv", ["image", "quantity", "a", "measured", "predicted_or_min", "extra"], rows)


# ================================================================ 2.2.2 antialiasing
AA_SPPS = {"WSRT": [1, 4, 9, 16, 25, 36, 64], "DRT": [1, 4, 9, 16]}


def aa_study(repeats=5):
    say("== 2.2.2 antialiasing")
    for name in ("aa_wsrt", "aa_drt", "aa_ss1", "aa_ss4", "aa_ss9", "aa_ss16"):
        render(name + ".pbrt")
    aadir = os.path.join(M2OUT, "aa")
    for name in ("aa_ss4_regular", "aa_ss4_random", "aa_ss16_regular", "aa_ss16_random", "aa_ref"):
        render("module2/aa/%s.pbrt" % name, aadir)
    W, H = VIEWS["aa_ref"]["res"]
    _, _, ref = load_pfm(os.path.join(aadir, "aa_ref.pfm"))
    ref_d = [srgb(v) for v in ref]
    cam = VIEWS["aa_ref"]["camera"]
    regions = []
    for label, anchor, hs, *_ in VIEWS["aa_ref"]["callouts"]:
        x, y = project(cam, anchor, W, H)
        r = hs * W
        idx = [3 * (yy * W + xx) + k for yy in range(max(0, int(y - r)), min(H, int(y + r))) for xx in range(max(0, int(x - r)), min(W, int(x + r)))
               for k in range(3)]
        regions.append((label, idx))

    def errors(path):
        _, _, img = load_pfm(path)
        d = [srgb(v) for v in img]
        return [rmse(d, ref_d)] + [rmse(d, ref_d, idx) for _, idx in regions]

    rows = []
    say("  display-referred (sRGB) RMSE against a 1024-spp reference (aa_ref), whole image and per callout region")
    say("    %-16s %4s  %8s  " % ("image", "spp", "all") + "  ".join("r%d" % (k + 1) for k in range(len(regions))))
    for name, spp, base in [("aa_ss1", 1, OUT), ("aa_ss4", 4, OUT), ("aa_ss9", 9, OUT), ("aa_ss16", 16, OUT),
                            ("aa_ss4_regular", 4, aadir), ("aa_ss16_regular", 16, aadir), ("aa_ss4_random", 4, aadir),
                            ("aa_ss16_random", 16, aadir)]:
        e = errors(os.path.join(base, name + ".pfm"))
        say("    %-16s %4d  %8.4f  " % (name, spp, e[0]) + "  ".join("%.3f" % x for x in e[1:]))
        rows.append(["error", name, spp] + e)
    for k, (label, _) in enumerate(regions):
        say("    r%d = %s" % (k + 1, label))

    # render time as a function of samples per pixel (median of several runs)
    tdir = os.path.join(aadir, "timing")
    say("  render time vs samples per pixel (median of %d runs; %dx%d; stratified jittered, 1 = pixel centre)" % (repeats, W, H))
    say("    %-6s %4s %10s %10s %12s %10s" % ("tracer", "spp", "time (s)", "s / spp", "rays", "RMSE"))
    fits = {}
    for tracer, scene, reps in (("WSRT", "aa_wsrt.pbrt", repeats), ("DRT", "aa_drt.pbrt", max(2, repeats // 2))):
        pts = []
        drt_ref = None
        for spp in AA_SPPS[tracer]:
            opts = ["--sampler", "independent", "--spp", "1"] if spp == 1 else ["--sampler", "stratified", "--spp", str(spp)]
            times = []
            for k in range(reps):
                base, info = render(scene, tdir, "%s_t%d" % (tracer, spp), opts + ["--seed", str(k)])
                times.append(info["render"])
            e = errors(base + ".pfm") if tracer == "WSRT" else float("nan")
            if tracer == "WSRT":
                e = e[0]
            t = median(times)
            pts.append((spp, t))
            say("    %-6s %4d %10.4f %10.5f %12d %10s" % (tracer, spp, t, t / spp, info["rays"], ("%.4f" % e) if e == e else "-"))
            rows.append(["time", tracer, spp, t, min(times), max(times), info["rays"], e])
            remove(base)
        # least-squares line t = a + b spp
        n = len(pts)
        sx, sy = sum(p[0] for p in pts), sum(p[1] for p in pts)
        sxx, sxy = sum(p[0] ** 2 for p in pts), sum(p[0] * p[1] for p in pts)
        b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        a = (sy - b * sx) / n
        fits[tracer] = (a, b)
        say("    %s fit: time = %.4f s + %.5f s x spp" % (tracer, a, b))
        rows.append(["fit", tracer, "", a, b, "", "", ""])
    write_csv("aa.csv", ["kind", "name_or_tracer", "spp", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"], rows)


# ================================================================ 2.2.3 sampler comparison
STRATS = [("uniform", "unif"), ("grid", "grid"), ("halton", "halton"), ("stratified", "strat")]
NS = [1, 4, 16, 64, 256]


def sampler_scene(tag, n):
    top = os.path.join(SC, "sampler_%s_%d.pbrt" % (tag, n))
    return ("sampler_%s_%d.pbrt" % (tag, n)) if os.path.exists(top) else ("module2/sampler/sampler_%s_%d.pbrt" % (tag, n))


def sampler_study(trials, pbrt):
    say("== 2.2.3 sampler comparison (soft shadows; one camera ray per pixel centre; direct light only)")
    sdir = os.path.join(M2OUT, "sampler")
    for _, tag in STRATS:
        for n in NS:
            scene = sampler_scene(tag, n)
            render(scene, OUT if scene.startswith("sampler_") else sdir)
    t0 = time.time()
    _, info = render("module2/sampler/sampler_ref_ours.pbrt", sdir)
    say("  reference (this renderer): 16384 stratified light samples per pixel, %.1f s" % info["render"])
    render("module2/sampler/sampler_unoccluded.pbrt", sdir)
    refdir = os.path.join(SC, "module2", "sampler", "reference")
    pbrt_pfm = os.path.join(refdir, "sampler_ref_pbrt.pfm")
    if pbrt and os.path.exists(pbrt) and not os.path.exists(pbrt_pfm):
        os.makedirs(refdir, exist_ok=True)
        t = time.time()
        r = subprocess.run([pbrt, "--outfile", pbrt_pfm, os.path.join(SC, "module2", "sampler", "sampler_ref_pbrt.pbrt")],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        with open(os.path.join(refdir, "sampler_ref_pbrt.txt"), "w") as f:
            f.write("pbrt-v4 output for sampler_ref_pbrt.pbrt (%.1f s)\n" % (time.time() - t) + r.stdout)
        say("  reference (pbrt-v4): rendered in %.1f s" % (time.time() - t))
    W, H = VIEWS["sampler_ref_ours"]["res"]
    ours = luminance(load_pfm(os.path.join(sdir, "sampler_ref_ours.pfm"))[2])
    unocc = luminance(load_pfm(os.path.join(sdir, "sampler_unoccluded.pfm"))[2])
    refs = {"ours": ours}
    if os.path.exists(pbrt_pfm):
        refs["pbrt"] = luminance(load_pfm(pbrt_pfm)[2])
    else:
        say("  (no pbrt-v4 reference: %s missing and pbrt not found)" % rel(pbrt_pfm))
    lit = [i for i in range(W * H) if unocc[i] > 1e-3]
    vis = [ours[i] / unocc[i] if unocc[i] > 1e-3 else 0.0 for i in range(W * H)]
    pen = [i for i in lit if 0.02 < vis[i] < 0.98]
    say("  pixels: %d lit floor/objects, %d in penumbrae (0.02 < visible fraction < 0.98)" % (len(lit), len(pen)))
    if "pbrt" in refs:
        p = refs["pbrt"]
        say("  reference agreement (pbrt-v4 vs this renderer): RMSE %.5f over lit pixels, mean %.5f vs %.5f (%.2f %%),"
            " penumbra RMSE %.5f" % (rmse(p, ours, lit), mean([p[i] for i in lit]), mean([ours[i] for i in lit]),
                                     100 * (mean([ours[i] for i in lit]) / mean([p[i] for i in lit]) - 1), rmse(p, ours, pen)))
    cam = VIEWS["sampler_ref_ours"]["camera"]
    regions = []
    for label, anchor, hs, *_ in VIEWS["sampler_ref_ours"]["callouts"]:
        x, y = project(cam, anchor, W, H)
        r = hs * W
        box = set(yy * W + xx for yy in range(max(0, int(y - r)), min(H, int(y + r)))
                  for xx in range(max(0, int(x - r)), min(W, int(x + r))))
        idx = [i for i in pen if i in box]
        # probe pixel: the penumbra pixel of the region whose visible fraction is closest to 1/2
        probe = min(idx, key=lambda i: abs(vis[i] - 0.5)) if idx else None
        regions.append((label, idx, probe))
    lit_probe = max(lit, key=lambda i: unocc[i] if vis[i] > 0.999 else -1)
    probes = [(lab, pr) for lab, _, pr in regions if pr is not None] + [("fully lit", lit_probe)]
    say("  probe pixels (x, y): " + "; ".join("%s (%d, %d) visible %.2f" % (lab, pr % W, pr // W, vis[pr]) for lab, pr in probes))
    with open(os.path.join(M2OUT, "sampler_probes.json"), "w") as f:
        json.dump({"probes": [[lab, pr % W, pr // W, vis[pr]] for lab, pr in probes],
                   "regions": [[lab, len(idx)] for lab, idx, _ in regions]}, f, indent=1)

    tdir = os.path.join(sdir, "trials")
    rows, prow = [], []
    say("  %d independent renders (seeds) per sampler and sample count; RMSE of the pixel values" % trials)
    say("    %-10s %5s %10s %10s %10s %10s %10s | per region (vs this renderer's reference)" % (
        "sampler", "N", "pen. RMSE", "rel. RMSE", "bias", "std dev", "vs pbrt"))
    for strat, tag in STRATS:
        for n in NS:
            scene = sampler_scene(tag, n)
            T = trials if strat != "grid" else 2  # the grid is deterministic: every seed gives the same image
            s1 = [0.0] * (W * H)
            s2 = [0.0] * (W * H)
            times = []
            for t in range(T):
                base, info = render(scene, tdir, "trial", ["--seed", str(1000 + t)])
                times.append(info["render"])
                v = luminance(load_pfm(base + ".pfm")[2])
                s1 = [a + b for a, b in zip(s1, v)]
                s2 = [a + b * b for a, b in zip(s2, v)]
                remove(base)
            m = [a / T for a in s1]
            var = [max(0.0, b / T - a * a) * T / max(1, T - 1) for a, b in zip(m, s2)]
            res = {}
            for key, ref in refs.items():
                # mean squared error of one render = bias^2 + variance (per pixel)
                mse = [(m[i] - ref[i]) ** 2 + var[i] * (T - 1) / T for i in range(W * H)]
                res[key] = mse
            pen_rmse = math.sqrt(mean([res["ours"][i] for i in pen]))
            # squared bias = (mean of the T renders - reference)^2 minus the variance of that mean
            bias = math.sqrt(max(0.0, mean([(m[i] - ours[i]) ** 2 - var[i] / T for i in pen])))
            std = math.sqrt(mean([var[i] for i in pen]))
            rel_rmse = pen_rmse / mean([ours[i] for i in pen])
            vs_pbrt = math.sqrt(mean([res["pbrt"][i] for i in pen])) if "pbrt" in res else float("nan")
            reg = [math.sqrt(mean([res["ours"][i] for i in idx])) if idx else float("nan") for _, idx, _ in regions]
            say("    %-10s %5d %10.5f %10.4f %10.5f %10.5f %10.5f | %s" % (
                strat, n, pen_rmse, rel_rmse, bias, std, vs_pbrt, " ".join("%.4f" % x for x in reg)))
            rows.append([strat, n, T, median(times), pen_rmse, rel_rmse, bias, std, vs_pbrt] + reg)
            for lab, pr in probes:
                prow.append([strat, n, T, lab, pr % W, pr // W, ours[pr], m[pr], math.sqrt(var[pr]), math.sqrt(res["ours"][pr]),
                             math.sqrt(res["pbrt"][pr]) if "pbrt" in res else float("nan")])
    say("    regions: " + "; ".join("%d %s (%d px)" % (k + 1, lab, len(idx)) for k, (lab, idx, _) in enumerate(regions)))
    write_csv("sampler.csv", ["sampler", "N", "trials", "time_s", "penumbra_rmse", "penumbra_rel_rmse", "bias", "std",
                              "penumbra_rmse_vs_pbrt"] + ["region%d_rmse" % (k + 1) for k in range(len(regions))], rows)
    write_csv("sampler_probes.csv", ["sampler", "N", "trials", "probe", "x", "y", "reference", "mean", "std", "rmse",
                                     "rmse_vs_pbrt"], prow)
    shutil.rmtree(tdir, ignore_errors=True)
    say("  sampler study took %.0f s" % (time.time() - t0))


def rel(p):
    return os.path.relpath(p, ROOT)


# ================================================================ 2.2.4 DRT parameter study
def param_study():
    say("== 2.2.4 DRT parameter study (BF = branching factor, MD = maximum depth)")
    pdir = os.path.join(M2OUT, "param")
    for name in sorted(VIEWS["_params"]):
        _, info = render(name + ".pbrt")
        p = VIEWS["_params"][name]
        say("  %-17s BF %2d MD %2d spp %2d: %8.1f s, %d rays, rays by depth %s" % (
            name, p["bf"], p["md"], p["spp"], info["render"], info["rays"],
            " ".join("%d:%d" % kv for kv in sorted(info.get("depth", {}).items()))))
    rows = []
    for out, sw in sorted(VIEWS["_sweeps"].items()):
        world = sw["world"]
        _, rinfo = render("module2/param/%s.pbrt" % sw["refname"], pdir)
        ref = luminance(load_pfm(os.path.join(pdir, sw["refname"] + ".pfm"))[2])
        rmean = mean(ref)
        say("  %s (%s, %dx%d, %d spp): reference %s (BF %d, MD %d, %d spp) %.1f s, mean %.5f" % (
            out, world, sw["res"][0], sw["res"][1], sw["spp"], sw["refname"], sw["ref"][0], sw["ref"][1], sw["ref"][2],
            rinfo["render"], rmean))
        say("    %4s %4s %9s %13s %10s %10s %10s %12s" % ("BF", "MD", "time (s)", "rays", "mean/ref", "noise", "rel RMSE",
                                                          "1/(err^2 t)"))
        chosen = VIEWS["_params"][out]
        for name in sw["files"]:
            v = VIEWS[name]
            base, info = render("module2/param/%s.pbrt" % name, pdir)
            a = luminance(load_pfm(base + ".pfm")[2])
            b2, _ = render("module2/param/%s.pbrt" % name, pdir, name + "_s2", ["--seed", "7"])
            b = luminance(load_pfm(b2 + ".pfm")[2])
            remove(b2)
            noise = math.sqrt(mean([(x - y) ** 2 for x, y in zip(a, b)]) / 2) / rmean
            err = rmse(a, ref) / rmean
            eff = 1 / (err * err * info["render"]) if err > 0 and info["render"] > 0 else float("nan")
            say("    %4d %4d %9.2f %13d %10.4f %10.4f %10.4f %12.1f" % (v["bf"], v["md"], info["render"], info["rays"],
                                                                     mean(a) / rmean, noise, err, eff))
            rows.append([out, world, v["bf"], v["md"], sw["spp"], info["render"], info["rays"], mean(a) / rmean, noise, err, eff,
                         " ".join("%d:%d" % kv for kv in sorted(info.get("depth", {}).items()))])
        # equal-time comparison: BF 1 with more samples per pixel, as long as the chosen setting
        bf, md = chosen["bf"], chosen["md"]
        if bf == 1:
            say("    equal time: the chosen setting already has BF 1 (nothing to compare)")
            continue
        base_c, ic = render("module2/param/%s_ref.pbrt" % world, pdir, "chosen",
                            ["--spp", str(sw["spp"]), "--bf", str(bf), "--maxdepth", str(md)])
        ac = luminance(load_pfm(base_c + ".pfm")[2])
        base_1, i1 = render("module2/param/%s_ref.pbrt" % world, pdir, "bf1",
                            ["--spp", str(sw["spp"]), "--bf", "1", "--maxdepth", str(md)])
        spp_eq = max(1, int(round(sw["spp"] * ic["render"] / max(1e-6, i1["render"]))))
        base_e, ie = render("module2/param/%s_ref.pbrt" % world, pdir, "equal",
                            ["--spp", str(spp_eq), "--bf", "1", "--maxdepth", str(md)])
        # the first estimate comes from a very short render: rescale once by the measured time ratio
        if abs(ie["render"] / ic["render"] - 1) > 0.1:
            spp_eq = max(1, int(round(spp_eq * ic["render"] / ie["render"])))
            base_e, ie = render("module2/param/%s_ref.pbrt" % world, pdir, "equal",
                                ["--spp", str(spp_eq), "--bf", "1", "--maxdepth", str(md)])
        ae = luminance(load_pfm(base_e + ".pfm")[2])
        say("    equal time: BF %d x %d spp: %.2f s, rel RMSE %.4f   vs   BF 1 x %d spp: %.2f s, rel RMSE %.4f" % (
            bf, sw["spp"], ic["render"], rmse(ac, ref) / rmean, spp_eq, ie["render"], rmse(ae, ref) / rmean))
        rows.append([out, world, "equal_time_bf%d" % bf, md, sw["spp"], ic["render"], ic["rays"], mean(ac) / rmean, "",
                     rmse(ac, ref) / rmean, "", ""])
        rows.append([out, world, "equal_time_bf1", md, spp_eq, ie["render"], ie["rays"], mean(ae) / rmean, "",
                     rmse(ae, ref) / rmean, "", ""])
        for bse in ("chosen", "bf1", "equal"):
            remove(os.path.join(pdir, bse))
    write_csv("param.csv", ["output", "world", "bf", "md", "spp", "time_s", "rays", "mean_over_ref", "rel_noise",
                            "rel_rmse", "efficiency", "rays_by_depth"], rows)


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="camera,aa,sampler,param")
    ap.add_argument("--trials", type=int, default=24, help="renders per sampler setting (sampler study)")
    ap.add_argument("--repeats", type=int, default=5, help="timing repetitions (antialiasing study)")
    ap.add_argument("--pbrt", default=os.path.expanduser("~/pbrt-v4/build/pbrt"))
    args = ap.parse_args()
    if not os.path.exists(RENDERER):
        sys.exit("build the renderer first: make -C source")
    which = args.only.split(",")
    t = time.time()
    os.makedirs(M2OUT, exist_ok=True)
    for study, fn in (("camera", camera_study), ("aa", lambda: aa_study(args.repeats)),
                      ("sampler", lambda: sampler_study(args.trials, args.pbrt)), ("param", param_study)):
        if study in which:
            start = len(REPORT)
            fn()
            with open(os.path.join(M2OUT, "section_%s.log" % study), "w") as f:
                f.write("\n".join(REPORT[start:]) + "\n")
    say("total %.0f s" % (time.time() - t))
    # module2.log: the latest section of every study (a partial run replaces only its own sections)
    sections = []
    for study in ("camera", "aa", "sampler", "param"):
        path = os.path.join(M2OUT, "section_%s.log" % study)
        if os.path.exists(path):
            sections.append(open(path).read())
    with open(os.path.join(M2OUT, "module2.log"), "w") as f:
        f.write("".join(sections))
    print("summary: output/module2/module2.log")


if __name__ == "__main__":
    main()

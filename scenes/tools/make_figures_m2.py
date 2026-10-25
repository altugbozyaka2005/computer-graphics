#!/usr/bin/env python3
"""Figures for the Module 2 report (Python 3 standard library only).

Reads the images rendered by module2_study.py (output/, output/module2/) and its measurements
(output/module2/*.csv) and writes output/figures/module2/:

  <image>_annotated.png / _insets.png / _legend.txt  numbered callouts on every required image
  camera_ortho_vs_persp.png, camera_fov.png          projections side by side, measured sizes
  aa_zoom.png, aa_patterns.png                       enlarged regions per sample count / pattern
  aa_time.png, aa_error.png                          render time and error against spp
  sampler_crops_<N>.png, sampler_error_<N>.png       penumbrae per sampler, |error| maps
  sampler_rmse.png, sampler_rmse_regions.png         RMSE against N (log-log)
  param_<scene>_sweep.png                            MD and BF sweeps, one tone mapping per scene
  param_md.png, param_bf.png, param_cost.png         energy against MD, noise against BF, rays per depth

  python3 scenes/tools/make_figures_m2.py
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures as mf  # noqa: E402  (drawing, fonts, PNG I/O, title bars, inset sheets)
import module2_study as st  # noqa: E402  (cameras, projection, PFM loading)

OUT, M2OUT = st.OUT, st.M2OUT
FIG = os.path.join(OUT, "figures", "module2")
VIEWS = st.VIEWS

# Categorical slots 1-4 of the reference palette (validated: scripts/validate_palette.js, light mode);
# every series also has its own marker shape and a direct label, so identity never rests on colour.
SERIES = [(42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0)]
MARKERS = ["circle", "square", "triangle", "diamond"]
INK, INK2, MUTED, GRID, SURFACE = (11, 11, 11), (82, 81, 78), (150, 149, 144), (228, 227, 222), (252, 252, 251)
YELLOW = (255, 214, 0)


def csv_rows(name):
    path = os.path.join(M2OUT, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ---------------------------------------------------------------- drawing helpers
def fill_poly(img, pts, col):
    w, h, d = img
    ys = [p[1] for p in pts]
    for y in range(max(0, int(min(ys))), min(h, int(max(ys)) + 1)):
        yc = y + 0.5
        xs = []
        for i in range(len(pts)):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            for x in range(max(0, int(round(a))), min(w, int(round(b)))):
                i = (y * w + x) * 3
                d[i:i + 3] = bytes(col)


def marker(img, x, y, kind, col, r=5.5):
    ring = r + 2  # 2px surface ring around every marker
    if kind == "circle":
        mf.draw_disc(img, x, y, ring, SURFACE)
        mf.draw_disc(img, x, y, r, col)
    elif kind == "square":
        fill_poly(img, [(x - ring, y - ring), (x + ring, y - ring), (x + ring, y + ring), (x - ring, y + ring)], SURFACE)
        fill_poly(img, [(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r)], col)
    elif kind == "triangle":
        k = 1.25
        fill_poly(img, [(x, y - ring * k), (x + ring * k, y + ring * 0.8), (x - ring * k, y + ring * 0.8)], SURFACE)
        fill_poly(img, [(x, y - r * k), (x + r * k, y + r * 0.8), (x - r * k, y + r * 0.8)], col)
    else:
        k = 1.3
        fill_poly(img, [(x, y - ring * k), (x + ring * k, y), (x, y + ring * k), (x - ring * k, y)], SURFACE)
        fill_poly(img, [(x, y - r * k), (x + r * k, y), (x, y + r * k), (x - r * k, y)], col)


def dashed(img, ax, ay, bx, by, col, width, dash=8, gap=6):
    L = math.hypot(bx - ax, by - ay)
    if L == 0:
        return
    t = 0.0
    while t < L:
        t1 = min(L, t + dash)
        mf.draw_line(img, ax + (bx - ax) * t / L, ay + (by - ay) * t / L, ax + (bx - ax) * t1 / L, ay + (by - ay) * t1 / L,
                     col, width)
        t = t1 + gap


def nice_ticks(lo, hi, n=5):
    span = hi - lo
    if span <= 0:
        return [lo]
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9 * span:
        out.append(round(t, 12))
        t += step
    return out


def fmt_tick(v):
    if v == 0:
        return "0"
    if abs(v) >= 1000 or abs(v) < 0.01:
        e = int(math.floor(math.log10(abs(v)) + 1e-9))
        m = v / 10 ** e
        return ("1e%d" % e) if abs(m - 1) < 1e-9 else ("%ge%d" % (round(m, 2), e))
    return ("%g" % round(v, 4))


def plot(series, title, xlabel, ylabel, xlog=False, ylog=False, size=(860, 520), guides=(), ylim=None, xlim=None,
         hline=None):
    """Line chart. series: [(label, [(x, y), ...])] in fixed palette order; guides: dashed reference lines
    [(label, [(x, y), ...])]; hline: (y, label) horizontal reference."""
    W, H = size
    img = mf.new_image(W, H, SURFACE)
    tp, lp = 20, 15
    lh = mf.line_height(tp)
    mf.draw_text(img, 18, 12, title, tp, INK, bold=True)
    # legend row under the title (a legend is always present for >= 2 series)
    lx, ly = 18, 14 + lh + 4
    if len(series) > 1:
        for k, (lab, _) in enumerate(series):
            marker(img, lx + 7, ly + 9, MARKERS[k % 4], SERIES[k % 4])
            lx += 20 + mf.draw_text(img, lx + 18, ly, lab, lp, INK2) + 22
    L, R, T, B = 86, 150, ly + 56, 64
    pw, ph = W - L - R, H - T - B
    pts = [p for _, ps in series for p in ps] + [p for _, ps in guides for p in ps]
    pts = [p for p in pts if p[0] == p[0] and p[1] == p[1] and (not xlog or p[0] > 0) and (not ylog or p[1] > 0)]
    tx = (lambda v: math.log10(v)) if xlog else (lambda v: v)
    ty = (lambda v: math.log10(v)) if ylog else (lambda v: v)
    x0, x1 = xlim if xlim else (min(tx(p[0]) for p in pts), max(tx(p[0]) for p in pts))
    y0, y1 = ylim if ylim else (min(ty(p[1]) for p in pts), max(ty(p[1]) for p in pts))
    if hline:
        y0, y1 = min(y0, ty(hline[0])), max(y1, ty(hline[0]))
    if xlim is None:
        pad = 0.04 * (x1 - x0 or 1)
        x0, x1 = x0 - pad, x1 + pad
    if ylim is None:
        pad = 0.08 * (y1 - y0 or 1)
        y0, y1 = y0 - pad, y1 + pad
        if not ylog and y0 > 0 and y0 < 0.25 * y1:
            y0 = 0.0
    X = lambda v: L + (tx(v) - x0) / (x1 - x0) * pw
    Y = lambda v: T + ph - (ty(v) - y0) / (y1 - y0) * ph
    # grid and ticks (recessive)
    def ticks(lo, hi, log):
        if log:
            out = []
            for e in range(int(math.floor(lo)), int(math.ceil(hi)) + 1):
                for m in (1, 2, 5):
                    v = m * 10 ** e
                    if lo - 1e-9 <= math.log10(v) <= hi + 1e-9:
                        out.append((v, m == 1))
            return out
        return [(v, True) for v in nice_ticks(lo, hi)]
    short_x, short_y = (x1 - x0) < 1.3, (y1 - y0) < 1.3  # log axes spanning about a decade: label 2 and 5 too
    for v, major in ticks(x0, x1, xlog):
        x = X(v)
        mf.draw_line(img, x, T, x, T + ph, GRID if major else (240, 239, 236), 1)
        if major or not xlog or short_x:
            s = fmt_tick(v)
            mf.draw_text(img, x - mf.text_width(s, 14) / 2, T + ph + 6, s, 14, INK2)
    for v, major in ticks(y0, y1, ylog):
        y = Y(v)
        mf.draw_line(img, L, y, L + pw, y, GRID if major else (240, 239, 236), 1)
        if major or not ylog or short_y:
            s = fmt_tick(v)
            mf.draw_text(img, L - 8 - mf.text_width(s, 14), y - 9, s, 14, INK2)
    mf.draw_line(img, L, T + ph, L + pw, T + ph, INK2, 1.5)
    mf.draw_line(img, L, T, L, T + ph, INK2, 1.5)
    mf.draw_text(img, L + pw / 2 - mf.text_width(xlabel, 15) / 2, H - 30, xlabel, 15, INK2)
    mf.draw_text(img, 12, T - 26, ylabel, 15, INK2)
    if hline:
        y = Y(hline[0])
        dashed(img, L, y, L + pw, y, MUTED, 1.5)
        mf.draw_text(img, L + pw + 8, y - 9, hline[1], 14, INK2)
    for lab, ps in guides:
        ps = [p for p in ps if (not xlog or p[0] > 0) and (not ylog or p[1] > 0)]
        for a, b in zip(ps, ps[1:]):
            dashed(img, X(a[0]), Y(a[1]), X(b[0]), Y(b[1]), MUTED, 1.5)
        if len(ps) >= 2:
            # label below the middle of the guide (the line ends carry the series labels)
            a, b = ps[0], ps[-1]
            mx, my = (X(a[0]) + X(b[0])) / 2, (Y(a[1]) + Y(b[1])) / 2
            mf.draw_text(img, mx + 4, my + 6, lab, 14, MUTED)
    labels = []
    for k, (lab, ps) in enumerate(series):
        col = SERIES[k % 4]
        ps = [p for p in ps if p[1] == p[1] and (not xlog or p[0] > 0) and (not ylog or p[1] > 0)]
        for a, b in zip(ps, ps[1:]):
            mf.draw_line(img, X(a[0]), Y(a[1]), X(b[0]), Y(b[1]), col, 2)
        for p in ps:
            marker(img, X(p[0]), Y(p[1]), MARKERS[k % 4], col)
        if ps and len(series) > 1:  # a single series is named by the title
            labels.append([Y(ps[-1][1]), X(ps[-1][0]), lab])
    # direct labels at the line ends, nudged apart
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 18)
    for y, x, lab in labels:
        mf.draw_text(img, x + 12, y - 9, lab, 14, INK)
    return img


def hstack(imgs, gap=16, bg=(255, 255, 255)):
    w = sum(i[0] for i in imgs) + gap * (len(imgs) - 1)
    h = max(i[1] for i in imgs)
    out = mf.new_image(w, h, bg)
    x = 0
    for i in imgs:
        mf.paste(out, i, x, 0)
        x += i[0] + gap
    return out


def vstack(imgs, gap=16, bg=(255, 255, 255)):
    w = max(i[0] for i in imgs)
    h = sum(i[1] for i in imgs) + gap * (len(imgs) - 1)
    out = mf.new_image(w, h, bg)
    y = 0
    for i in imgs:
        mf.paste(out, i, 0, y)
        y += i[1] + gap
    return out


def captioned(img, text, sub=None, px=18):
    """An image with a short caption bar above it (bold title line, optional grey second line)."""
    lh = mf.line_height(px)
    h = 8 + lh + (mf.line_height(px - 3) if sub else 0) + 6
    out = mf.new_image(img[0], img[1] + h, (255, 255, 255))
    mf.draw_text(out, 6, 6, text, px, INK, bold=True)
    if sub:
        mf.draw_text(out, 6, 6 + lh, sub, px - 3, INK2)
    mf.paste(out, img, 0, h)
    return out


def frame(img, box, col=YELLOW, lw=3):
    x0, y0, x1, y1 = box
    mf.draw_rect(img, x0, y0, x1, y1, (0, 0, 0), lw + 2)
    mf.draw_rect(img, x0, y0, x1, y1, col, lw)


def load_png(path):
    return mf.load_png(path) if os.path.exists(path) else None


def save(img, name):
    os.makedirs(FIG, exist_ok=True)
    mf.save_png(os.path.join(FIG, name), img)
    print("wrote output/figures/module2/%s" % name)


# ---------------------------------------------------------------- callouts on an image
def callout_boxes(name, W, H):
    v = VIEWS[name]
    out = []
    for c in v["callouts"]:
        label, anchor, hs = c[0], c[1], c[2]
        px, py = st.project(v["camera"], anchor, W, H)
        r = hs * W
        # badge direction from the box: given per callout, otherwise away from the image centre
        d = tuple(c[3]) if len(c) > 3 else (1 if px < W * 0.55 else -1, -1 if py > H * 0.35 else 1)
        out.append((label, (px, py), (int(px - r), int(py - r), int(px + r), int(py + r)), d))
    return out


def annotate(name, base_dir, title):
    img = load_png(os.path.join(base_dir, name + ".png"))
    if img is None:
        print("skip %s (not rendered)" % name)
        return
    W, H = img[0], img[1]
    ann = [W, H, bytearray(img[2])]
    lw = max(2.0, W / 400)
    rad = max(14, W / 48)
    tiles, keys, legend = [], [], []
    boxes = callout_boxes(name, W, H)
    for n, (label, (px, py), (x0, y0, x1, y1), (dx, dy)) in enumerate(boxes, 1):
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            print("  warning: %s callout %d (%s) is outside the image" % (name, n, label))
            continue
        frame(ann, (x0, y0, x1, y1), YELLOW, lw)
        r = (x1 - x0) / 2
        bx = min(W - rad - 4, max(rad + 4, px + dx * (r + 2.6 * rad)))
        by = min(H - rad - 4, max(rad + 4, py + dy * (r + 2.6 * rad)))
        # arrow to the nearest point of the frame (a corner, or an edge midpoint when straight)
        cx = px if dx == 0 else (x0 if bx < px else x1)
        cy = py if dy == 0 else (y0 if by < py else y1)
        mf.draw_arrow(ann, bx, by, cx, cy, (0, 0, 0), lw + 2)
        mf.draw_arrow(ann, bx, by, cx, cy, YELLOW, lw)
        mf.badge(ann, bx, by, rad, n)
        z = max(1, round(300 / max(1, x1 - x0)))
        tiles.append((n, label, z, mf.crop_scaled(img, x0, y0, x1, y1, z)))
        keys.append((n, label))
        legend.append("%d  %s" % (n, label))
    info = mf._render_info(base_dir, name)
    save(mf._labelled(ann, title, info, keys) if keys else captioned(ann, title, info), name + "_annotated.png")
    if tiles:
        save(mf._inset_sheet(tiles, rad), name + "_insets.png")
        with open(os.path.join(FIG, name + "_legend.txt"), "w") as f:
            f.write("%s: numbered regions in %s_annotated.png and %s_insets.png\n" % (name, name, name) + "\n".join(legend) + "\n")


# ================================================================ camera
def camera_figures():
    annotate("camera_ortho", OUT, "camera_ortho: orthographic (isometric) view")
    annotate("camera_persp", OUT, "camera_persp: perspective view, fov 45°")
    for name, fov in (("camera_fov1", 25), ("camera_fov2", 60), ("camera_fov3", 100)):
        annotate(name, OUT, "%s: field of view %d° (vertical)" % (name, fov))
    rows = csv_rows("camera.csv") or []
    roof = {(r["image"], r["quantity"]): r for r in rows}
    cdir = os.path.join(M2OUT, "camera")
    panels = []
    for name, base, title in (("camera_ortho", OUT, "orthographic (camera_ortho)"),
                              ("camera_ortho_as_persp", cdir, "perspective, same direction")):
        img = load_png(os.path.join(base, name + ".png"))
        if img is None:
            return
        r = roof.get((name, "roof_area_px"))
        sub = ("16 identical roofs: area %.0f px (min %s, max %s)" % (fnum(r["measured"]), r["predicted_or_min"], r["extra"])
               if r else None)
        panels.append(captioned(img, title, sub))
    top = hstack(panels)
    panels = []
    for name, base, title in (("camera_persp", OUT, "perspective (camera_persp)"),
                              ("camera_persp_as_ortho", cdir, "orthographic, same position and direction")):
        img = load_png(os.path.join(base, name + ".png"))
        if img is None:
            return
        cam = VIEWS[name]["camera"]
        W, H = img[0], img[1]
        ann = [W, H, bytearray(img[2])]
        heights = []
        for z in (0, 20, 40):
            a, b = st.project(cam, (-3.2, 0, z), W, H), st.project(cam, (-3.2, 5.2, z), W, H)
            if 0 <= a[0] < W and 0 <= b[1] < H:
                frame(ann, (int(b[0] - 10), int(b[1] - 4), int(a[0] + 10), int(min(H - 1, a[1]))), YELLOW, 2)
                heights.append("z=%d: %.0f px" % (z, a[1] - b[1]))
        panels.append(captioned(ann, title, "telegraph pole heights (exact projection) " + ", ".join(heights)))
    save(vstack([top, hstack(panels)]), "camera_ortho_vs_persp.png")

    # field of view: fixed camera (top) and dolly zoom (bottom), reference sphere framed
    meas = {r["image"]: r for r in rows if r["quantity"] == "ref_sphere_diameter_px"}
    stretch = {(r["image"], r["quantity"]): r for r in rows if r["quantity"].startswith("stretch_")}
    lines = []
    for suffix, base in (("", OUT), ("_dolly", cdir)):
        panels = []
        for name, fov in (("camera_fov1", 25), ("camera_fov2", 60), ("camera_fov3", 100)):
            n = name + suffix
            img = load_png(os.path.join(base, n + ".png"))
            if img is None:
                return
            W, H = img[0], img[1]
            ann = [W, H, bytearray(img[2])]
            cam = VIEWS[n]["camera"]
            pts = st.sphere_silhouette(cam, VIEWS["camera_fov1"]["callouts"][0][1], 0.5, W, H)
            frame(ann, (int(min(p[0] for p in pts)) - 3, int(min(p[1] for p in pts)) - 3, int(max(p[0] for p in pts)) + 3,
                        int(max(p[1] for p in pts)) + 3), YELLOW, 3)
            for side in ("near-left", "near-right"):
                s = stretch.get((n, "stretch_" + side))
                if s:
                    ctr = (-3.0 if side == "near-left" else 3.0, 0.5, -3.0)
                    sp = st.sphere_silhouette(cam, ctr, 0.5, W, H)
                    frame(ann, (int(min(p[0] for p in sp)) - 3, int(min(p[1] for p in sp)) - 3,
                                int(max(p[0] for p in sp)) + 3, int(max(p[1] for p in sp)) + 3), (90, 200, 255), 3)
            m = meas.get(n)
            st_l = stretch.get((n, "stretch_near-left"))
            sub = "red sphere %s px wide (predicted %.1f)" % (m["measured"], fnum(m["predicted_or_min"])) if m else ""
            if st_l:
                sub += "; blue: stretched %.2fx at %.0f°" % (fnum(st_l["measured"]), fnum(st_l["a"]))
            dist = math.dist(cam["eye"], VIEWS["camera_fov1"]["callouts"][0][1])
            panels.append(mf.resize_box(captioned(ann, "fov %d°, camera %.1f from the sphere" % (fov, dist), sub, 22),
                                        W * 2 // 3, (H + 64) * 2 // 3))
        lines.append(hstack(panels))
    save(vstack([captioned(lines[0], "fixed camera position: only the field of view changes"),
                 captioned(lines[1], "dolly zoom: the camera moves so that the red sphere keeps its size")]), "camera_fov.png")


# ================================================================ antialiasing
def aa_figures():
    annotate("aa_wsrt", OUT, "aa_wsrt: Whitted, 1 ray per pixel centre")
    annotate("aa_drt", OUT, "aa_drt: distributed, 1 camera ray per pixel centre, BF 32")
    for n in (1, 4, 9, 16):
        annotate("aa_ss%d" % n, OUT, "aa_ss%d: %d sample%s per pixel" % (n, n, "s" if n > 1 else ""))
    rows = csv_rows("aa.csv") or []
    err = {r["name_or_tracer"]: r for r in rows if r["kind"] == "error"}
    tm = {(r["name_or_tracer"], int(r["spp"])): r for r in rows if r["kind"] == "time"}
    aadir = os.path.join(M2OUT, "aa")
    cols = [("aa_ss1", OUT, "1 spp (centre)"), ("aa_ss4", OUT, "4 spp"), ("aa_ss9", OUT, "9 spp"), ("aa_ss16", OUT, "16 spp"),
            ("aa_ref", aadir, "1024 spp (reference)")]

    def grid(columns, regions, zoom, fname):
        imgs = [load_png(os.path.join(b, n + ".png")) for n, b, _ in columns]
        if any(i is None for i in imgs):
            return
        W, H = imgs[0][0], imgs[0][1]
        boxes = callout_boxes("aa_ss1", W, H)
        rowsimg = []
        header = []
        for (n, b, lab) in columns:
            e = err.get(n)
            t = tm.get(("WSRT", int(n.replace("aa_ss", "").split("_")[0]))) if n.startswith("aa_ss") else None
            sub = ("RMSE %.4f" % fnum(e["v1"]) if e else "") + ("  %.3f s" % fnum(t["v1"]) if t else "")
            header.append((lab, sub))
        for k in regions:
            label, _, (x0, y0, x1, y1), _ = boxes[k]
            tiles = [mf.crop_scaled(i, x0, y0, x1, y1, zoom) for i in imgs]
            rowsimg.append(captioned(hstack(tiles, 8), "%d  %s" % (k + 1, label), px=17))
        tw = rowsimg[0][0]
        top = mf.new_image(tw, 50, (255, 255, 255))
        cw = (tw - 8 * (len(columns) - 1)) / len(columns)
        for c, (lab, sub) in enumerate(header):
            mf.draw_text(top, c * (cw + 8) + 4, 2, lab, 17, INK, bold=True)
            mf.draw_text(top, c * (cw + 8) + 4, 25, sub, 15, INK2)
        save(vstack([top] + rowsimg, 10), fname)
    grid(cols, [0, 1, 2, 3, 4], 3, "aa_zoom.png")
    cols2 = [("aa_ss4_regular", aadir, "4: regular grid"), ("aa_ss4", OUT, "4: jittered"), ("aa_ss4_random", aadir, "4: random"),
             ("aa_ss16_regular", aadir, "16: regular grid"), ("aa_ss16", OUT, "16: jittered"), ("aa_ss16_random", aadir, "16: random")]
    grid(cols2, [0, 1, 3], 3, "aa_patterns.png")
    if tm:
        charts = []
        for tracer in ("WSRT", "DRT"):
            pts = sorted((s, fnum(r["v1"])) for (t, s), r in tm.items() if t == tracer)
            fit = [r for r in rows if r["kind"] == "fit" and r["name_or_tracer"] == tracer]
            guides = []
            if fit:
                a, b = fnum(fit[0]["v1"]), fnum(fit[0]["v2"])
                smax = max(p[0] for p in pts)
                guides = [("fit %.3g + %.3g spp" % (a, b), [(1, a + b), (smax, a + smax * b)])]
            charts.append(plot([(tracer, pts)], "%s render time against samples per pixel" % tracer, "samples per pixel",
                               "render time (s)", guides=guides, size=(760, 480)))
        save(hstack(charts), "aa_time.png")
        # time rows: v1 median time, v2 min, v3 max, v4 rays, v5 RMSE against the reference
        jit = sorted((s, fnum(r["v5"])) for (t, s), r in tm.items() if t == "WSRT" and fnum(r["v5"]) == fnum(r["v5"]))
        ser = [("jittered", jit)]
        for kind in ("regular", "random"):
            ps = [(s, fnum(err["aa_ss%d_%s" % (s, kind)]["v1"])) for s in (4, 16) if "aa_ss%d_%s" % (s, kind) in err]
            ser.append((kind, ps))
        if jit:
            g0 = jit[1][1] if len(jit) > 1 else jit[0][1]
            guides = [("N^-1/2", [(4, g0), (64, g0 / 4)]), ("N^-3/4", [(4, g0 * 0.85), (64, g0 * 0.85 / 8)])]
            save(plot(ser, "WSRT error against samples per pixel (sRGB RMSE vs 1024 spp)", "samples per pixel", "RMSE",
                      xlog=True, ylog=True, guides=guides), "aa_error.png")


# ================================================================ sampler comparison
SAMPLERS = [("uniform", "unif"), ("grid", "grid"), ("halton", "halton"), ("stratified", "strat")]


def sampler_figures():
    for tag, title in (("unif", "uniform random"), ("grid", "regular grid"), ("halton", "Halton")):
        for n in (4, 16, 64):
            annotate("sampler_%s_%d" % (tag, n), OUT, "sampler_%s_%d: %s light samples, N = %d" % (tag, n, title, n))
    sdir = os.path.join(M2OUT, "sampler")
    ref = load_png(os.path.join(sdir, "sampler_ref_ours.png"))
    if ref is None:
        return
    W, H = ref[0], ref[1]
    boxes = callout_boxes("sampler_ref_ours", W, H)
    refpf = st.load_pfm(os.path.join(sdir, "sampler_ref_ours.pfm"))[2]
    for n in (4, 16, 64):
        paths = [(lab, st.sampler_scene(tag, n)) for lab, tag in SAMPLERS]
        imgs = []
        for lab, scene in paths:
            base = OUT if scene.startswith("sampler_") else sdir
            imgs.append((lab, os.path.join(base, os.path.splitext(os.path.basename(scene))[0])))
        loaded = [(lab, load_png(p + ".png"), p) for lab, p in imgs]
        if any(i is None for _, i, _ in loaded):
            continue
        rowsimg = []
        for k, (label, _, (x0, y0, x1, y1), _) in enumerate(boxes):
            tiles = [mf.crop_scaled(i, x0, y0, x1, y1, 3) for _, i, _ in loaded] + [mf.crop_scaled(ref, x0, y0, x1, y1, 3)]
            rowsimg.append(captioned(hstack(tiles, 8), "%d  %s" % (k + 1, label), px=17))
        tw = rowsimg[0][0]
        top = mf.new_image(tw, 30, (255, 255, 255))
        cw = (tw - 8 * 4) / 5
        for c, lab in enumerate([l for l, _, _ in loaded] + ["reference (16384)"]):
            mf.draw_text(top, c * (cw + 8) + 4, 4, lab + ("" if c == 4 else ", N = %d" % n), 17, INK, bold=True)
        save(vstack([top] + rowsimg, 10), "sampler_crops_%d.png" % n)
        # |error| maps against the reference (sequential single-hue ramp, light = small error)
        maps = []
        scale = 0.08
        for lab, _, p in loaded:
            img = st.load_pfm(p + ".pfm")[2]
            e = [abs(a - b) for a, b in zip(st.luminance(img), st.luminance(refpf))]
            out = mf.new_image(W, H)
            d = out[2]
            for i, v in enumerate(e):
                t = min(1.0, v / scale)
                c = (int(252 + (13 - 252) * t), int(252 + (43 - 252) * t), int(251 + (92 - 251) * t))
                d[3 * i:3 * i + 3] = bytes(c)
            maps.append(captioned(mf.resize_box(out, W // 2, H // 2), lab, "N = %d" % n, 17))
        bar = mf.new_image(W // 2, 40, (255, 255, 255))
        for x in range(W // 2 - 20):
            t = x / (W // 2 - 20)
            mf.draw_line(bar, 10 + x, 6, 10 + x, 22, (int(252 - 239 * t), int(252 - 209 * t), int(251 - 159 * t)), 1.2)
        mf.draw_text(bar, 10, 22, "|error| 0", 14, INK2)
        mf.draw_text(bar, W // 2 - 10 - mf.text_width(">= %.2f" % scale, 14), 22, ">= %.2f" % scale, 14, INK2)
        save(vstack([hstack(maps[:2]), hstack(maps[2:]), bar], 8), "sampler_error_%d.png" % n)
    rows = csv_rows("sampler.csv")
    if not rows:
        return
    ser = []
    for lab, _ in SAMPLERS:
        ser.append((lab, [(int(r["N"]), fnum(r["penumbra_rmse"])) for r in rows if r["sampler"] == lab]))
    u = [p for p in ser[0][1]]
    g0 = u[0][1]
    guides = [("N^-1/2", [(1, g0), (256, g0 / 16)]), ("N^-3/4", [(1, g0 * 0.7), (256, g0 * 0.7 / 64)])]
    save(plot(ser, "Penumbra RMSE against light samples N", "light samples per shading point (N)",
              "RMSE (penumbra pixels)", xlog=True, ylog=True, guides=guides), "sampler_rmse.png")
    probes_regions = [b[0] for b in boxes]
    charts = []
    for k, lab in enumerate(probes_regions):
        s2 = [(sl, [(int(r["N"]), fnum(r["region%d_rmse" % (k + 1)])) for r in rows if r["sampler"] == sl]) for sl, _ in SAMPLERS]
        charts.append(plot(s2, "%d  %s" % (k + 1, lab), "N", "RMSE", xlog=True, ylog=True, size=(620, 430)))
    save(vstack([hstack(charts[:3]), hstack(charts[3:])]), "sampler_rmse_regions.png")


# ================================================================ parameter study
def param_figures():
    titles = {"param_small_low": "small BF, low MD", "param_small_high": "small BF, high MD",
              "param_large_low": "large BF, low MD", "param_large_high": "large BF, high MD"}
    for name, p in sorted(VIEWS["_params"].items()):
        annotate(name, OUT, "%s: BF %d, MD %d (%s)" % (name, p["bf"], p["md"], titles[name]))
    rows = csv_rows("param.csv") or []
    pdir = os.path.join(M2OUT, "param")
    for out, sw in sorted(VIEWS["_sweeps"].items()):
        world = sw["world"]
        refp = os.path.join(pdir, sw["refname"] + ".pfm")
        if not os.path.exists(refp):
            continue
        ref = st.load_pfm(refp)
        _, _, white = mf.tonemap(ref, "reinhard", "luminance", 1.0, 0)
        white = sorted(st.luminance(ref[2]))[int(0.999 * ref[0] * ref[1])] or white  # 99.9th percentile
        data = {(int(r["bf"]), int(r["md"])): r for r in rows if r["output"] == out and r["bf"].isdigit()}

        def tile(name, label):
            path = os.path.join(pdir, name + ".pfm")
            if not os.path.exists(path):
                return None
            img, _, _ = mf.tonemap(st.load_pfm(path), "reinhard", "luminance", 1.0, white)
            return captioned(img, label[0], label[1], 16)
        md_tiles = []
        for m in sw["md"]:
            r = data.get((sw["md_bf"], m))
            t = tile("%s_bf%d_md%d" % (world, sw["md_bf"], m),
                     ("MD %d" % m, "%.1f s, energy %.3f" % (fnum(r["time_s"]), fnum(r["mean_over_ref"])) if r else ""))
            if t:
                md_tiles.append(t)
        bf_tiles = []
        for b in sw["bf"]:
            r = data.get((b, sw["bf_md"]))
            t = tile("%s_bf%d_md%d" % (world, b, sw["bf_md"]),
                     ("BF %d" % b, "%.1f s, noise %.1f %%" % (fnum(r["time_s"]), 100 * fnum(r["rel_noise"])) if r else ""))
            if t:
                bf_tiles.append(t)
        reft = tile(sw["refname"], ("reference", "BF %d, MD %d, %d spp" % tuple(sw["ref"])))
        per_row = 5
        md_rows = [hstack(md_tiles[i:i + per_row], 8) for i in range(0, len(md_tiles), per_row)]
        parts = [captioned(r, "MD sweep at BF %d (%d spp)" % (sw["md_bf"], sw["spp"]) if i == 0 else "")
                 for i, r in enumerate(md_rows)]
        parts.append(captioned(hstack(bf_tiles + [reft], 8), "BF sweep at MD %d (%d spp), and the reference" % (sw["bf_md"], sw["spp"])))
        save(vstack(parts, 14), "%s_sweep.png" % out)
    if not rows:
        return
    outs = sorted(VIEWS["_sweeps"])
    charts = []
    for out in outs:
        sw = VIEWS["_sweeps"][out]
        pts = sorted((int(r["md"]), fnum(r["mean_over_ref"])) for r in rows
                     if r["output"] == out and r["bf"].isdigit() and int(r["bf"]) == sw["md_bf"] and int(r["md"]) in sw["md"])
        charts.append(plot([("BF %d" % sw["md_bf"], pts)], "%s: energy against MD" % out, "maximum depth MD",
                           "mean / reference", size=(640, 420), hline=(1.0, "reference")))
    save(vstack([hstack(charts[:2]), hstack(charts[2:])]), "param_md.png")
    charts = []
    for out in outs:
        sw = VIEWS["_sweeps"][out]
        pts = sorted((int(r["bf"]), fnum(r["rel_noise"])) for r in rows
                     if r["output"] == out and r["bf"].isdigit() and int(r["md"]) == sw["bf_md"] and int(r["bf"]) in sw["bf"])
        guides = [("BF^-1/2", [(pts[0][0], pts[0][1]), (pts[-1][0], pts[0][1] * math.sqrt(pts[0][0] / pts[-1][0]))])] if pts else []
        charts.append(plot([("MD %d" % sw["bf_md"], pts)], "%s: noise against BF" % out, "branching factor BF",
                           "relative noise", xlog=True, ylog=True, size=(640, 420), guides=guides))
    save(vstack([hstack(charts[:2]), hstack(charts[2:])]), "param_bf.png")
    # rays per depth: exponential growth BF^d against linear growth for BF = 1
    ser = []
    sw = VIEWS["_sweeps"]["param_large_high"]
    for b in [v for v in sw["bf"] if v in (1, 2, 4, 6)]:  # four series: the validated palette slots
        r = [x for x in rows if x["output"] == "param_large_high" and x["bf"] == str(b) and int(x["md"]) == sw["bf_md"]]
        if r:
            d = dict(tuple(map(int, t.split(":"))) for t in r[0]["rays_by_depth"].split())
            cam = d.get(0, 1)
            ser.append(("BF %d" % b, [(k, v / cam) for k, v in sorted(d.items())]))
    if ser:
        save(plot(ser, "param_large_high: rays traced at each depth, per camera ray", "depth d", "rays per camera ray",
                  ylog=True), "param_cost.png")


def main():
    camera_figures()
    aa_figures()
    sampler_figures()
    param_figures()


if __name__ == "__main__":
    main()

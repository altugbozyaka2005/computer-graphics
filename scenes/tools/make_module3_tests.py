#!/usr/bin/env python3
"""Builds the Module 3 student test suite in studentTests/ (Python 3 standard library only).

For every test N it writes studentTests/testN/:
  testscene_N.pbrt        the test scene in the course's pbrt subset (Integrator "distributed")
  testscene_N_pbrt.pbrt   the same scene for pbrt-v4 (only the Integrator/Sampler/Film lines differ)
  testsuite_ref_N.pfm     reference image rendered by pbrt-v4 (or analytic, test 9), linear HDR
  testsuite_ref_N.png     the reference for viewing (clamped, sRGB)
  testsuite_ref_N.log     pbrt-v4's console output for that scene (for error tests: pbrt-v4's message)
  example_testsuite_my_N.log   the log CGR26_renderer writes for the scene (what a passing log looks like)
  test.json               category, metric, pixels / markers / keywords, thresholds
  run.sh                  runs just this test: ../runAllTests.py --tests N

Tests 1-5 camera and intersections (glowing objects of equal luminance on black: coverage, framing),
6-9 shading (pbrt "diffuse" = Phong diffuse term vs pbrt-v4; Phong lobes vs the closed form),
10-21 error handling (one deliberate error each, grouped: syntax, structure, unknown, files,
transform, range).

  python3 scenes/tools/make_module3_tests.py [--pbrt ~/pbrt-v4/build/pbrt] [--renderer output/CGR26_renderer]
                                             [--only 3,7] [--no-render]

pbrt-v4 has no Phong BRDF; its "diffuse" material is the Phong BRDF's diffuse term (kd / pi), which is
what the shading tests compare. Test 9 checks the specular lobes against the analytic Phong value.
"""
import argparse
import colorsys
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ST = os.path.join(ROOT, "studentTests")
sys.path.insert(0, HERE)
sys.path.insert(0, ST)
import runAllTests as rt  # noqa: E402  (image I/O, centroids)
from validate_module1 import Camera, add, mul, norm, sub, dot  # noqa: E402  (pbrt LookAt + perspective)
from make_poolroom import fmt, box  # noqa: E402

def v3(p):
    return " ".join(fmt(c) for c in p)


def tri_mesh(P, I):
    return ('Shape "trianglemesh" "point3 P" [ ' + "  ".join(v3(p) for p in P) + ' ]\n    "integer indices" [ ' +
            " ".join(str(i) for i in I) + " ]\n")


# ================================================================ test definitions
TESTS = {}


def test(n, **kw):
    TESTS[n] = dict(n=n, **kw)


# ---------------------------------------------------------------- geometry helpers
def quad(a, b, c, d, uv=None):
    s = 'Shape "trianglemesh" "point3 P" [ %s  %s  %s  %s ]\n' % (v3(a), v3(b), v3(c), v3(d))
    if uv:
        s += '    "point2 uv" [ %s ]\n' % "  ".join("%s %s" % (fmt(u), fmt(w)) for u, w in uv)
    return s + '    "integer indices" [ 0 1 2 0 2 3 ]\n'


def lathe(profile, nseg=40, normals=False, crease=35.0):
    """Surface of revolution about +y: profile = [(radius, y), ...] from bottom to top; a radius of 0 is
    a pole. Each profile segment is a separate band; with normals, per-vertex normals are averaged across
    a profile corner only if it is smoother than `crease` degrees (sharp corners stay sharp)."""
    segn = []
    for (r0, y0), (r1, y1) in zip(profile, profile[1:]):
        l = math.hypot(r1 - r0, y1 - y0) or 1.0
        segn.append(((y1 - y0) / l, -(r1 - r0) / l))
    cc = math.cos(math.radians(crease))

    def vnormal(j, s):  # normal at profile point j as used by segment s
        o = s - 1 if j == s else s + 1  # the other segment sharing point j
        if 0 <= o < len(segn) and segn[o][0] * segn[s][0] + segn[o][1] * segn[s][1] > cc:
            nr, ny = segn[o][0] + segn[s][0], segn[o][1] + segn[s][1]
            l = math.hypot(nr, ny)
            return nr / l, ny / l
        return segn[s]

    P, N, I = [], [], []
    for s_ in range(len(segn)):
        (r0, y0), (r1, y1) = profile[s_], profile[s_ + 1]
        if r0 < 1e-9 and r1 < 1e-9:
            continue
        rows = []
        for j, (r, y) in ((s_, profile[s_]), (s_ + 1, profile[s_ + 1])):
            nr, ny = vnormal(j, s_)
            row = []
            for k in range(nseg):
                ph = 2 * math.pi * (k + (0.5 if r < 1e-9 else 0.0)) / nseg  # a pole gets one vertex per wedge
                c, sn = math.cos(ph), math.sin(ph)
                row.append(len(P))
                P.append((r * c, y, r * sn))
                N.append((nr * c, ny, nr * sn))
            rows.append(row)
        A, B = rows
        for k in range(nseg):
            k1 = (k + 1) % nseg
            if r0 < 1e-9:
                I += [A[k], B[k1], B[k]]
            elif r1 < 1e-9:
                I += [A[k], A[k1], B[k]]
            else:
                I += [A[k], A[k1], B[k1], A[k], B[k1], B[k]]
    s = 'Shape "trianglemesh" "point3 P" [ ' + "  ".join(v3(p) for p in P) + ' ]\n'
    if normals:
        s += '    "normal N" [ ' + "  ".join(v3(n) for n in N) + ' ]\n'
    return s + '    "integer indices" [ ' + " ".join(str(i) for i in I) + " ]\n"


def icosahedron(r):
    g = (1 + math.sqrt(5)) / 2
    V = [(-1, g, 0), (1, g, 0), (-1, -g, 0), (1, -g, 0), (0, -1, g), (0, 1, g), (0, -1, -g), (0, 1, -g),
         (g, 0, -1), (g, 0, 1), (-g, 0, -1), (-g, 0, 1)]
    s = r / math.sqrt(1 + g * g)
    V = [(x * s, y * s, z * s) for x, y, z in V]
    F = [0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7, 1, 8,
         3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9, 8, 1]
    return tri_mesh(V, F)


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def glow(h, s=0.55, Y=0.62):
    """An emitter colour of hue h and saturation s with luminance Y: every glowing object has the same
    luminance, so a pixel's luminance is still the fraction of it covered (the coverage metric)."""
    c = colorsys.hsv_to_rgb(h % 1.0, s, 1.0)
    k = Y / lum(c)
    return tuple(round(k * v, 4) for v in c)


GOLD, CYAN, ROSE, LIME, VIOLET, AMBER, ICE, WHITE = (glow(0.11), glow(0.52), glow(0.93), glow(0.27), glow(0.75),
                                                    glow(0.07, 0.7), glow(0.58, 0.25), glow(0.0, 0.0))


def emitter(shape_lines, transform="", col=None):
    c = col or WHITE
    return ("AttributeBegin\n" + transform +
            'AreaLightSource "diffuse" "rgb L" [ %s ] "bool twosided" true\n' % v3(c) +
            'Material "diffuse" "rgb reflectance" [ 0 0 0 ]\n' + shape_lines + "AttributeEnd\n")


def occluder(shape_lines, transform=""):
    """A black, non-emitting object: it only hides what is behind it."""
    return ("AttributeBegin\n" + transform + 'Material "diffuse" "rgb reflectance" [ 0 0 0 ]\n' + shape_lines +
            "AttributeEnd\n")


def rng(seed):
    state = [seed * 2654435761 % 2 ** 32 or 1]

    def r():
        state[0] = (1103515245 * state[0] + 12345) % 2 ** 31
        return state[0] / 2 ** 31
    return r


# ---------------------------------------------------------------- camera and intersections
# Objects are glowing two-sided emitters of equal luminance on black: a pixel's luminance is the fraction
# of it covered, so silhouettes can be compared at sub-pixel level independently of shading.
def scene_orrery():
    w = []
    # ringed planet: full sphere + annulus (disk with innerradius) tilted towards the camera
    w.append(emitter('Shape "sphere" "float radius" [ 0.72 ]\n', "Translate -1.85 0.95 0.6\n", GOLD))
    w.append(emitter('Shape "disk" "float radius" [ 1.38 ] "float innerradius" [ 0.98 ]\n',
                     "Translate -1.85 0.95 0.6\nRotate 18 0 0 1\nRotate 70 1 0 0\n", ICE))
    # a moon on the ring plane
    w.append(emitter('Shape "sphere" "float radius" [ 0.16 ]\n', "Translate -0.55 1.55 0.4\n", ICE))
    # an open lantern: sphere clipped by zmin, zmax and phimax
    w.append(emitter('Shape "sphere" "float radius" [ 0.72 ] "float zmin" [ -0.45 ] "float zmax" [ 0.58 ] '
                     '"float phimax" [ 250 ]\n', "Translate 0.55 0.95 0\nRotate 35 0 1 0\nRotate -65 1 0 0\n", ROSE))
    # a gem: icosahedron (20-triangle mesh) under two rotations
    w.append(emitter(icosahedron(0.68), "Translate 2.35 1.05 0.3\nRotate 25 0 1 0\nRotate 31 1 0 0\n", LIME))
    # a disk raised along its axis by "height"
    w.append(emitter('Shape "disk" "float radius" [ 0.5 ] "float height" [ 0.45 ]\n',
                     "Translate 2.1 -1.05 0\nRotate 30 0 1 0\nRotate -20 1 0 0\n", AMBER))
    # a comet: sphere head and a thin triangle tail
    w.append(emitter('Shape "sphere" "float radius" [ 0.22 ]\n', "Translate -0.35 -1.05 0\n", CYAN))
    w.append(emitter(tri_mesh([(-0.45, -0.92, 0.05), (-0.45, -1.2, -0.05), (-3.0, -0.25, 0.4)], [0, 1, 2]), "", CYAN))
    # a kite: a non-planar two-triangle quad
    w.append(emitter(tri_mesh([(0.55, -2.3, 0.4), (1.05, -1.55, -0.1), (0.75, -0.55, 0.2), (0.3, -1.4, 0.0)],
                              [0, 1, 2, 0, 2, 3]), "", VIOLET))
    # stars: spheres only a few pixels across
    r = rng(7)
    placed = 0
    while placed < 16:
        x, y = -3.4 + 6.8 * r(), -2.5 + 5.0 * r()
        if (abs(x + 1.85) < 1.6 and abs(y - 0.95) < 1.0) or (abs(x - 0.55) < 0.9 and abs(y - 0.95) < 0.9) or \
                (abs(x - 2.35) < 0.8 and abs(y - 1.05) < 0.8) or (abs(x - 2.1) < 0.7 and abs(y + 1.05) < 0.7) or \
                (-3.1 < x < 0.0 and -1.4 < y < -0.1) or (0.2 < x < 1.2 and -2.4 < y < -0.4) or abs(x) > 3.3:
            continue
        w.append(emitter('Shape "sphere" "float radius" [ %s ]\n' % fmt(0.025 + 0.035 * r()),
                         "Translate %s %s 1.2\n" % (fmt(x), fmt(y)), WHITE))
        placed += 1
    return "".join(w)


test(1, name="Orrery: sphere, clipped sphere, annulus, raised disk, triangles, icosahedron, tiny spheres",
     category="camera", metric="coverage",
     description="A ringed planet (sphere + tilted annulus), an open lantern (sphere clipped by zmin, zmax and "
                 "phimax), a disk raised by 'height', a 20-triangle gem, a comet (sphere + thin triangle), a "
                 "non-planar kite and stars only a few pixels wide. Checks every primitive's intersection and the "
                 "perspective camera at sub-pixel level.",
     camera=("LookAt 0 0 -6.5  0 0 0  0 1 0", 'Camera "perspective" "float fov" [ 45 ]'), res=(384, 288),
     my_spp=(8, 8), ref_spp=(32, 32), maxdepth=1, world=scene_orrery,
     thresholds=dict(max_mismatch=0.0005, max_offset=0.1))


def scene_clockwork():
    w = []
    # flower: ten petals made from one sphere under a non-uniform Scale, a Translate and a Rotate
    w.append("AttributeBegin\nTranslate -1.75 0.75 0.5\n")
    for k in range(10):
        w.append("AttributeBegin\nRotate %d 0 0 1\nScale 1 0.24 0.24\nTranslate 1 0 0\n" % (k * 36) +
                 'AreaLightSource "diffuse" "rgb L" [ %s ] "bool twosided" true\n' % v3(ROSE if k % 2 else VIOLET) +
                 'Material "diffuse" "rgb reflectance" [ 0 0 0 ]\nShape "sphere" "float radius" [ 0.55 ]\n'
                 'AttributeEnd\n')
    w.append(emitter('Shape "sphere" "float radius" [ 0.24 ]\n', "Translate 0 0 -0.2\n", GOLD))
    w.append("AttributeEnd\n")
    # star polygon placed by an explicit ConcatTransform matrix (pbrt's column-major order)
    pts_, idx = [(0, 0, 0)], []
    for k in range(10):
        rr = 0.85 if k % 2 == 0 else 0.36
        a = math.pi / 2 + k * math.pi / 5
        pts_.append((rr * math.cos(a), rr * math.sin(a), 0))
    for k in range(10):
        idx += [0, 1 + k, 1 + (k + 1) % 10]
    c, s = math.cos(math.radians(25)), math.sin(math.radians(25))
    m = [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 1.75, 1.15, 0.3, 1]
    w.append(emitter(tri_mesh(pts_, idx), "ConcatTransform [ " + " ".join(fmt(v) for v in m) + " ]\n", GOLD))
    # pennant and its mirror image (Scale -1 1 1): an asymmetric shape shows a wrong reflection
    pennant = (box((-0.03, 0, -0.03), (0.03, 1.1, 0.03)) +
               tri_mesh([(0.03, 1.1, 0), (0.03, 0.72, 0), (0.62, 0.98, 0.1)], [0, 1, 2]))
    w.append(emitter(pennant, "Translate -2.55 -2.15 0.2\nRotate -8 0 0 1\n", LIME))
    w.append(emitter(pennant, "Translate -1.05 -2.15 0.2\nScale -1 1 1\nRotate -8 0 0 1\n", LIME))
    # spiral staircase: each step adds Rotate + Translate to the running transform (composition order),
    # then CoordinateSystem names the top and CoordSysTransform puts a finial there
    w.append("AttributeBegin\nTranslate -0.1 -2.35 1.0\n")
    w.append(emitter(box((-0.05, 0, -0.05), (0.05, 2.0, 0.05)), "", ICE))
    for k in range(15):
        w.append("Rotate 24 0 1 0\nTranslate 0 0.125 0\n")
        w.append(emitter(box((0.06, 0, -0.07), (0.62, 0.035, 0.07)), "", CYAN if k % 2 else ICE))
    w.append("Translate 0.34 0.12 0\nCoordinateSystem \"stairtop\"\nAttributeEnd\n")
    w.append(emitter('Shape "sphere" "float radius" [ 0.09 ]\n', 'CoordSysTransform "stairtop"\n', AMBER))
    # ring of cubes in a frame set by an absolute Transform (tilted and stretched), nested Rotate/Translate
    c2, s2 = math.cos(math.radians(-25)), math.sin(math.radians(-25))
    T = [1.1, 0, 0, 0, 0, c2, s2, 0, 0, -s2, c2, 0, 1.95, -1.45, 0.4, 1]
    w.append("AttributeBegin\nTransform [ " + " ".join(fmt(v) for v in T) + " ]\n")
    for k in range(12):
        a = 360.0 * k / 12
        w.append("AttributeBegin\nRotate %s 0 1 0\nTranslate 1.0 0 0\nRotate %d 1 1 0\n" % (fmt(a), 20 * k) +
                 emitter(box((-0.11, -0.11, -0.11), (0.11, 0.11, 0.11)), "", AMBER if k % 3 else GOLD) +
                 "AttributeEnd\n")
    w.append("AttributeEnd\n")
    return "".join(w)


test(2, name="Clockwork: Scale/Rotate petals, ConcatTransform, Transform, mirror Scale, CoordSysTransform",
     category="camera", metric="coverage",
     description="Petals from a sphere under non-uniform Scale and Rotate, a star placed by ConcatTransform, a "
                 "pennant and its mirror image (Scale -1 1 1), a spiral staircase built by accumulating Rotate + "
                 "Translate with its top named by CoordinateSystem and reused by CoordSysTransform, and a ring of "
                 "cubes in a frame set by an absolute Transform. Checks the whole transform stack.",
     camera=("LookAt 0 0 -6  0 0 0  0 1 0", 'Camera "perspective" "float fov" [ 45 ]'), res=(384, 288),
     my_spp=(8, 8), ref_spp=(32, 32), maxdepth=1, world=scene_clockwork,
     thresholds=dict(max_mismatch=0.0005, max_offset=0.1))


def framing_markers(cam, depth, radius, fracs_x, fracs_y):
    """Small spheres whose centres project to the given fractions of the image."""
    out, marks = [], []
    cols = (ROSE, GOLD, CYAN)
    for j, fy in enumerate(fracs_y):
        for i, fx in enumerate(fracs_x):
            o, d = cam.ray(fx * cam.xres, fy * cam.yres)
            t = depth / dot(d, cam.dir)
            p = add(o, mul(d, t))
            out.append(emitter('Shape "sphere" "float radius" [ %s ]\n' % fmt(radius), "Translate %s\n" % v3(p), cols[j]))
            px, py, _ = cam.project(p)
            marks.append({"label": "(%.2f,%.2f)" % (fx, fy), "x": round(px, 3), "y": round(py, 3)})
    return "".join(out), marks


def framing_test(n, res, fov, radius, name, description):
    cam = Camera((0, 0, 0), (0, 0, 1), (0, 1, 0), fov, res[0], res[1])
    camline = 'Camera "perspective" "float fov" [ %s ]' % fmt(fov)
    world, marks = framing_markers(cam, 10.0, radius, (0.05, 0.5, 0.95), (0.06, 0.5, 0.94))
    test(n, name=name, category="camera", metric="centroids", description=description,
         camera=("LookAt 0 0 0  0 0 1  0 1 0", camline), res=res,
         my_spp=(8, 8), ref_spp=(32, 32), maxdepth=1, world=lambda: world, markers=marks,
         radius=max(3, int(math.ceil(2.5 * radius / cam.units_per_pixel_at(10.0)))),
         thresholds=dict(max_centroid_error=0.2))


framing_test(3, (240, 120), 30, 0.09, "Field of view, landscape 2:1 (fov on the shorter axis)",
             "Nine small spheres placed at 5%/50%/95% of the width and 6%/50%/94% of the height for fov 30 on a "
             "landscape image. pbrt applies fov to the shorter (vertical) axis; checks framing to a fraction of a pixel.")
framing_test(4, (120, 240), 60, 0.2, "Field of view, portrait 1:2 (fov on the horizontal axis)",
             "As test 3 for a portrait image with fov 60, where the shorter axis, and so the fov, is horizontal.")


def scene_avenue():
    w = []
    for side in (-1, 1):  # lamp posts receding to z = 60
        for k in range(16):
            z = 2 + k * 3.8
            x = side * 2.2
            w.append(emitter(box((x - 0.05, 0, z - 0.05), (x + 0.05, 2.2, z + 0.05)) +
                             box((x - side * 0.5, 2.15, z - 0.025), (x + 0.0001 * side, 2.2, z + 0.025)), "", ICE))
            w.append(emitter('Shape "sphere" "float radius" [ 0.13 ]\n',
                             "Translate %s 1.98 %s\n" % (fmt(x - side * 0.45), fmt(z)), AMBER))
        # railing: a thin quad from z = 2 to 60
        w.append(emitter(quad((side * 2.2, 0.95, 2), (side * 2.2, 0.95, 60), (side * 2.2, 1.02, 60),
                              (side * 2.2, 1.02, 2)), "", ICE))
    # road: dashed centre line and kerb lines on the ground, receding to z = 60
    dashes = [quad((-0.05, 0, z), (0.05, 0, z), (0.05, 0, z + 1.4), (-0.05, 0, z + 1.4)) for z in [2 + 3 * k for k in range(20)]]
    w.append(emitter("".join(dashes), "", GOLD))
    for x in (-1.6, 1.6):
        w.append(emitter(quad((x - 0.04, 0, 1.0), (x + 0.04, 0, 1.0), (x + 0.04, 0, 60), (x - 0.04, 0, 60)), "", ICE))
    # overhead cables: very thin boxes across the avenue
    for k in range(0, 16, 3):
        z = 2 + k * 3.8
        w.append(emitter(box((-2.2, 2.55, z - 0.012), (2.2, 2.57, z + 0.012)), "", CYAN))
    # distant lanterns and a moon, near spheres at the border of the image
    for k in range(5):
        w.append(emitter('Shape "sphere" "float radius" [ 0.6 ]\n', "Translate %s 2.5 80\n" % fmt(-6 + 3 * k), GOLD))
    w.append(emitter('Shape "sphere" "float radius" [ 3.5 ]\n', "Translate 14 22 90\n", WHITE))
    w.append(emitter('Shape "sphere" "float radius" [ 0.35 ]\n', "Translate -1.55 0.35 0.2\n", ROSE))
    w.append(emitter('Shape "sphere" "float radius" [ 0.25 ]\n', "Translate 1.3 2.0 0.4\n", LIME))
    return "".join(w)


test(5, name="Wide angle (fov 100): lamp-lit avenue to z = 60, thin cables, distant and near spheres",
     category="camera", metric="coverage",
     description="Lamp posts, railings and cables only 0.02 units thick receding to 60 units, lanterns at 80 "
                 "units, a moon at 90 and spheres close to the lens at the image border, seen with fov 100. Checks "
                 "precision of thin and distant hits and wide-angle framing.",
     camera=("LookAt 0 1.2 -1.2  0 1.1 10  0 1 0", 'Camera "perspective" "float fov" [ 100 ]'), res=(400, 300),
     my_spp=(8, 8), ref_spp=(32, 32), maxdepth=1, world=scene_avenue,
     thresholds=dict(max_mismatch=0.0008, max_offset=0.15))


PAWN = [(0.0, 0.0), (0.3, 0.0), (0.3, 0.06), (0.24, 0.1), (0.24, 0.14), (0.14, 0.22), (0.1, 0.42), (0.17, 0.46),
        (0.17, 0.5), (0.09, 0.53), (0.14, 0.58), (0.16, 0.66), (0.13, 0.74), (0.07, 0.79), (0.0, 0.8)]


# ---------------------------------------------------------------- shading (Phong diffuse term = pbrt "diffuse")
def pts(cam, named):
    out = []
    for label, p in named:
        x, y, _ = cam.project(p)
        if not (1 <= x < cam.xres - 1 and 1 <= y < cam.yres - 1):
            print("WARNING: test pixel '%s' projects outside the image: (%.1f, %.1f)" % (label, x, y))
            x, y = min(max(x, 1), cam.xres - 2), min(max(y, 1), cam.yres - 2)
        out.append({"label": label, "x": int(x), "y": int(y)})
    return out


def lookat_line(e, l, u):
    return "LookAt %s  %s  %s" % (v3(e), v3(l), v3(u))


def diffuse(c):
    return 'Material "diffuse" "rgb reflectance" [ %s ]\n' % v3(c)


VASE = [(0.0, 0.0), (0.2, 0.0), (0.26, 0.05), (0.34, 0.25), (0.37, 0.45), (0.33, 0.65), (0.22, 0.85),
        (0.15, 1.0), (0.14, 1.12), (0.19, 1.22), (0.21, 1.26)]


def still_life():
    w = [diffuse((0.62, 0.55, 0.47)), quad((-12, 0, -12), (12, 0, -12), (12, 0, 12), (-12, 0, 12)),
         diffuse((0.32, 0.38, 0.5)), quad((-12, 0, 3.2), (12, 0, 3.2), (12, 8, 3.2), (-12, 8, 3.2))]
    # fruit bowl: lower hemisphere (zmax 0) turned so that it opens upwards; fruit inside
    w.append("AttributeBegin\n" + diffuse((0.62, 0.3, 0.18)) + "Translate -0.7 0.8 0.7\nRotate -90 1 0 0\n"
             'Shape "sphere" "float radius" [ 0.8 ] "float zmax" [ 0 ]\nAttributeEnd\n')
    for c, p, r in (((0.85, 0.42, 0.06), (-0.98, 0.58, 0.78), 0.3), ((0.6, 0.06, 0.08), (-0.45, 0.62, 0.98), 0.28),
                    ((0.35, 0.6, 0.12), (-0.66, 0.66, 0.38), 0.26), ((0.85, 0.42, 0.06), (-0.38, 0.74, 0.52), 0.18),
                    ((0.45, 0.15, 0.4), (-0.88, 0.86, 0.6), 0.16)):
        w.append("AttributeBegin\n" + diffuse(c) + "Translate %s\n" % v3(p) +
                 'Shape "sphere" "float radius" [ %s ]\nAttributeEnd\n' % fmt(r))
    # vase: smooth-shaded mesh of revolution (per-vertex normals)
    w.append("AttributeBegin\n" + diffuse((0.16, 0.48, 0.52)) + "Translate 1.05 0 1.25\nScale 1.25 1.25 1.25\n" +
             lathe(VASE, 48, normals=True) + "AttributeEnd\n")
    # two books
    w.append("AttributeBegin\n" + diffuse((0.55, 0.1, 0.1)) + "Translate 0.95 0 -0.35\nRotate 18 0 1 0\n" +
             box((-0.45, 0, -0.3), (0.45, 0.12, 0.3)) + "AttributeEnd\n")
    w.append("AttributeBegin\n" + diffuse((0.75, 0.68, 0.45)) + "Translate 0.9 0.12 -0.38\nRotate -12 0 1 0\n" +
             box((-0.36, 0, -0.25), (0.36, 0.1, 0.25)) + "AttributeEnd\n")
    return "".join(w)


SL_CAM = ((0.3, 3.1, -4.7), (0.1, 0.55, 0.8), (0, 1, 0), 38)
res_sl = (320, 240)
cam_sl = Camera(*SL_CAM, res_sl[0], res_sl[1])
test(6, name="Still life: Phong diffuse under a point light and a spotlight (direct lighting)",
     category="shading", metric="pixels",
     description="Fruit bowl (clipped sphere, seen inside and out), fruit, a smooth-shaded vase (mesh with "
                 "per-vertex normals) and books, lit by a warm point light and a cool spotlight (cone 22, falloff "
                 "8 degrees), maxdepth 1. Isolates the diffuse BRDF, cosine, 1/d^2, shadows, the spotlight cone "
                 "and its smooth falloff.",
     camera=(lookat_line(*SL_CAM[:3]), 'Camera "perspective" "float fov" [ 38 ]'), res=res_sl,
     my_spp=(8, 8), ref_spp=(64, 64), maxdepth=1,
     world=lambda: ('LightSource "point" "point3 from" [ -2.6 4.2 -2.4 ] "rgb I" [ 30 30 30 ]\n'
                    'LightSource "spot" "point3 from" [ 3.4 3.6 -0.8 ] "point3 to" [ 1.05 0.7 1.25 ] '
                    '"float coneangle" [ 22 ] "float conedeltaangle" [ 8 ] "rgb I" [ 45 45 45 ]\n' + still_life()),
     pixels=pts(cam_sl, [("orange, lit side", (-1.15, 0.72, 0.6)), ("bowl outside", (-0.7, 0.35, 0.02)),
                        ("bowl inside, far wall", (-0.25, 0.62, 1.32)),
                        ("vase, in the spotlight", (0.73, 0.55, 1.13)), ("vase, beyond the spotlight cone", (1.481, 0.95, 1.174)),
                        ("table, spotlight falloff band", (1.95, 0, 0.35)),
                        ("table, bowl shadow", (0.05, 0, 1.75)), ("book cover", (0.85, 0.22, -0.4)),
                        ("wall", (-2.8, 1.25, 3.2))]),
     window=1, thresholds=dict(max_rel_error=0.03))


IVORY, WALNUT = (0.78, 0.72, 0.6), (0.24, 0.14, 0.08)
KING = [(0.0, 0.0), (0.32, 0.0), (0.32, 0.06), (0.26, 0.1), (0.2, 0.2), (0.12, 0.6), (0.2, 0.66), (0.2, 0.7),
        (0.12, 0.74), (0.17, 0.95), (0.08, 1.0), (0.08, 1.1), (0.0, 1.1)]
ROOK = [(0.0, 0.0), (0.3, 0.0), (0.3, 0.06), (0.24, 0.1), (0.19, 0.2), (0.17, 0.55), (0.22, 0.58), (0.22, 0.72),
        (0.15, 0.72), (0.15, 0.66), (0.0, 0.66)]


def chess():
    sq = 0.5
    w = [diffuse((0.2, 0.2, 0.22)), quad((-12, -0.05, -12), (12, -0.05, -12), (12, -0.05, 12), (-12, -0.05, 12))]
    for parity, col in ((0, IVORY), (1, WALNUT)):
        P, I = [], []
        for i in range(8):
            for j in range(8):
                if (i + j) % 2 != parity:
                    continue
                x0, z0 = -2 + i * sq, -2 + j * sq
                b = len(P)
                P += [(x0, 0, z0), (x0 + sq, 0, z0), (x0 + sq, 0, z0 + sq), (x0, 0, z0 + sq)]
                I += [b, b + 1, b + 2, b, b + 2, b + 3]
        w.append("AttributeBegin\n" + diffuse(col) + tri_mesh(P, I) + "AttributeEnd\n")
    w.append("AttributeBegin\n" + diffuse((0.3, 0.2, 0.12)) + box((-2.15, -0.05, -2.15), (2.15, -0.002, 2.15)) + "AttributeEnd\n")
    pieces = [(KING, IVORY, (-0.25, 0.25)), (ROOK, WALNUT, (0.75, 1.25)), (PAWN, IVORY, (-0.75, -0.75)),
              (PAWN, WALNUT, (0.75, -0.25)), (KING, WALNUT, (1.25, 0.75)), (PAWN, IVORY, (-1.25, 1.25))]
    for prof, col, (x, z) in pieces:
        w.append("AttributeBegin\n" + diffuse(col) + "Translate %s 0 %s\nScale 1.1 1.1 1.1\n" % (fmt(x), fmt(z)) +
                 lathe(prof, 40, normals=True) + "AttributeEnd\n")
    return "".join(w)


CH_CAM = ((0.6, 3.1, -4.6), (0.2, 0.3, 0.4), (0, 1, 0), 40)
res_ch = (320, 240)
cam_ch = Camera(*CH_CAM, res_ch[0], res_ch[1])
test(7, name="Chess endgame: Phong diffuse under a rectangular and a spherical area light (soft shadows)",
     category="shading", metric="pixels",
     description="Chess pieces (smooth meshes of revolution) on a two-tone board, lit by a one-sided 1.4 x 1.0 "
                 "emissive rectangle above the left and a glowing sphere on the right, maxdepth 1. Pixels in "
                 "umbrae, penumbrae and fully lit squares test the area-light estimators and their sampling density.",
     camera=(lookat_line(*CH_CAM[:3]), 'Camera "perspective" "float fov" [ 40 ]'), res=res_ch,
     my_spp=(16, 16), ref_spp=(64, 64), maxdepth=1, lightsamples=16,
     world=lambda: ('AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 9 9 9 ]\n' +
                    quad((-2.2, 3.4, -1.0), (-0.8, 3.4, -1.0), (-0.8, 3.4, 0.0), (-2.2, 3.4, 0.0)) + "AttributeEnd\n" +
                    'AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 12 11 10 ]\nTranslate 2.05 1.25 1.6\n'
                    'Shape "sphere" "float radius" [ 0.18 ]\nAttributeEnd\n' + chess()),
     pixels=pts(cam_ch, [("white king, shoulder", (-0.42, 0.75, 0.12)), ("black king, side facing the lamp", (1.47, 0.6, 0.65)),
                        ("ivory square, lit", (-1.25, 0, -1.25)), ("walnut square, lit", (-0.75, 0, -1.25)),
                        ("board, umbra behind the white king", (0.25, 0, 0.6)),
                        ("board, penumbra", (0.05, 0, 1.02)), ("board, lamp-lit, rook shadow edge", (0.25, 0, 1.55)),
                        ("rook top", (0.75, 0.73, 1.25)), ("table cloth", (-2.6, -0.05, 0.6))]),
     window=1, thresholds=dict(max_rel_error=0.04))


def gallery():
    q = quad
    X, Y, Z0, Z1 = 2.0, 2.6, -4.0, 3.0
    w = ['AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 16 16 16 ]\n',
         q((-0.5, Y - 0.01, -0.6), (0.5, Y - 0.01, -0.6), (0.5, Y - 0.01, 0.2), (-0.5, Y - 0.01, 0.2)), "AttributeEnd\n",
         diffuse((0.78, 0.76, 0.72)), q((-X, Y, Z0), (X, Y, Z0), (X, Y, Z1), (-X, Y, Z1)),             # ceiling
         q((-X, 0, Z1), (X, 0, Z1), (X, Y, Z1), (-X, Y, Z1)), q((-X, 0, Z0), (X, 0, Z0), (X, Y, Z0), (-X, Y, Z0)),
         "AttributeBegin\n" + diffuse((0.42, 0.3, 0.2)) + q((-X, 0, Z0), (X, 0, Z0), (X, 0, Z1), (-X, 0, Z1)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.1, 0.42, 0.42)) + q((-X, 0, Z0), (-X, 0, Z1), (-X, Y, Z1), (-X, Y, Z0)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.72, 0.32, 0.14)) + q((X, 0, Z0), (X, 0, Z1), (X, Y, Z1), (X, Y, Z0)) + "AttributeEnd\n",
         # plinth and sculpture
         "AttributeBegin\n" + diffuse((0.8, 0.8, 0.78)) + box((-0.35, 0, 0.6), (0.35, 0.9, 1.3)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.85, 0.85, 0.85)) + 'Translate 0 1.3 0.95\nShape "sphere" "float radius" [ 0.4 ]\nAttributeEnd\n',
         # a column on the left and a bench on the right
         "AttributeBegin\n" + diffuse((0.7, 0.68, 0.62)) + box((-1.6, 0, 1.6), (-1.2, Y, 2.0)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.25, 0.18, 0.12)) + box((0.9, 0, -0.9), (1.9, 0.4, -0.4)) + "AttributeEnd\n",
         # paintings on the back wall: dark frames with coloured canvases
         "AttributeBegin\n" + diffuse((0.08, 0.06, 0.05)) + box((-1.0, 1.0, Z1 - 0.04), (-0.2, 1.9, Z1)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.75, 0.6, 0.15)) + q((-0.92, 1.08, Z1 - 0.041), (-0.28, 1.08, Z1 - 0.041),
                                                          (-0.28, 1.82, Z1 - 0.041), (-0.92, 1.82, Z1 - 0.041)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.08, 0.06, 0.05)) + box((0.6, 1.1, Z1 - 0.04), (1.6, 1.8, Z1)) + "AttributeEnd\n",
         "AttributeBegin\n" + diffuse((0.15, 0.25, 0.6)) + q((0.68, 1.18, Z1 - 0.041), (1.52, 1.18, Z1 - 0.041),
                                                         (1.52, 1.72, Z1 - 0.041), (0.68, 1.72, Z1 - 0.041)) + "AttributeEnd\n"]
    return "".join(w)


res_gal = (256, 192)
G_CAM = ((0.15, 1.35, -3.6), (0, 1.1, 1.5), (0, 1, 0), 58)
cam_gal = Camera(*G_CAM, res_gal[0], res_gal[1])
test(8, name="Gallery: Phong diffuse interreflection in a closed room (maxdepth 3)",
     category="shading", metric="pixels",
     description="Closed room with a teal and a terracotta wall, a ceiling light panel, a sculpture on a plinth, "
                 "a column, a bench and paintings, maxdepth 3 (direct light plus two diffuse bounces). The ceiling "
                 "and the underside of the sphere are lit only indirectly and the walls bleed colour, so the pixels "
                 "test indirect light and the meaning of maxdepth.",
     camera=(lookat_line(*G_CAM[:3]), 'Camera "perspective" "float fov" [ 58 ]'), res=res_gal,
     my_spp=(32, 32), ref_spp=(128, 128), maxdepth=3, lightsamples=4, world=gallery, display_pct=0.9,
     pixels=pts(cam_gal, [("ceiling, beside the light (indirect only)", (-1.2, 2.6, 0.9)),
                        ("back wall", (0.15, 0.6, 3.0)), ("teal wall", (-2.0, 1.2, -0.6)),
                        ("terracotta wall", (2.0, 1.6, 0.4)),
                        ("floor near the teal wall (colour bleeding)", (-1.75, 0, -0.9)),
                        ("floor near the terracotta wall (colour bleeding)", (1.8, 0, 0.4)),
                        ("sculpture top", (-0.05, 1.68, 0.8)), ("sculpture underside (indirect only)", (0.1, 1.0, 0.7)),
                        ("plinth front", (-0.15, 0.4, 0.6)), ("yellow painting", (-0.6, 1.45, 2.959))]),
     window=1, thresholds=dict(max_rel_error=0.05))


# ---------------------------------------------------------------- Phong specular (analytic reference)
# Three white Phong spheres on a Phong plane under a red, a green and a blue point light: coloured
# highlights and RGB shadows. maxdepth 1, so the image is direct light only and has a closed form.
PH_LIGHTS = [((-3.0, 4.2, -1.2), (16.0, 0.0, 0.0)), ((0.2, 4.8, -2.6), (0.0, 16.0, 0.0)),
             ((3.0, 4.2, -1.0), (0.0, 0.0, 16.0))]
PH_PLANE = dict(kd=(0.3, 0.3, 0.32), ks=(0.25, 0.25, 0.25), n=20.0)
PH_SPHERES = [((-1.25, 0.75, 1.0), 0.75, dict(kd=(0.45, 0.45, 0.45), ks=(0.5, 0.5, 0.5), n=60.0)),
              ((0.75, 0.5, 0.15), 0.5, dict(kd=(0.25, 0.25, 0.25), ks=(0.7, 0.7, 0.7), n=200.0)),
              ((1.65, 0.38, 1.7), 0.38, dict(kd=(0.6, 0.6, 0.6), ks=(0.2, 0.2, 0.2), n=12.0))]
P_CAM = ((0.0, 3.0, -5.2), (0.15, 0.4, 0.9), (0, 1, 0), 40)
res_ph = (320, 240)
cam_ph = Camera(*P_CAM, res_ph[0], res_ph[1])


def phong_mat(m):
    return ('Material "phong" "rgb Kd" [ %s ] "rgb Ks" [ %s ] "float exponent" [ %s ]\n'
            % (v3(m["kd"]), v3(m["ks"]), fmt(m["n"])))


def phong_world():
    w = ["".join('LightSource "point" "point3 from" [ %s ] "rgb I" [ %s ]\n' % (v3(p), v3(I)) for p, I in PH_LIGHTS),
         phong_mat(PH_PLANE), tri_mesh([(-40, 0, -40), (40, 0, -40), (40, 0, 40), (-40, 0, 40)], [0, 1, 2, 0, 2, 3])]
    for c, r, m in PH_SPHERES:
        w.append("AttributeBegin\n" + phong_mat(m) + "Translate %s\n" % v3(c) +
                 'Shape "sphere" "float radius" [ %s ]\nAttributeEnd\n' % fmt(r))
    return "".join(w)


def _sphere_t(o, d, c, r):
    oc = sub(o, c)
    b = dot(oc, d)
    disc = b * b - (dot(oc, oc) - r * r)
    if disc < 0:
        return None
    s = math.sqrt(disc)
    for t in (-b - s, -b + s):
        if t > 1e-6:
            return t
    return None


def phong_radiance(o, d):
    """Exact direct radiance along a camera ray (normalised Phong, point lights, hard shadows)."""
    best, hit = float("inf"), None
    if d[1] < 0:
        best, hit = -o[1] / d[1], ("plane", None)
    for k, (c, r, m) in enumerate(PH_SPHERES):
        t = _sphere_t(o, d, c, r)
        if t is not None and t < best:
            best, hit = t, ("sphere", k)
    if hit is None:
        return (0.0, 0.0, 0.0), -1
    p = add(o, mul(d, best))
    if hit[0] == "plane":
        nrm, m, ident = (0.0, 1.0, 0.0), PH_PLANE, 0
    else:
        c, r, m = PH_SPHERES[hit[1]]
        nrm, ident = mul(sub(p, c), 1.0 / r), 1 + hit[1]
    wo = mul(d, -1)
    refl = sub(mul(nrm, 2 * dot(nrm, wo)), wo)
    out = [0.0, 0.0, 0.0]
    for lp, I in PH_LIGHTS:
        lv = sub(lp, p)
        d2 = dot(lv, lv)
        dist = math.sqrt(d2)
        wi = mul(lv, 1 / dist)
        cos_i = dot(nrm, wi)
        if cos_i <= 0:
            continue
        blocked = False
        for c, r, _m in PH_SPHERES:
            t = _sphere_t(p, wi, c, r)
            if t is not None and 1e-5 < t < dist:
                blocked = True
                break
        if blocked:
            continue
        cr = max(0.0, dot(refl, wi))
        spec = (m["n"] + 2) / (2 * math.pi) * cr ** m["n"]
        for k in range(3):
            out[k] += (m["kd"][k] / math.pi + m["ks"][k] * spec) * I[k] * cos_i / d2
    return tuple(out), ident


def phong_pixel(cam, x, y, ss):
    acc = [0.0, 0.0, 0.0]
    for j in range(ss):
        for i in range(ss):
            o, d = cam.ray(x + (i + 0.5) / ss, y + (j + 0.5) / ss)
            L, _ = phong_radiance(o, d)
            for k in range(3):
                acc[k] += L[k]
    return [v / (ss * ss) for v in acc]


def phong_analytic(cam, ss=4, fine=None, fine_ss=16):
    """Box-filtered closed form: ss x ss samples per pixel, fine_ss x fine_ss at the listed test pixels."""
    W, H = cam.xres, cam.yres
    data = [0.0] * (W * H * 3)
    for y in range(H):
        for x in range(W):
            data[3 * (y * W + x):3 * (y * W + x) + 3] = phong_pixel(cam, x, y, ss)
    for p in fine or []:
        x, y = p["x"], p["y"]
        data[3 * (y * W + x):3 * (y * W + x) + 3] = phong_pixel(cam, x, y, fine_ss)
    return rt.Image(W, H, data)


def phong_test_pixels(cam):
    """Highlight peaks found from the closed form (per sphere and light), plus chosen plane points."""
    out = []
    W, H = cam.xres, cam.yres
    peaks = {}
    for y in range(H):
        for x in range(W):
            o, d = cam.ray(x + 0.5, y + 0.5)
            L, ident = phong_radiance(o, d)
            if ident >= 1:
                for k in range(3):
                    key = (ident, k)
                    if L[k] > peaks.get(key, (0, None))[0]:
                        peaks[key] = (L[k], (x, y))
    names = ("red", "green", "blue")
    for (ident, k), (v, (x, y)) in sorted(peaks.items()):
        if (ident, k) in ((1, 0), (1, 1), (2, 2), (3, 0), (2, 1)):
            out.append({"label": "sphere %d (n %g), %s highlight" % (ident, PH_SPHERES[ident - 1][2]["n"], names[k]),
                        "x": x, "y": y})
    # plane pixels by which lights they see: all three (white), all but red (cyan), all but green
    # (magenta), all but blue (yellow); the brightest pixel whose 7x7 neighbourhood sees the same lights
    mask = {}
    for y in range(H):
        for x in range(W):
            o, d = cam.ray(x + 0.5, y + 0.5)
            L, ident = phong_radiance(o, d)
            if ident != 0:
                continue
            p = add(o, mul(d, -o[1] / d[1]))
            m = 0
            for li, (lp, _I) in enumerate(PH_LIGHTS):
                lv = sub(lp, p)
                dist = math.sqrt(dot(lv, lv))
                wi = mul(lv, 1 / dist)
                if not any((lambda t: t is not None and 1e-5 < t < dist)(_sphere_t(p, wi, c, r)) for c, r, _m in PH_SPHERES):
                    m |= 1 << li
            mask[(x, y)] = (m, lum(L))
    for want, label in ((7, "plane, lit by all three lights (white)"), (6, "plane, red light blocked (cyan shadow)"),
                        (5, "plane, green light blocked (magenta shadow)"), (3, "plane, blue light blocked (yellow shadow)")):
        best = None
        for (x, y), (m, l) in mask.items():
            if m != want or not (8 <= x < W - 8 and 8 <= y < H - 8):
                continue
            if all(mask.get((x + i, y + j), (-1, 0))[0] == want for j in range(-3, 4) for i in range(-3, 4)):
                if best is None or l > best[0]:
                    best = (l, x, y)
        if best:
            out.append({"label": label, "x": best[1], "y": best[2]})
    return out


test(9, name="Phong specular lobes vs the analytic value: RGB lights, three Phong spheres on a Phong plane",
     category="shading", metric="pixels", analytic=True,
     description="Three white Phong spheres (exponents 60, 200, 12) on a Phong plane (exponent 20) under a red, "
                 "a green and a blue point light (normalised modified Phong: kd/pi + ks (n+2)/(2 pi) cos^n alpha). "
                 "pbrt-v4 has no Phong BRDF, so the reference is the closed form with hard shadows, box-filtered "
                 "over each pixel. Pixels at the highlight peaks and in the coloured shadows.",
     camera=(lookat_line(*P_CAM[:3]), 'Camera "perspective" "float fov" [ 40 ]'), res=res_ph,
     my_spp=(16, 16), ref_spp=None, maxdepth=1, world=phong_world, pixels=None,
     window=0, thresholds=dict(max_rel_error=0.03))

# ---------------------------------------------------------------- error handling
# Each scene is a small, complete still life with one deliberate error. "mode" says where the error goes:
# world = lines appended after WorldBegin, options = lines before WorldBegin, replace = (old, new) in the
# header, file = an extra file written next to the scene.
ERR_HEADER = ('LookAt 0 2.4 -6  0 0.7 0  0 1 0\nCamera "perspective" "float fov" [ 40 ]\n'
              'Film "rgb" "integer xresolution" [ 96 ] "integer yresolution" [ 72 ] "string filename" [ "%s" ]\n'
              'Sampler "independent" "integer pixelsamples" [ 8 ]\nIntegrator "%s" "integer maxdepth" [ 2 ]\n')
ERR_WORLD = ('WorldBegin\nLightSource "point" "point3 from" [ -2 5 -3 ] "rgb I" [ 30 28 24 ]\n'
             'LightSource "distant" "point3 from" [ 3 4 -2 ] "point3 to" [ 0 0 0 ] "rgb L" [ 0.4 0.45 0.6 ]\n'
             'Material "diffuse" "rgb reflectance" [ 0.55 0.5 0.45 ]\n' +
             tri_mesh([(-20, 0, -20), (20, 0, -20), (20, 0, 20), (-20, 0, 20)], [0, 1, 2, 0, 2, 3]) +
             'AttributeBegin\nMaterial "diffuse" "rgb reflectance" [ 0.7 0.25 0.15 ]\nTranslate -1.1 0.7 0.3\n'
             'Shape "sphere" "float radius" [ 0.7 ]\nAttributeEnd\n'
             'AttributeBegin\nMaterial "diffuse" "rgb reflectance" [ 0.15 0.4 0.65 ]\nTranslate 0.9 0.5 -0.2\n'
             'Shape "sphere" "float radius" [ 0.5 ]\nAttributeEnd\n')

ERRORS = [  # (group, name, mode, payload, keywords[, extra files])
    # syntax
    ("syntax", "Misspelt directive (Shapee)", "world", ['Shapee "sphere" "float radius" [ 1 ]'], ["shapee", "directive"]),
    ("syntax", "Unterminated parameter list (missing ])", "world",
     ['Shape "sphere" "float radius" [ 1', 'Material "diffuse" "rgb reflectance" [ 0.5 0.5 0.5 ]'],
     ["syntax", "bracket", "unterminated", "expected"]),
    # scene structure
    ("structure", "AttributeEnd without AttributeBegin", "world", ['AttributeEnd', 'Shape "sphere" "float radius" [ 0.3 ]'],
     ["attributeend", "attribute"]),
    ("structure", "Missing Include file", "world", ['Include "missing_include.pbrt"'], ["missing_include", "include"]),
    # unknown types and names
    ("unknown", "Unknown shape type (teapot)", "world", ['Shape "teapot" "float radius" [ 1 ]'], ["teapot", "shape"]),
    ("unknown", "Unknown material type (plasticky)", "world",
     ['Material "plasticky" "rgb reflectance" [ 0.5 0.5 0.5 ]', 'Shape "sphere" "float radius" [ 0.3 ]'],
     ["plasticky", "material"]),
    ("unknown", "Undefined named material", "world", ['NamedMaterial "undefined_mat"', 'Shape "sphere" "float radius" [ 0.3 ]'],
     ["undefined_mat", "named"]),
    # missing files
    ("files", "Missing texture file", "world",
     ['Texture "t" "spectrum" "imagemap" "string filename" [ "does_not_exist.pfm" ]',
      'Material "diffuse" "texture reflectance" "t"', 'Shape "sphere" "float radius" [ 0.3 ]'], ["does_not_exist", "texture"]),
    # transforms
    ("transform", "Malformed transform: Translate with two numbers", "world",
     ['AttributeBegin', 'Translate 0 1', 'Shape "sphere" "float radius" [ 0.3 ]', 'AttributeEnd'], ["translate"]),
    # out-of-range values
    ("range", "Negative sphere radius", "world", ['Shape "sphere" "float radius" [ -1 ]'], ["radius"]),
    ("range", "Triangle mesh index out of range", "world",
     ['Shape "trianglemesh" "point3 P" [ 0 0 0  1 0 0  0 1 0 ] "integer indices" [ 0 1 7 ]'], ["index", "indices", "range"]),
    ("range", "Camera field of view 200 degrees", "replace",
     ('Camera "perspective" "float fov" [ 40 ]', 'Camera "perspective" "float fov" [ 200 ]'), ["fov"]),
]
FIRST_ERROR = 10
for k, e in enumerate(ERRORS):
    group, name, mode, payload, keys = e[:5]
    n = FIRST_ERROR + k
    test(n, name=name, category="error", metric="error", group=group, keywords=keys, mode=mode, payload=payload,
         files=e[5] if len(e) > 5 else {},
         description="Deliberate error (%s): %s. The renderer must not crash or hang, and must report the problem "
                     "(a log line mentioning one of %s)." % (group, name[0].lower() + name[1:], keys))


# ================================================================ writing
def header(t, for_pbrt):
    n = t["n"]
    lines = ["# testscene_%d: %s" % (n, t["name"]),
             "# Category: %s. %s" % (t["category"], t["description"]),
             "# Reference: testsuite_ref_%d.pfm, %s." % (
                 n, "analytic (see test.json)" if t.get("analytic") else
                 "rendered by pbrt-v4 from testscene_%d_pbrt.pbrt (same scene; only Integrator, Sampler and Film differ)" % n)]
    if for_pbrt:
        lines.append("# pbrt-v4 version of testscene_%d.pbrt, used to render the reference image." % n)
    lines += list(t["camera"])
    W, H = t["res"]
    fname = ("testsuite_ref_%d.pfm" if for_pbrt else "testsuite_my_%d.png") % n
    lines.append('Film "rgb" "integer xresolution" [ %d ] "integer yresolution" [ %d ] "string filename" [ "%s" ]' % (W, H, fname))
    sx, sy = t["ref_spp"] if for_pbrt else t["my_spp"]
    lines.append('Sampler "stratified" "integer xsamples" [ %d ] "integer ysamples" [ %d ] "bool jitter" true' % (sx, sy))
    lines.append('PixelFilter "box"')
    if for_pbrt:
        lines.append('Integrator "path" "integer maxdepth" [ %d ]' % t["maxdepth"])
    else:
        ls = (' "integer lightsamples" [ %d ]' % t["lightsamples"]) if t.get("lightsamples") else ""
        lines.append('Integrator "distributed" "integer maxdepth" [ %d ]%s' % (t["maxdepth"], ls))
    return "\n".join(lines) + "\n"


def error_scene(t, for_pbrt):
    n = t["n"]
    fname = ("testsuite_ref_%d.png" if for_pbrt else "testsuite_my_%d.png") % n
    h = ERR_HEADER
    if t["mode"] == "replace":
        old, new = t["payload"]
        assert old in h, old
        h = h.replace(old, new)
    h = h.replace('"%s" ]', '"' + fname + '" ]', 1).replace('Integrator "%s"', 'Integrator "%s"' % (
        "path" if for_pbrt else "distributed"))
    if t["mode"] == "options":
        h += "".join(l + "\n" for l in t["payload"])
    body = ERR_WORLD
    if t["mode"] == "world":
        body += "".join(l + "\n" for l in t["payload"])
    top = ("# testscene_%d: %s\n# Category: error (%s). %s\n" % (n, t["name"], t["group"], t["description"]) +
           ("# pbrt-v4 version (gives pbrt-v4's own message in testsuite_ref_%d.log).\n" % n if for_pbrt else ""))
    return top + h + body


RUN_SH = """#!/bin/sh
# Runs test %d only (renderer: ../../output/CGR26_renderer unless --renderer is given).
cd "$(dirname "$0")/.." && exec python3 runAllTests.py --tests %d "$@"
"""


def run(cmd, cwd, timeout=3600):
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return "timeout", (e.stdout or b"").decode("utf-8", "replace") + "\n[killed after %d s]\n" % timeout
    out = p.stdout.decode("utf-8", "replace").replace("\r", "\n")
    # Drop pbrt-v4's progress bar (it redraws one line many times).
    out = "\n".join(l for l in out.splitlines() if not l.lstrip().startswith("Rendering: [")) + "\n"
    return p.returncode, out


def build(t, args):
    n = t["n"]
    d = os.path.join(ST, "test%d" % n)
    os.makedirs(d, exist_ok=True)
    spec = {k: t[k] for k in ("name", "category", "metric", "description") if k in t}
    spec["test"] = n
    spec["scene"] = "testscene_%d.pbrt" % n
    with open(os.path.join(d, "run.sh"), "w") as f:
        f.write(RUN_SH % (n, n))
    os.chmod(os.path.join(d, "run.sh"), 0o755)
    if t["category"] == "error":
        with open(os.path.join(d, spec["scene"]), "w") as f:
            f.write(error_scene(t, False))
        with open(os.path.join(d, "testscene_%d_pbrt.pbrt" % n), "w") as f:
            f.write(error_scene(t, True))
        spec["group"] = t["group"]
        spec["error_lines"] = list(t["payload"]) if t["mode"] != "replace" else [t["payload"][1]]
        spec["keywords"] = t["keywords"]
        for fn, txt in t["files"].items():
            with open(os.path.join(d, fn), "w") as f:
                f.write(txt)
        spec["reference_log"] = "testsuite_ref_%d.log" % n
        if args.pbrt and not args.no_render:
            code, out = run([args.pbrt, "--nthreads", "4", "--outfile", os.path.join(args.tmp, "err.png"),
                             "testscene_%d_pbrt.pbrt" % n], d, 120)
            with open(os.path.join(d, "testsuite_ref_%d.log" % n), "w") as f:
                f.write("# pbrt-v4 console output for testscene_%d_pbrt.pbrt (exit status %s)\n" % (n, code) +
                        out.replace(d + "/", ""))
    else:
        with open(os.path.join(d, spec["scene"]), "w") as f:
            f.write(header(t, False) + "\nWorldBegin\n" + t["world"]())
        for fn, make in t.get("extra_files", {}).items():
            rt.write_pfm(os.path.join(d, fn), make())
        spec["reference"] = "testsuite_ref_%d.pfm" % n
        spec["reference_log"] = "testsuite_ref_%d.log" % n
        if not t.get("analytic"):
            spec["pbrt_scene"] = "testscene_%d_pbrt.pbrt" % n
            with open(os.path.join(d, spec["pbrt_scene"]), "w") as f:
                f.write(header(t, True) + "\nWorldBegin\n" + t["world"]())
        if t.get("analytic") and t.get("pixels") is None:
            t["pixels"] = phong_test_pixels(cam_ph)
        for k in ("pixels", "window", "markers", "radius"):
            if k in t:
                spec[k] = t[k]
        spec.update(t["thresholds"])
        if not args.no_render:
            if t.get("analytic"):
                img = phong_analytic(cam_ph, 4, spec["pixels"], 32)
                rt.write_pfm(os.path.join(d, spec["reference"]), img)
                with open(os.path.join(d, spec["reference_log"]), "w") as f:
                    f.write("# Analytic reference (scenes/tools/make_module3_tests.py, phong_analytic): normalised\n"
                            "# modified Phong kd/pi + ks (n+2)/(2 pi) cos^n(alpha), point lights with hard shadows,\n"
                            "# direct light only, box filter: 4x4 samples per pixel, 32x32 at the test pixels.\n"
                            "# plane y = 0: %s\n" % PH_PLANE +
                            "".join("# sphere centre %s radius %s: %s\n" % (c, r, m) for c, r, m in PH_SPHERES) +
                            "".join("# point light at %s, I = %s\n" % (p, I) for p, I in PH_LIGHTS) +
                            "# pbrt-v4 has no Phong BRDF, so no pbrt-v4 render exists for this test.\n")
            elif args.pbrt:
                code, out = run([args.pbrt, spec["pbrt_scene"]], d)
                with open(os.path.join(d, spec["reference_log"]), "w") as f:
                    f.write("# pbrt-v4 console output for %s (exit status %s)\n" % (spec["pbrt_scene"], code) + out)
                if code != 0:
                    print("pbrt-v4 failed on test %d:\n%s" % (n, out))
            ref = rt.read_pfm(os.path.join(d, spec["reference"]))
            if t["metric"] == "centroids":  # markers: start from the reference's own centroids
                lvl = rt.object_level(ref)
                for m in spec["markers"]:
                    cx, cy = rt.blob_centroid(ref, m["x"], m["y"], spec["radius"], lvl)
                    m["analytic_x"], m["analytic_y"] = m["x"], m["y"]
                    m["x"], m["y"] = round(cx, 3), round(cy, 3)
            exposure = 1.0
            if t["category"] == "shading":
                lums = sorted(ref.lum(x, y) for y in range(ref.h) for x in range(ref.w))
                exposure = round(0.8 / max(lums[int(t.get("display_pct", 0.99) * (len(lums) - 1))], 1e-6), 4)
            spec["display_exposure"] = exposure
            rt.display_png(os.path.join(d, "testsuite_ref_%d.png" % n), ref, exposure)
    with open(os.path.join(d, "test.json"), "w") as f:
        json.dump(spec, f, indent=1)
    # The log CGR26_renderer writes for this scene, as an example of a passing log.
    if args.renderer and not args.no_render:
        code, out = run([args.renderer, os.path.join(d, spec["scene"]), "--quiet", "--outdir", args.tmp,
                         "--out", "example_%d" % n], d)
        lp = os.path.join(args.tmp, "example_%d.log" % n)
        if os.path.exists(lp):
            txt = open(lp).read().replace(ROOT + "/", "")
            with open(os.path.join(d, "example_testsuite_my_%d.log" % n), "w") as f:
                f.write("# CGR26_renderer log for testscene_%d.pbrt (exit status %s)\n" % (n, code) + txt)
    print("test%d: %s" % (n, t["name"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbrt", default=os.path.expanduser("~/pbrt-v4/build/pbrt"))
    ap.add_argument("--renderer", default=os.path.join(ROOT, "output", "CGR26_renderer"))
    ap.add_argument("--only", default="")
    ap.add_argument("--no-render", action="store_true", help="write scenes and test.json only")
    args = ap.parse_args()
    if not os.path.exists(args.pbrt):
        print("pbrt-v4 not found at %s: references are not re-rendered" % args.pbrt)
        args.pbrt = None
    if not os.path.exists(args.renderer):
        args.renderer = None
    args.tmp = os.path.join(ROOT, "output", "module3", "tests_tmp")
    os.makedirs(args.tmp, exist_ok=True)
    only = {int(s) for s in args.only.split(",") if s.strip()}
    if not only:  # full rebuild: remove tests that no longer exist and old results
        for x in os.listdir(ST):
            if x.startswith("test") and x[4:].isdigit() and int(x[4:]) not in TESTS:
                shutil.rmtree(os.path.join(ST, x))
        shutil.rmtree(os.path.join(ST, "results"), ignore_errors=True)
    for n in sorted(TESTS):
        if not only or n in only:
            build(TESTS[n], args)
    shutil.rmtree(args.tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

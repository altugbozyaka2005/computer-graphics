#!/usr/bin/env python3
"""Module 3 checks (Python 3 standard library only); writes output/module3/validation.log.

  1  BVH exactness: every scene in scenes/ (Modules 1-3) renders to the same bytes with the BVH as
     with brute force (every ray against every primitive), at reduced resolution and spp.
  2  The BVH result does not depend on how the tree is built (split methods, leaf sizes).
  3  Checkpoint comparison (information): where the Module 1/2 per-object boxes ("objects") differ
     from brute force, and by how much.
  4  The student test suite discriminates: unchanged scenes pass, and each deliberately broken copy
     of a scene (wrong fov, light 5% too bright, maxdepth 2 for 3, ...) fails; a renderer that
     crashes or reports nothing fails the error-handling tests.

  python3 scenes/tools/validate_module3.py [--quick]
"""
import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "output")
VOUT = os.path.join(OUT, "module3", "validation")
R = os.path.join(OUT, "CGR26_renderer")
LOG = []
FAILS = []


def say(s=""):
    print(s)
    sys.stdout.flush()
    LOG.append(s)


def verdict(name, ok, details=()):
    say(("PASS  " if ok else "FAIL  ") + name)
    for d in details:
        say("      " + d)
    if not ok:
        FAILS.append(name)


def render(scene, out, extra):
    subprocess.run([R, scene, "--quiet", "--outdir", VOUT, "--out", out] + extra, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(VOUT, out + ".pfm")


def read_pfm(path):
    with open(path, "rb") as f:
        f.readline()
        w, h = map(int, f.readline().split())
        s = float(f.readline())
        return w, h, struct.unpack(("<" if s < 0 else ">") + "%df" % (w * h * 3), f.read(w * h * 12))


def diff_stats(a, b):
    _, _, x = read_pfm(a)
    _, _, y = read_pfm(b)
    n = len(x) // 3
    px = sum(1 for i in range(n) if x[3 * i:3 * i + 3] != y[3 * i:3 * i + 3])
    mx = max((abs(x[i] - y[i]) for i in range(len(x))), default=0.0)
    return px, n, mx


def low(scene):
    """Reduced settings (width 120, the scene's own aspect ratio, 2 spp)."""
    txt = open(scene, errors="replace").read()
    mx = re.search(r'"integer xresolution"\s*\[\s*(\d+)', txt)
    my = re.search(r'"integer yresolution"\s*\[\s*(\d+)', txt)
    w, h = (int(mx.group(1)), int(my.group(1))) if mx and my else (4, 3)
    return ["--res", "120x%d" % max(1, round(120 * h / w)), "--spp", "2"]


def check_exact(args):
    scenes = sorted(glob.glob(os.path.join(ROOT, "scenes", "*.pbrt")))
    if args.quick:
        scenes = [s for s in scenes if os.path.basename(s).startswith(("acc_", "WSRT_", "DRT_"))]
    same, details, objects_info = 0, [], []
    for s in scenes:
        stem = os.path.splitext(os.path.basename(s))[0]
        a = render(s, stem + "_bvh", ["--accel", "bvh"] + low(s))
        b = render(s, stem + "_none", ["--accel", "none"] + low(s))
        c = render(s, stem + "_objects", ["--accel", "objects"] + low(s))
        identical = open(a, "rb").read() == open(b, "rb").read()
        same += identical
        if not identical:
            px, n, mx = diff_stats(a, b)
            details.append("%s: %d of %d pixels differ (max %.3g)" % (stem, px, n, mx))
        px, n, mx = diff_stats(c, b)
        if px:
            objects_info.append("%s: objects vs none: %d of %d pixels differ, max |difference| %.4g" % (stem, px, n, mx))
    verdict("BVH gives byte-identical images to brute force on all %d scenes in scenes/ (%d identical)" % (len(scenes), same),
            same == len(scenes), details)
    return objects_info


def check_build_independence(args):
    details, ok = [], True
    for scene in ("acc_best", "acc_worst", "acc_complex"):
        path = os.path.join(ROOT, "scenes", scene + ".pbrt")
        ref = open(render(path, scene + "_none", ["--accel", "none"] + low(path)), "rb").read()
        for extra in (["--splitmethod", "middle"], ["--splitmethod", "equal"], ["--maxnodeprims", "1"],
                      ["--maxnodeprims", "32"]):
            out = "%s_%s" % (scene, "_".join(e.strip("-") for e in extra))
            got = open(render(path, out, ["--accel", "bvh"] + extra + low(path)), "rb").read()
            if got != ref:
                ok = False
                details.append("%s %s differs from brute force" % (scene, " ".join(extra)))
        details.append("%s: sah, middle, equal, maxnodeprims 1/4/32 all identical to brute force" % scene)
    verdict("BVH result independent of the split method and leaf size", ok, details if not ok else details[-3:])


# ---------------------------------------------------------------- 4 test-suite sensitivity
MUTATIONS = [  # (test, description, old text, new text)
    (1, "fov 45 -> 45.4 (framing off by ~1%)", '"float fov" [ 45 ]', '"float fov" [ 45.4 ]'),
    (2, "one petal rotated by 2 degrees more", "Rotate 36 0 0 1", "Rotate 38 0 0 1"),
    (3, "fov 30 -> 30.1", '"float fov" [ 30 ]', '"float fov" [ 30.1 ]'),
    (4, "fov 60 applied to the longer axis (fov 60 -> 32.2)", '"float fov" [ 60 ]', '"float fov" [ 32.2 ]'),
    (5, "screen window shifted by 0.7%", "[ -1.1 1.9 -0.45 1.55 ]", "[ -1.08 1.92 -0.45 1.55 ]"),
    (6, "fov 70 -> 70.4", '"float fov" [ 70 ]', '"float fov" [ 70.4 ]'),
    (7, "camera 0.03 units higher", "LookAt 0 1.2 -1.2", "LookAt 0 1.23 -1.2"),
    (8, "screen window 1% wider", "[ -3.4 3.4 -2.0 2.675 ]", "[ -3.434 3.434 -2.0 2.675 ]"),
    (9, "focal distance 5.3 -> 4.3 (focus on the wrong pawn)", '"float focaldistance" [ 5.3 ]',
     '"float focaldistance" [ 4.3 ]'),
    (9, "lens radius 0.06 -> 0.075 (25% more blur)", '"float lensradius" [ 0.06 ]', '"float lensradius" [ 0.075 ]'),
    (10, "point light 5% brighter", '"rgb I" [ 30 30 30 ]', '"rgb I" [ 31.5 31.5 31.5 ]'),
    (10, "spotlight cone 22 -> 20 degrees", '"float coneangle" [ 22 ]', '"float coneangle" [ 20 ]'),
    (11, "rectangular area light 5% brighter", '"rgb L" [ 9 9 9 ]', '"rgb L" [ 9.45 9.45 9.45 ]'),
    (12, "maxdepth 3 -> 2 (one indirect bounce fewer)", '"integer maxdepth" [ 3 ]', '"integer maxdepth" [ 2 ]'),
    (13, "floor uv mirrored in u", '"point2 uv" [ 0 0  1 0  1 1  0 1 ]', '"point2 uv" [ 1 0  0 0  0 1  1 1 ]'),
    (13, "image texture scale 0.9 -> 0.85", '"float scale" [ 0.9 ]', '"float scale" [ 0.85 ]'),
    (14, "Phong exponent 60 -> 66", '"float exponent" [ 60 ]', '"float exponent" [ 66 ]'),
]


def check_suite(args):
    tmp = os.path.join(VOUT, "suite")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "studentTests"), tmp, ignore=shutil.ignore_patterns("results", "runAllTests.log"))
    runner = os.path.join(tmp, "runAllTests.py")
    def run(tests, renderer=R):
        # The renderer writes into its own folder (output/ for CGR26_renderer), where the runner looks.
        p = subprocess.run([sys.executable, runner, "--renderer", renderer, "--tests", tests],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode()
        return {int(l.split()[0][4:]): ("PASS" in l.split()[2]) for l in out.splitlines() if l.startswith("test")}

    base = run(",".join(str(n) for n in sorted({m[0] for m in MUTATIONS})))
    verdict("unchanged image tests pass", all(base.values()), ["%s" % base])
    details, ok = [], True
    for n, desc, old, new in MUTATIONS:
        path = os.path.join(tmp, "test%d" % n, "testscene_%d.pbrt" % n)
        txt = open(path).read()
        if old not in txt:
            ok = False
            details.append("test%d: mutation text not found (%s)" % (n, old))
            continue
        open(path, "w").write(txt.replace(old, new, 1))
        res = run(str(n))
        open(path, "w").write(txt)
        caught = res.get(n) is False
        ok &= caught
        details.append("test%-3d %-48s -> %s" % (n, desc, "FAIL (caught)" if caught else "PASS (NOT caught)"))
    verdict("each deliberately broken image test fails", ok, details)
    # Fake renderers for the error category: one crashes (SIGSEGV), one exits 0 and writes nothing.
    crash = os.path.join(VOUT, "crash.sh")
    open(crash, "w").write("#!/bin/sh\nkill -SEGV $$\n")
    silent = os.path.join(VOUT, "silent.sh")
    open(silent, "w").write("#!/bin/sh\nexit 0\n")
    for p in (crash, silent):
        os.chmod(p, 0o755)
    errs = ",".join(str(n) for n in sorted(
        int(d[4:]) for d in os.listdir(tmp) if d.startswith("test") and d[4:].isdigit()
        and json.load(open(os.path.join(tmp, d, "test.json")))["category"] == "error"))
    rc, rs = run(errs, crash), run(errs, silent)
    verdict("error tests fail for a crashing renderer and for one that reports nothing",
            not any(rc.values()) and not any(rs.values()),
            ["crashing renderer: %d of %d passed" % (sum(rc.values()), len(rc)),
             "silent renderer:   %d of %d passed" % (sum(rs.values()), len(rs))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    os.makedirs(VOUT, exist_ok=True)
    say("==== Module 3 validation ====")
    objects_info = check_exact(args)
    check_build_independence(args)
    say("INFO  checkpoint per-object boxes ('objects') vs brute force:")
    for l in objects_info or ["identical on every scene"]:
        say("      " + l)
    check_suite(args)
    say("== %d of %d checks passed" % (sum(1 for l in LOG if l.startswith("PASS")),
                                       sum(1 for l in LOG if l.startswith(("PASS", "FAIL")))))
    with open(os.path.join(OUT, "module3", "validation.log"), "w") as f:
        f.write("\n".join(LOG) + "\n")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

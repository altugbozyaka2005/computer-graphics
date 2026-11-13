#!/usr/bin/env python3
"""Module 3, 2.3.1: renders the acceleration-structure images and measures the timings
(Python 3 standard library only).

  python3 scenes/tools/module3_study.py [--quick] [--threads N]

Writes into output/:
  acc_best.png, acc_worst.png, acc_complex.png (+ .pfm, .log)     the three required images (BVH)
  module3/acc/<scene>_<accel>.log                                   every timing run's log
  module3/acc/<scene>_cost.pfm                                      per-pixel cost maps (--costmap)
  module3/acc_main.csv     best / worst / complex (+ two Module 1 scenes): none vs objects vs bvh
  module3/acc_scaling.csv  render time and tests per ray against primitive count (marbles, straws)
  module3/acc_split.csv    BVH split methods (sah, middle, equal)
  module3/acc_leaf.csv     BVH maxnodeprims sweep
  module3/module3.log      all tables in text form

Timings: every configuration of a table is rendered with the same resolution and samples per pixel
(given in the tables; the main table uses 960 pixels wide for the three acc_ scenes, whose images are
1920 wide); runs that take under 5 s are repeated three times and the fastest is kept.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "output")
M3OUT = os.path.join(OUT, "module3")
ACCOUT = os.path.join(M3OUT, "acc")
R = os.path.join(OUT, "CGR26_renderer")
LOG = []


def say(s=""):
    print(s)
    sys.stdout.flush()
    LOG.append(s)


def log_values(path):
    txt = open(path).read()

    def num(key, cast=float):
        m = re.search(r"^" + re.escape(key) + r"\s*([0-9.]+)", txt, re.M)
        return cast(m.group(1)) if m else None
    v = {"render_s": num("render (s):"), "build_s": num("accel build (s):"), "parse_s": num("parse+load (s):"),
         "prim_tests": num("ray-primitive tests:", int), "box_tests": num("ray-box tests:", int),
         "camera_rays": num("camera rays:", int), "secondary_rays": num("secondary rays:", int),
         "shadow_rays": num("shadow rays:", int)}
    v["rays"] = (v["camera_rays"] or 0) + (v["secondary_rays"] or 0) + (v["shadow_rays"] or 0)
    m = re.search(r"scene: (\d+) primitives", txt)
    v["prims"] = int(m.group(1)) if m else None
    m = re.search(r"(\d+) objects", txt)
    v["objects"] = int(m.group(1)) if m else None
    m = re.search(r"(\d+) nodes, (\d+) leaves, depth (\d+), largest leaf (\d+), mean prims/leaf ([0-9.]+), SAH cost ([0-9.]+)", txt)
    if m:
        v.update(nodes=int(m.group(1)), leaves=int(m.group(2)), depth=int(m.group(3)), largest_leaf=int(m.group(4)),
                 mean_leaf=float(m.group(5)), sah_cost=float(m.group(6)))
    m = re.search(r"film: (\d+)x(\d+), (\d+) spp", txt)
    if m:
        v["res"] = "%sx%s" % (m.group(1), m.group(2))
        v["spp"] = int(m.group(3))
    v["prim_per_ray"] = v["prim_tests"] / v["rays"] if v["rays"] else 0
    v["box_per_ray"] = v["box_tests"] / v["rays"] if v["rays"] else 0
    return v


def render(scene, out, args, extra, repeat=True):
    """Renders and returns the log values; fast runs are repeated and the fastest time kept."""
    os.makedirs(ACCOUT, exist_ok=True)
    best = None
    for _ in range(3 if repeat else 1):
        cmd = [R, os.path.join(ROOT, "scenes", scene), "--quiet", "--outdir", ACCOUT, "--out", out] + extra
        if args.threads:
            cmd += ["--threads", str(args.threads)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        v = log_values(os.path.join(ACCOUT, out + ".log"))
        if best is None or v["render_s"] < best["render_s"]:
            best = v
        if v["render_s"] > 5:
            break
    return best


def write_csv(name, header, rows):
    with open(os.path.join(M3OUT, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def table(header, rows):
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(header)]
    say("  " + "  ".join(str(h).rjust(widths[i]) for i, h in enumerate(header)))
    for r in rows:
        say("  " + "  ".join(str(c).rjust(widths[i]) for i, c in enumerate(r)))


def f3(v):
    return "%.3f" % v


# ---------------------------------------------------------------- 1 best / worst / complex
MAIN = [  # (label, scene, spp, resolution used for the timing table; None = the scene's own)
    # The output images are 1920 pixels wide; brute force at that size would take ~10 min per run, so
    # the table uses half the width (same camera and aspect ratio) for all three configurations.
    ("best", "acc_best.pbrt", 1, "960x540"),
    ("worst", "acc_worst.pbrt", 1, "960x540"),
    ("complex", "acc_complex.pbrt", 1, "960x640"),
    ("few primitives (Module 1 WSRT_simple)", "WSRT_simple.pbrt", 1, None),
    ("realistic (Module 1 DRT_creative)", "DRT_creative.pbrt", 1, None),
]
TIMING_RES = {os.path.splitext(m[1])[0]: m[3] for m in MAIN}


def main_table(args):
    say("== 1  Render time without and with the BVH (all configurations of a row: same resolution and spp)")
    say("   none = every ray against every primitive; objects = one box per Shape directive (the Module 1/2")
    say("   renderer); bvh = SAH BVH, maxnodeprims 4. Times in seconds on %s threads." % (args.threads or "all"))
    rows = []
    for label, scene, spp, tres in MAIN:
        stem = os.path.splitext(scene)[0]
        res = {}
        for accel in ("bvh", "objects", "none"):
            if args.quick and accel != "bvh" and stem in ("acc_best", "acc_complex", "DRT_creative"):
                extra_res = ["--res", "240x135" if stem != "DRT_creative" else "150x200"]
            else:
                extra_res = ["--res", tres] if tres else []
            res[accel] = render(scene, "%s_%s" % (stem, accel), args, ["--accel", accel, "--spp", str(spp)] + extra_res,
                                repeat=True)
        b, o, n = res["bvh"], res["objects"], res["none"]
        rows.append([label, b["res"], b["spp"], b["prims"], b["objects"], f3(n["render_s"]), f3(o["render_s"]),
                     f3(b["build_s"]), f3(b["render_s"]), "%.1f" % (n["render_s"] / b["render_s"]),
                     "%.1f" % (o["render_s"] / b["render_s"]), "%.1f" % n["prim_per_ray"], "%.1f" % o["prim_per_ray"],
                     "%.2f" % b["prim_per_ray"], "%.1f" % b["box_per_ray"],
                     "%.1f" % (n["prim_tests"] / max(1, b["prim_tests"] + b["box_tests"])),
                     b.get("nodes"), b.get("depth"), b.get("sah_cost")])
    header = ["scene", "resolution", "spp", "primitives", "objects", "none_s", "objects_s", "bvh_build_s", "bvh_s",
              "speedup_vs_none", "speedup_vs_objects", "prim_tests_per_ray_none", "prim_tests_per_ray_objects",
              "prim_tests_per_ray_bvh", "box_tests_per_ray_bvh", "test_reduction_vs_none", "bvh_nodes", "bvh_depth",
              "bvh_sah_cost"]
    write_csv("acc_main.csv", header, rows)
    table(["scene", "res", "spp", "prims", "none s", "objects s", "build s", "bvh s", "x none", "x objects",
           "tests/ray none", "prim/ray bvh", "box/ray bvh"],
          [[r[0][:24], r[1], r[2], r[3], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[13], r[14]] for r in rows])
    say("   (x none = none_s / bvh_s; x objects = objects_s / bvh_s; the build time is not in bvh_s)")
    say()


# ---------------------------------------------------------------- 2 scaling
def scaling(args):
    import make_module3_scenes as ms
    say("== 2  Scaling with the number of primitives (400x225, 1 spp, Whitted, maxdepth 5)")
    rows = []
    for kind, counts in (("marbles", ms.SCALE_MARBLES), ("straws", ms.SCALE_STRAWS)):
        for n in counts:
            if args.quick and n > 4096:
                continue
            scene = "module3/acc/scale_%s_%d.pbrt" % (kind, n)
            b = render(scene, "scale_%s_%d_bvh" % (kind, n), args, ["--accel", "bvh"])
            nn = render(scene, "scale_%s_%d_none" % (kind, n), args, ["--accel", "none"])
            rows.append([kind, n, b["prims"], f3(nn["render_s"]), f3(b["render_s"]), f3(b["build_s"]),
                         "%.2f" % (nn["render_s"] / b["render_s"]), "%.1f" % nn["prim_per_ray"],
                         "%.2f" % b["prim_per_ray"], "%.1f" % b["box_per_ray"], b.get("depth"), b.get("sah_cost")])
    header = ["layout", "count", "primitives", "none_s", "bvh_s", "bvh_build_s", "speedup", "prim_tests_per_ray_none",
              "prim_tests_per_ray_bvh", "box_tests_per_ray_bvh", "bvh_depth", "bvh_sah_cost"]
    write_csv("acc_scaling.csv", header, rows)
    table(["layout", "count", "prims", "none s", "bvh s", "build s", "speedup", "prim/ray none", "prim/ray bvh",
           "box/ray bvh", "depth"], [r[:11] for r in rows])
    say()


# ---------------------------------------------------------------- 3 split methods and leaf size
def split_and_leaf(args):
    say("== 3  BVH split method (maxnodeprims 4) and leaf size (sah); 1 spp at each scene's resolution")
    rows = []
    for scene in ("acc_best.pbrt", "acc_worst.pbrt", "acc_complex.pbrt"):
        stem = os.path.splitext(scene)[0]
        for sm in ("sah", "middle", "equal"):
            extra = ["--accel", "bvh", "--splitmethod", sm, "--spp", "1"] + (["--res", "200x150"] if args.quick else [])
            v = render(scene, "%s_split_%s" % (stem, sm), args, extra)
            rows.append([stem, sm, f3(v["build_s"]), v["nodes"], v["depth"], v["sah_cost"], f3(v["render_s"]),
                         "%.2f" % v["prim_per_ray"], "%.1f" % v["box_per_ray"]])
    write_csv("acc_split.csv", ["scene", "splitmethod", "build_s", "nodes", "depth", "sah_cost", "render_s",
                                "prim_tests_per_ray", "box_tests_per_ray"], rows)
    table(["scene", "split", "build s", "nodes", "depth", "SAH cost", "render s", "prim/ray", "box/ray"], rows)
    rows = []
    for scene in ("acc_best.pbrt", "acc_complex.pbrt"):
        stem = os.path.splitext(scene)[0]
        for mp in (1, 2, 4, 8, 16, 32):
            extra = ["--accel", "bvh", "--maxnodeprims", str(mp), "--spp", "1"] + (["--res", "200x150"] if args.quick else [])
            v = render(scene, "%s_leaf_%d" % (stem, mp), args, extra)
            rows.append([stem, mp, f3(v["build_s"]), v["nodes"], v["depth"], "%.2f" % v["mean_leaf"], v["sah_cost"],
                         f3(v["render_s"]), "%.2f" % v["prim_per_ray"], "%.1f" % v["box_per_ray"]])
    write_csv("acc_leaf.csv", ["scene", "maxnodeprims", "build_s", "nodes", "depth", "mean_prims_per_leaf", "sah_cost",
                               "render_s", "prim_tests_per_ray", "box_tests_per_ray"], rows)
    table(["scene", "maxnodeprims", "build s", "nodes", "depth", "prims/leaf", "SAH cost", "render s", "prim/ray",
           "box/ray"], rows)
    say()


# ---------------------------------------------------------------- 4 final images and cost maps
def images(args):
    say("== 4  Output images (BVH, scene settings) and cost maps (1 spp, at the timing resolution)")
    for scene in ("acc_best", "acc_worst", "acc_complex"):
        extra = ["--quiet"] + (["--spp", "4"] if args.quick else [])
        t = time.time()
        subprocess.run([R, os.path.join(ROOT, "scenes", scene + ".pbrt")] + extra, check=True, stdout=subprocess.DEVNULL)
        v = log_values(os.path.join(OUT, scene + ".log"))
        say("   %-12s %s, %d spp: build %.3f s, render %.2f s (wall %.1f s), %.2f primitive + %.1f box tests per ray" % (
            scene, v["res"], v["spp"], v["build_s"], v["render_s"], time.time() - t, v["prim_per_ray"], v["box_per_ray"]))
        for accel in ("bvh", "objects"):
            if accel == "objects" and scene != "acc_complex":
                continue
            subprocess.run([R, os.path.join(ROOT, "scenes", scene + ".pbrt"), "--quiet", "--accel", accel, "--spp", "1",
                            "--res", TIMING_RES[scene], "--costmap", "--outdir", ACCOUT, "--out", "%s_costmap_%s" % (scene, accel)],
                           check=True, stdout=subprocess.DEVNULL)
    say()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="lower resolutions for the slow brute-force runs")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--only", default="", help="comma-separated sections: main,scaling,split,images")
    args = ap.parse_args()
    if not os.path.exists(R):
        sys.exit("renderer not built: " + R)
    os.makedirs(ACCOUT, exist_ok=True)
    say("==== Module 3 acceleration study (%s) ====" % time.strftime("%Y-%m-%d %H:%M:%S"))
    only = set(s for s in args.only.split(",") if s)
    for name, fn in (("images", images), ("main", main_table), ("scaling", scaling), ("split", split_and_leaf)):
        if not only or name in only:
            fn(args)
    with open(os.path.join(M3OUT, "module3.log" if not only else "module3_%s.log" % "_".join(sorted(only))), "w") as f:
        f.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()

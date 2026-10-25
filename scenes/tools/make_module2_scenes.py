#!/usr/bin/env python3
"""Scene files for Module 2 (Python 3 standard library only).

Writes every scene rendered for the Module 2 report, so that variants of one study
(field of view, samples per pixel, light-sample counts, BF / MD) share their geometry:

  scenes/include/m2_*.pbrt     shared worlds (geometry, materials, lights)
  scenes/<output>.pbrt         one file per required output image (camera_ortho, aa_ss4, ...)
  scenes/module2/<study>/*.pbrt  the extra views and parameter sweeps shown in the figures
  scenes/module2/sampler/sampler_ref_pbrt.pbrt  the same sampler scene for pbrt-v4 (reference)
  scenes/module2/views.json    camera and callout anchors of every image (for make_figures_m2.py)

Only the sampler-study world is pure pbrt-v4 syntax (it is also rendered by pbrt-v4); the
other worlds use the renderer's extensions (blinnphong materials, whitted/distributed).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_poolroom as mp  # noqa: E402  (mesh helpers: lathe, fix_winding, box, quad, fmt)

SCENES = os.path.join(HERE, "..")
INC = os.path.join(SCENES, "include")
M2 = os.path.join(SCENES, "module2")
fmt = mp.fmt
VIEWS = {}


# ---------------------------------------------------------------- small helpers
def vec(v):
    return " ".join(fmt(c) for c in v)


def write(path, text):
    """Writes text to path unless the file already holds exactly that text."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return
    with open(path, "w") as f:
        f.write(text)


def rel(path):
    return os.path.relpath(path, SCENES)


def mesh_shape(mesh, extra=""):
    """Inline pbrt trianglemesh with vertex normals and uvs (standard pbrt-v4 syntax)."""
    verts, norms, uvs, faces = mesh
    out = ['Shape "trianglemesh"' + extra + "\n"]
    out.append('    "point3 P" [ ' + "  ".join(vec(v) for v in verts) + " ]\n")
    out.append('    "normal N" [ ' + "  ".join(vec(n) for n in norms) + " ]\n")
    out.append('    "point2 uv" [ ' + "  ".join(vec(t) for t in uvs) + " ]\n")
    out.append('    "integer indices" [ ' + " ".join("%d %d %d" % f for f in faces) + " ]\n")
    return "".join(out)


def flat_shape(tris):
    """Trianglemesh from a list of triangles [(p0, p1, p2), ...] (flat shading)."""
    P, I = [], []
    for t in tris:
        base = len(P)
        P.extend(t)
        I.extend([base, base + 1, base + 2])
    return ('Shape "trianglemesh" "point3 P" [ ' + "  ".join(vec(p) for p in P) + ' ]\n    "integer indices" [ ' +
            " ".join(str(i) for i in I) + " ]\n")


def box_tris(lo, hi):
    """12 outward triangles of an axis-aligned box."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    q = [((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)),   # -x
         ((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)),   # +x
         ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),   # -y
         ((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)),   # +y
         ((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)),   # -z
         ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]   # +z
    out = []
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    for a, b, cc, d in q:
        for t in ((a, b, cc), (a, cc, d)):
            n = mp.tri_normal(*t)
            fc = [sum(p[k] for p in t) / 3 for k in range(3)]
            if sum(n[k] * (fc[k] - c[k]) for k in range(3)) < 0:
                t = (t[0], t[2], t[1])
            out.append(t)
    return out


def boxes_shape(boxes):
    tris = []
    for lo, hi in boxes:
        tris += box_tris(lo, hi)
    return flat_shape(tris)


def quad_shape(p0, p1, p2, p3, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    return mp.quad(p0, p1, p2, p3, uv)


def torus_mesh(R, r, nu, nv):
    """Torus around the y axis: smooth normals, uv in [0,1]^2."""
    verts, norms, uvs, faces = [], [], [], []
    for i in range(nu + 1):
        u = 2 * math.pi * i / nu
        for j in range(nv + 1):
            v = 2 * math.pi * j / nv
            cx, cz = math.cos(u), math.sin(u)
            n = (math.cos(v) * cx, math.sin(v), math.cos(v) * cz)
            verts.append(((R + r * math.cos(v)) * cx, r * math.sin(v), (R + r * math.cos(v)) * cz))
            norms.append(n)
            uvs.append((i / nu, j / nv))
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            b = (i + 1) * (nv + 1) + j
            faces += [(a, b, b + 1), (a, b + 1, a + 1)]
    return mp.fix_winding((verts, norms, uvs, faces))


def lathe_mesh(profile, segments):
    return mp.fix_winding(mp.lathe(profile, segments))


def lookat(eye, look, up=(0, 1, 0)):
    return "LookAt %s   %s   %s\n" % (vec(eye), vec(look), vec(up))


def register(name, cam, res, callouts=(), extra=None):
    """Camera and callout anchors of an image, for make_figures_m2.py."""
    v = {"camera": cam, "res": list(res), "callouts": [list(c) for c in callouts]}
    if extra:
        v.update(extra)
    VIEWS[name] = v


def camera_block(cam):
    s = lookat(cam["eye"], cam["look"], cam.get("up", (0, 1, 0)))
    if cam["type"] == "orthographic":
        s += 'Camera "orthographic" "float screenwindow" [ %s ]' % vec(cam["window"])
    else:
        s += 'Camera "perspective" "float fov" [ %s ]' % fmt(cam["fov"])
    if cam.get("lensradius"):
        s += ' "float lensradius" [ %s ] "float focaldistance" [ %s ]' % (fmt(cam["lensradius"]), fmt(cam["focaldistance"]))
    return s + "\n"


def scene_file(path, comment, cam, res, out_name, sampler, integrator, world_include, film_extra=""):
    text = "".join("# " + line + "\n" for line in comment.strip().split("\n"))
    text += camera_block(cam)
    text += 'Film "rgb" "integer xresolution" [ %d ] "integer yresolution" [ %d ]\n    "string filename" [ "%s.png" ]%s\n' % (
        res[0], res[1], out_name, film_extra)
    text += sampler + "\n" + integrator + "\n\n"
    inc = os.path.relpath(world_include, os.path.dirname(path))
    text += 'Include "%s"\n' % inc
    write(path, text)


def stratified(n, jitter=True):
    return 'Sampler "stratified" "integer xsamples" [ %d ] "integer ysamples" [ %d ] "bool jitter" %s' % (
        n, n, "true" if jitter else "false")


def independent(n):
    return 'Sampler "independent" "integer pixelsamples" [ %d ]' % n


def whitted(md=5, ambient=(0.12, 0.12, 0.14)):
    return 'Integrator "whitted" "integer maxdepth" [ %d ] "rgb ambient" [ %s ]' % (md, vec(ambient))


def distributed(md, bf=1, ls=4, sampling=None, extra=""):
    s = 'Integrator "distributed" "integer maxdepth" [ %d ] "integer branchingfactor" [ %d ] "integer lightsamples" [ %d ]' % (
        md, bf, ls)
    if sampling:
        s += ' "string lightsampling" "%s"' % sampling
    return s + extra


TONEMAP_NONE = ' "string tonemap" "none"'


# ================================================================ 2.2.1 camera models
# ---- orthographic preferred: an isometric town block (equal houses, measurable sizes)
TOWN_HOUSES = [(ix, iz) for ix in range(-2, 2) for iz in range(-2, 2)]  # 4 x 4 grid of identical houses
TOWN_SPACING = 4.0
HOUSE_W, HOUSE_H, HOUSE_D, ROOF_H = 2.0, 1.4, 2.0, 1.0


def town_world():
    s = ["# Isometric town block: 16 identical houses on a 1-unit ground grid (camera_ortho).\n",
         "WorldBegin\n",
         'LightSource "distant" "point3 from" [ -4 10 -6 ] "point3 to" [ 0 0 0 ] "rgb L" [ 1.05 1.0 0.92 ]\n',
         'LightSource "infinite" "rgb L" [ 0.55 0.65 0.8 ]\n',
         'Texture "grid" "spectrum" "checkerboard" "float uscale" [ 128 ] "float vscale" [ 128 ]\n'
         '    "rgb tex1" [ 0.78 0.78 0.74 ] "rgb tex2" [ 0.66 0.68 0.64 ]\n',
         'MakeNamedMaterial "ground" "string type" "blinnphong" "texture Kd" "grid" "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "wallA" "string type" "blinnphong" "rgb Kd" [ 0.85 0.78 0.62 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "wallB" "string type" "blinnphong" "rgb Kd" [ 0.72 0.8 0.86 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "roof" "string type" "blinnphong" "rgb Kd" [ 0.62 0.2 0.15 ] "rgb Ka" [ 1 1 1 ]\n'
         '    "rgb Ks" [ 0.15 0.15 0.15 ] "float shininess" [ 30 ]\n',
         'MakeNamedMaterial "road" "string type" "blinnphong" "rgb Kd" [ 0.09 0.09 0.1 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "tree" "string type" "blinnphong" "rgb Kd" [ 0.2 0.5 0.2 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "trunk" "string type" "blinnphong" "rgb Kd" [ 0.4 0.28 0.16 ] "rgb Ka" [ 1 1 1 ]\n',
         'NamedMaterial "ground"\n',
         quad_shape((-64, 0, -64), (64, 0, -64), (64, 0, 64), (-64, 0, 64)),
         'NamedMaterial "road"\n']
    # roads between the house rows (slightly above the ground)
    for k in (-1, 0, 1):
        c = k * TOWN_SPACING
        s.append(quad_shape((c - 0.5, 0.005, -9), (c + 0.5, 0.005, -9), (c + 0.5, 0.005, 9), (c - 0.5, 0.005, 9)))
        s.append(quad_shape((-9, 0.006, c - 0.5), (9, 0.006, c - 0.5), (9, 0.006, c + 0.5), (-9, 0.006, c + 0.5)))
    for n, (ix, iz) in enumerate(TOWN_HOUSES):
        cx, cz = (ix + 0.5) * TOWN_SPACING, (iz + 0.5) * TOWN_SPACING
        x0, x1, z0, z1 = cx - HOUSE_W / 2, cx + HOUSE_W / 2, cz - HOUSE_D / 2, cz + HOUSE_D / 2
        s.append('NamedMaterial "%s"\n' % ("wallA" if (ix + iz) % 2 == 0 else "wallB"))
        s.append(boxes_shape([((x0, 0, z0), (x1, HOUSE_H, z1))]))
        # gable roof along x, with a small overhang
        o, y0, y1 = 0.15, HOUSE_H, HOUSE_H + ROOF_H
        a, b = (x0 - o, y0, z0 - o), (x1 + o, y0, z0 - o)
        c, d = (x1 + o, y0, z1 + o), (x0 - o, y0, z1 + o)
        r0, r1 = (x0 - o, y1, cz), (x1 + o, y1, cz)
        s.append('NamedMaterial "roof"\n')
        s.append(flat_shape([(a, r0, r1), (a, r1, b), (d, c, r1), (d, r1, r0), (a, d, r0), (b, r1, c),
                             (a, b, c), (a, c, d)]))
        # one tree in the front garden of every other house
        if n % 2 == 0:
            tx, tz = cx + 1.45, cz - 1.45
            s.append('NamedMaterial "trunk"\n' + boxes_shape([((tx - 0.08, 0, tz - 0.08), (tx + 0.08, 0.6, tz + 0.08))]))
            s.append('AttributeBegin Translate %s 1.0 %s NamedMaterial "tree" Shape "sphere" "float radius" [ 0.45 ] AttributeEnd\n'
                     % (fmt(tx), fmt(tz)))
    return "".join(s)


ISO_DIR = (1 / math.sqrt(3), 1 / math.sqrt(3), -1 / math.sqrt(3))  # isometric: equal angles to the 3 axes
TOWN_TARGET = (0.0, 0.8, 0.0)


def town_cam(kind):
    if kind == "orthographic":
        eye = tuple(TOWN_TARGET[k] + 60 * ISO_DIR[k] for k in range(3))
        return {"type": "orthographic", "eye": eye, "look": TOWN_TARGET, "window": (-11.2, 11.2, -8.4, 8.4)}
    # perspective from the same direction, close enough for a comparable framing
    eye = tuple(TOWN_TARGET[k] + 17.5 * ISO_DIR[k] for k in range(3))
    return {"type": "perspective", "eye": eye, "look": TOWN_TARGET, "fov": 62}


# ---- perspective preferred: a railway to the horizon (depth from size and convergence)
RAIL_LEN = 150.0
POLE_STEP = 10.0


def railway_world():
    s = ["# Railway to the horizon: rails, sleepers, telegraph poles and wires (camera_persp).\n",
         "WorldBegin\n",
         'LightSource "distant" "point3 from" [ 6 9 -3 ] "point3 to" [ 0 0 0 ] "rgb L" [ 1.1 1.0 0.88 ]\n',
         'LightSource "infinite" "rgb L" [ 0.5 0.62 0.85 ]\n',
         'Texture "grass" "spectrum" "checkerboard" "float uscale" [ 300 ] "float vscale" [ 300 ]\n'
         '    "rgb tex1" [ 0.32 0.45 0.2 ] "rgb tex2" [ 0.28 0.4 0.18 ]\n',
         'MakeNamedMaterial "grass" "string type" "blinnphong" "texture Kd" "grass" "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "ballast" "string type" "blinnphong" "rgb Kd" [ 0.45 0.43 0.4 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "steel" "string type" "blinnphong" "rgb Kd" [ 0.35 0.33 0.32 ] "rgb Ka" [ 1 1 1 ]\n'
         '    "rgb Ks" [ 0.6 0.6 0.6 ] "float shininess" [ 80 ]\n',
         'MakeNamedMaterial "sleeper" "string type" "blinnphong" "rgb Kd" [ 0.36 0.24 0.14 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "pole" "string type" "blinnphong" "rgb Kd" [ 0.42 0.3 0.2 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "wire" "string type" "blinnphong" "rgb Kd" [ 0.1 0.1 0.1 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "platform" "string type" "blinnphong" "rgb Kd" [ 0.7 0.68 0.64 ] "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "shelter" "string type" "blinnphong" "rgb Kd" [ 0.55 0.15 0.12 ] "rgb Ka" [ 1 1 1 ]\n',
         'NamedMaterial "grass"\n',
         quad_shape((-400, 0, -20), (400, 0, -20), (400, 0, 600), (-400, 0, 600)),
         'NamedMaterial "ballast"\n',
         quad_shape((-1.6, 0.02, -20), (1.6, 0.02, -20), (1.6, 0.02, RAIL_LEN + 300), (-1.6, 0.02, RAIL_LEN + 300)),
         'NamedMaterial "steel"\n']
    for x in (-0.72, 0.72):
        s.append(boxes_shape([((x - 0.035, 0.12, -20), (x + 0.035, 0.27, RAIL_LEN + 300))]))
    s.append('NamedMaterial "sleeper"\n')
    z = -6.0
    chunk = []
    while z < RAIL_LEN:
        chunk.append(((-1.25, 0.02, z - 0.12), (1.25, 0.12, z + 0.12)))
        if len(chunk) == 20:
            s.append(boxes_shape(chunk))
            chunk = []
        z += 0.65
    if chunk:
        s.append(boxes_shape(chunk))
    # telegraph poles on the left, wires between their crossbars
    poles = [k * POLE_STEP for k in range(int(RAIL_LEN / POLE_STEP) + 1)]
    px = -3.2
    for zp in poles:
        s.append('NamedMaterial "pole"\n' + boxes_shape([((px - 0.09, 0, zp - 0.09), (px + 0.09, 5.2, zp + 0.09)),
                                                          ((px - 0.7, 4.8, zp - 0.06), (px + 0.7, 4.92, zp + 0.06))]))
    s.append('NamedMaterial "wire"\n')
    wires = []
    for wx in (px - 0.55, px + 0.55):
        for i in range(len(poles) - 1):
            wires.append(((wx - 0.012, 4.95, poles[i]), (wx + 0.012, 4.975, poles[i + 1])))
    s.append(boxes_shape(wires))
    # a platform with a shelter on the right, 30 units ahead
    s.append('NamedMaterial "platform"\n' + boxes_shape([((2.0, 0, 26), (5.5, 0.9, 52))]))
    s.append('NamedMaterial "shelter"\n' + boxes_shape([((3.8, 0.9, 34), (5.3, 3.2, 40)), ((3.6, 3.2, 33.6), (5.5, 3.35, 40.4))]))
    return "".join(s)


RAIL_EYE, RAIL_LOOK = (4.5, 2.2, -5.0), (-1.5, 1.4, 30.0)


def railway_cam(kind):
    if kind == "orthographic":
        # same position and direction; the window starts above the ground (rays are parallel)
        return {"type": "orthographic", "eye": RAIL_EYE, "look": RAIL_LOOK, "window": (-5.0, 5.0, -2.1, 5.4)}
    return {"type": "perspective", "eye": RAIL_EYE, "look": RAIL_LOOK, "fov": 45}


# ---- field of view: a gallery of identical spheres
GALLERY_RED = (0.0, 0.5, 4.0)
GALLERY_X = [-6, -4, -2, 0, 2, 4, 6]
GALLERY_Z = [0, 2, 4, 6, 8]
GALLERY_EYE, GALLERY_LOOK = (0.0, 1.6, -6.0), (0.0, 0.9, 4.0)


def gallery_world():
    cols = [(0.2, 0.45, 0.8), (0.9, 0.75, 0.2), (0.3, 0.7, 0.35), (0.95, 0.95, 0.95), (0.6, 0.35, 0.75)]
    s = ["# Gallery of identical spheres (radius 0.5) on a 1-unit checker floor in front of a gridded wall\n"
         "# (camera_fov1/2/3). The red sphere at (0, 0.5, 4) is the reference subject.\n",
         "WorldBegin\n",
         'LightSource "distant" "point3 from" [ -3 8 -5 ] "point3 to" [ 0 0 0 ] "rgb L" [ 0.9 0.9 0.88 ]\n',
         'LightSource "point" "point3 from" [ 4 6 -4 ] "rgb I" [ 30 30 30 ]\n',
         'Texture "floor" "spectrum" "checkerboard" "float uscale" [ 20 ] "float vscale" [ 20 ]\n'
         '    "rgb tex1" [ 0.82 0.82 0.8 ] "rgb tex2" [ 0.3 0.3 0.32 ]\n',
         'Texture "wall" "spectrum" "checkerboard" "float uscale" [ 24 ] "float vscale" [ 12 ]\n'
         '    "rgb tex1" [ 0.75 0.7 0.62 ] "rgb tex2" [ 0.6 0.55 0.48 ]\n',
         'MakeNamedMaterial "floor" "string type" "blinnphong" "texture Kd" "floor" "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "wall" "string type" "blinnphong" "texture Kd" "wall" "rgb Ka" [ 1 1 1 ]\n',
         'MakeNamedMaterial "red" "string type" "blinnphong" "rgb Kd" [ 0.8 0.08 0.06 ] "rgb Ka" [ 1 1 1 ]\n'
         '    "rgb Ks" [ 0.2 0.2 0.2 ] "float shininess" [ 60 ]\n']
    for i, c in enumerate(cols):
        s.append('MakeNamedMaterial "c%d" "string type" "blinnphong" "rgb Kd" [ %s ] "rgb Ka" [ 1 1 1 ]\n'
                 '    "rgb Ks" [ 0.15 0.15 0.15 ] "float shininess" [ 60 ]\n' % (i, vec([0.85 * v for v in c])))
    s.append('NamedMaterial "floor"\n' + quad_shape((-30, 0, -20), (30, 0, -20), (30, 0, 10), (-30, 0, 10),
                                                     uv=((0, 0), (3, 0), (3, 1.5), (0, 1.5))))
    # back wall: 60 x 20 units, cells of 1 unit
    s.append('NamedMaterial "wall"\n' + quad_shape((-30, 0, 10), (30, 0, 10), (30, 20, 10), (-30, 20, 10),
                                                    uv=((0, 0), (2.5, 0), (2.5, 1 + 2 / 3), (0, 1 + 2 / 3))))
    k = 0
    for z in GALLERY_Z:
        for x in GALLERY_X:
            if x == 0 and z < GALLERY_RED[2]:
                continue  # keep the line of sight to the reference sphere free
            if (x, z) == (GALLERY_RED[0], GALLERY_RED[2]):
                m = "red"
            else:
                m = "c%d" % (k % len(cols))
                k += 1
            s.append('AttributeBegin Translate %s 0.5 %s NamedMaterial "%s" Shape "sphere" "float radius" [ 0.5 ] AttributeEnd\n'
                     % (fmt(x), fmt(z), m))
    # two spheres close to the camera, near the edges of the wide view
    for x in (-3.0, 3.0):
        s.append('AttributeBegin Translate %s 0.5 -3 NamedMaterial "c1" Shape "sphere" "float radius" [ 0.5 ] AttributeEnd\n' % fmt(x))
    return "".join(s)


FOVS = [("camera_fov1", 25.0), ("camera_fov2", 60.0), ("camera_fov3", 100.0)]


def gallery_cam(fov, dolly=False):
    eye = GALLERY_EYE
    if dolly:
        # keep the red sphere the same size as at 60 degrees: distance proportional to 1/tan(fov/2)
        d60 = math.dist(GALLERY_EYE, GALLERY_LOOK)
        d = d60 * math.tan(math.radians(30)) / math.tan(math.radians(fov / 2))
        u = [(GALLERY_EYE[k] - GALLERY_LOOK[k]) / d60 for k in range(3)]
        eye = tuple(GALLERY_LOOK[k] + d * u[k] for k in range(3))
    return {"type": "perspective", "eye": eye, "look": GALLERY_LOOK, "fov": fov}


# ================================================================ 2.2.2 antialiasing
# (The shared worlds use procedural textures only: relative file names in an Include are
# resolved against the directory of the scene file, as in pbrt-v4, and the Module 2 scene
# files live at different depths.)
def ribbon(p0, p1, width, eye):
    """Two triangles along the segment p0-p1, turned to face the eye (a thin wire)."""
    d = [p1[k] - p0[k] for k in range(3)]
    m = [(p0[k] + p1[k]) / 2 - eye[k] for k in range(3)]
    n = mp.normalize3(mp.tri_normal((0, 0, 0), d, m))
    o = [n[k] * width / 2 for k in range(3)]
    a = tuple(p0[k] - o[k] for k in range(3)); b = tuple(p1[k] - o[k] for k in range(3))
    c = tuple(p1[k] + o[k] for k in range(3)); e = tuple(p0[k] + o[k] for k in range(3))
    return [(a, b, c), (a, c, e)]


def garden_world():
    s = ["# Garden for the antialiasing study: a checker lawn running to the horizon (moire), a picket\n"
         "# fence, power lines thinner than a pixel, a spoked wheel and a finely striped ball.\n",
         "WorldBegin\n",
         'LightSource "distant" "point3 from" [ -6 9 -4 ] "point3 to" [ 0 0 0 ] "rgb L" [ 2.6 2.5 2.3 ]\n',
         'LightSource "infinite" "rgb L" [ 0.45 0.58 0.85 ]\n',
         'Texture "lawn" "spectrum" "checkerboard" "float uscale" [ 1200 ] "float vscale" [ 1200 ]\n'
         '    "rgb tex1" [ 0.75 0.8 0.7 ] "rgb tex2" [ 0.12 0.25 0.1 ]\n',
         'Texture "stripes" "spectrum" "checkerboard" "float uscale" [ 48 ] "float vscale" [ 24 ]\n'
         '    "rgb tex1" [ 0.9 0.9 0.88 ] "rgb tex2" [ 0.08 0.1 0.35 ]\n',
         'Texture "grid" "spectrum" "checkerboard" "float uscale" [ 10 ] "float vscale" [ 10 ]\n'
         '    "rgb tex1" [ 0.85 0.6 0.25 ] "rgb tex2" [ 0.25 0.15 0.08 ]\n',
         'MakeNamedMaterial "lawn" "string type" "phong" "texture Kd" "lawn" "rgb Ka" [ 0.6 0.6 0.6 ]\n',
         'MakeNamedMaterial "paint" "string type" "phong" "rgb Kd" [ 0.92 0.92 0.9 ] "rgb Ka" [ 0.6 0.6 0.6 ]\n',
         'MakeNamedMaterial "post" "string type" "phong" "rgb Kd" [ 0.45 0.32 0.2 ] "rgb Ka" [ 0.6 0.6 0.6 ]\n',
         'MakeNamedMaterial "wire" "string type" "phong" "rgb Kd" [ 0.05 0.05 0.05 ] "rgb Ka" [ 0.6 0.6 0.6 ]\n',
         'MakeNamedMaterial "rim" "string type" "phong" "rgb Kd" [ 0.3 0.3 0.32 ] "rgb Ka" [ 0.6 0.6 0.6 ]\n'
         '    "rgb Ks" [ 0.6 0.6 0.6 ] "float exponent" [ 60 ]\n',
         'MakeNamedMaterial "spoke" "string type" "phong" "rgb Kd" [ 0.65 0.65 0.68 ] "rgb Ka" [ 0.6 0.6 0.6 ]\n'
         '    "rgb Ks" [ 0.3 0.3 0.3 ] "float exponent" [ 40 ]\n',
         'MakeNamedMaterial "ball" "string type" "phong" "texture Kd" "stripes" "rgb Ka" [ 0.6 0.6 0.6 ]\n'
         '    "rgb Ks" [ 0.3 0.3 0.3 ] "float exponent" [ 50 ]\n',
         'MakeNamedMaterial "crate" "string type" "phong" "texture Kd" "grid" "rgb Ka" [ 0.6 0.6 0.6 ]\n',
         'NamedMaterial "lawn"\n',
         quad_shape((-300, 0, -10), (300, 0, -10), (300, 0, 590), (-300, 0, 590)),
         'NamedMaterial "paint"\n']
    # picket fence along z = 9 on the left half (the lawn runs to the horizon on the right):
    # slats 0.07 wide every 0.22
    slats, x = [], -12.0
    while x <= -0.4:
        slats.append(((x - 0.035, 0, 9.0), (x + 0.035, 1.05, 9.06)))
        x += 0.22
    slats += [((-12.1, 0.25, 8.95), (-0.3, 0.33, 9.0)), ((-12.1, 0.8, 8.95), (-0.3, 0.88, 9.0))]
    s.append(boxes_shape(slats))
    # power lines between two posts far behind the fence, thinner than a pixel at this distance
    s.append('NamedMaterial "post"\n' + boxes_shape([((-12.1, 0, 20), (-11.8, 6.2, 20.3)), ((11.8, 0, 26), (12.1, 6.2, 26.3))]))
    s.append('NamedMaterial "wire"\n')
    tris = []
    for y in (5.4, 5.75, 6.1):
        a, b = (-11.95, y, 20.15), (11.95, y - 0.25, 26.15)
        # a sagging wire as 12 camera-facing ribbons 0.016 wide (well below a pixel at this distance)
        pts = []
        for i in range(13):
            t = i / 12
            p = [a[j] + t * (b[j] - a[j]) for j in range(3)]
            p[1] -= 0.35 * 4 * t * (1 - t)
            pts.append(p)
        for p0, p1 in zip(pts, pts[1:]):
            tris += ribbon(p0, p1, 0.016, GARDEN_CAM["eye"])
    s.append(flat_shape(tris))
    # spoked wheel leaning on nothing, facing the camera at an angle
    wheel = ["AttributeBegin\n", "  Translate -2.2 1.0 5.0\n", "  Rotate 35 0 1 0\n",
             '  NamedMaterial "rim"\n',
             '  Shape "disk" "float radius" [ 0.95 ] "float innerradius" [ 0.86 ]\n',
             '  Shape "disk" "float radius" [ 0.09 ]\n',
             '  NamedMaterial "spoke"\n']
    tris = []
    for i in range(36):
        a = 2 * math.pi * i / 36
        w = 0.008
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa * w, ca * w
        r0, r1 = 0.08, 0.87
        p = [(r0 * ca + px, r0 * sa + py, 0.001), (r1 * ca + px, r1 * sa + py, 0.001),
             (r1 * ca - px, r1 * sa - py, 0.001), (r0 * ca - px, r0 * sa - py, 0.001)]
        tris += [(p[0], p[1], p[2]), (p[0], p[2], p[3])]
    wheel.append("  " + flat_shape(tris))
    wheel.append("AttributeEnd\n")
    s.append("".join(wheel))
    s.append('AttributeBegin Translate 2.0 0.7 4.0 Rotate -90 1 0 0 NamedMaterial "ball" Shape "sphere" "float radius" [ 0.7 ] AttributeEnd\n')
    s.append('AttributeBegin Translate 4.3 0 6.0 Rotate 25 0 1 0 NamedMaterial "crate"\n' +
             mp.box((-0.6, 0, -0.6), (0.6, 1.2, 0.6), 1 / 1.2) + 'AttributeEnd\n')
    return "".join(s)


GARDEN_CAM = {"type": "perspective", "eye": (0.0, 1.3, -3.0), "look": (0.0, 1.2, 10.0), "fov": 48}


# ================================================================ 2.2.3 sampler comparison
# Pure pbrt-v4 syntax (the same world is rendered by pbrt-v4 for the reference image).
LIGHT_C, LIGHT_W, LIGHT_D, LIGHT_Y = (0.0, 2.4), 1.6, 0.8, 3.0  # rectangle centre (x, z), size, height
SAMPLER_CAM = {"type": "perspective", "eye": (0.0, 2.6, -4.6), "look": (0.0, 0.25, 0.6), "fov": 42}
SAMPLER_RES = (640, 480)
SAMPLER_NS = [1, 4, 16, 64, 256]


def study_world(occluders=True):
    lx, lz = LIGHT_C
    hw, hd = LIGHT_W / 2, LIGHT_D / 2
    s = ["# Sampler-comparison world (pure pbrt-v4 syntax: also rendered by pbrt-v4 for the reference).\n",
         "# A 1.6 x 0.8 emissive rectangle at height 3 (edges along x and z) lights a white floor with\n",
         "# five occluders: an axis-aligned box (shadow edges parallel to the light's grid axes), a box\n",
         "# rotated by 30 degrees, a sphere, a thin pole and a grille of thin slats.\n",
         "WorldBegin\n",
         "AttributeBegin\n",
         '  AreaLightSource "diffuse" "rgb L" [ 22 22 22 ]\n',
         '  Shape "trianglemesh" "point3 P" [ %s  %s  %s  %s ] "integer indices" [ 0 1 2  0 2 3 ]\n' % (
             vec((lx - hw, LIGHT_Y, lz - hd)), vec((lx + hw, LIGHT_Y, lz - hd)), vec((lx + hw, LIGHT_Y, lz + hd)),
             vec((lx - hw, LIGHT_Y, lz + hd))),
         "AttributeEnd\n",
         'Material "diffuse" "rgb reflectance" [ 0.8 0.8 0.8 ]\n',
         'Shape "trianglemesh" "point3 P" [ -30 0 -30  30 0 -30  30 0 30  -30 0 30 ] "integer indices" [ 0 2 1  0 3 2 ]\n']
    if not occluders:
        return "".join(s)
    s += ['Material "diffuse" "rgb reflectance" [ 0.45 0.45 0.45 ]\n',
         "# (1) axis-aligned box\n", boxes_shape([((-1.95, 0, 0.0), (-1.05, 0.7, 0.7))]),
         "# (2) box rotated 30 degrees about y\n",
         "AttributeBegin Translate 1.45 0 0.35 Rotate 30 0 1 0\n", boxes_shape([((-0.45, 0, -0.35), (0.45, 0.7, 0.35))]),
         "AttributeEnd\n",
         "# (3) sphere\n",
         'AttributeBegin Translate -0.2 0.95 0.9 Shape "sphere" "float radius" [ 0.42 ] AttributeEnd\n',
         "# (4) thin pole on a small base\n",
         boxes_shape([((0.62, 0, -0.62), (0.68, 1.5, -0.56)), ((0.5, 0, -0.74), (0.8, 0.04, -0.44))]),
         "# (5) grille: seven thin slats on two legs, 0.75 above the floor\n"]
    slats = [((-1.35 + 0.16 * i, 0.75, -1.05), (-1.30 + 0.16 * i, 0.79, -0.25)) for i in range(7)]
    slats += [((-1.4, 0, -1.08), (-1.36, 0.75, -1.04)), ((-0.36, 0, -0.26), (-0.32, 0.75, -0.22))]
    s.append(boxes_shape(slats))
    return "".join(s)


def study_pbrt_header(spp):
    cam = SAMPLER_CAM
    return ("# pbrt-v4 reference for the sampler comparison: the same camera and world as sampler_*.pbrt.\n"
            "# Point sampling at the pixel centre (box filter of radius 1e-4), direct light only\n"
            "# (path, maxdepth 1), %d low-discrepancy samples per pixel.\n"
            "# Render: pbrt --outfile sampler_ref_pbrt.pfm sampler_ref_pbrt.pbrt\n" % spp +
            lookat(cam["eye"], cam["look"]) + 'Camera "perspective" "float fov" [ %s ]\n' % fmt(cam["fov"]) +
            'Film "rgb" "integer xresolution" [ %d ] "integer yresolution" [ %d ] "string filename" [ "sampler_ref_pbrt.pfm" ]\n'
            % SAMPLER_RES +
            'Sampler "zsobol" "integer pixelsamples" [ %d ]\n' % spp +
            'PixelFilter "box" "float xradius" [ 0.0001 ] "float yradius" [ 0.0001 ]\n' +
            'Integrator "path" "integer maxdepth" [ 1 ]\n\n')


# ================================================================ 2.2.4 DRT parameter study
def chess_piece_profiles():
    """(r, y) profiles, bottom centre to top centre, radius ~0.35 base."""
    def base(r=0.36):
        return [(0.0, 0.0), (r, 0.0), (r, 0.05), (r * 0.92, 0.09), (r * 0.8, 0.12)]
    pawn = base() + [(0.17, 0.2), (0.12, 0.42), (0.17, 0.46), (0.17, 0.49), (0.1, 0.52)]
    pawn += [(0.15 * math.sin(math.pi * t / 8) + 0.0, 0.52 + 0.15 * (1 - math.cos(math.pi * t / 8))) for t in range(1, 9)]
    pawn[-1] = (0.0, pawn[-1][1])
    rook = base(0.38) + [(0.22, 0.2), (0.19, 0.6), (0.27, 0.66), (0.27, 0.82), (0.19, 0.82), (0.19, 0.76), (0.0, 0.76)]
    king = base(0.4) + [(0.22, 0.22), (0.15, 0.72), (0.24, 0.78), (0.24, 0.82), (0.16, 0.86), (0.21, 1.02), (0.12, 1.06),
                        (0.06, 1.06), (0.06, 1.2), (0.0, 1.2)]
    queen = base(0.4) + [(0.21, 0.22), (0.14, 0.68), (0.23, 0.74), (0.23, 0.78), (0.15, 0.82), (0.24, 0.98), (0.18, 1.0)]
    queen += [(0.18 * math.cos(math.pi / 2 * t / 6), 1.0 + 0.1 * math.sin(math.pi / 2 * t / 6)) for t in range(1, 7)]
    queen[-1] = (0.0, queen[-1][1])
    bishop = base(0.37) + [(0.19, 0.2), (0.12, 0.58), (0.2, 0.62), (0.13, 0.66)]
    bishop += [(0.16 * math.sin(math.pi * t / 10) + 0.0, 0.66 + 0.3 * (1 - math.cos(math.pi * t / 10)) / 2) for t in range(1, 11)]
    bishop[-1] = (0.0, bishop[-1][1])
    return {"pawn": pawn, "rook": rook, "king": king, "queen": queen, "bishop": bishop}


def chess_world():
    prof = chess_piece_profiles()
    s = ["# Chess endgame under a spotlight in a dark room (param_small_low): direct light dominates,\n"
         "# the open dark surroundings return little indirect light.\n",
         "WorldBegin\n",
         'LightSource "spot" "point3 from" [ -2.5 7 -4.5 ] "point3 to" [ 0 0 0.5 ] "float coneangle" [ 32 ]\n'
         '    "float conedeltaangle" [ 6 ] "rgb I" [ 70 66 58 ]\n',
         'LightSource "point" "point3 from" [ 5 3 -2 ] "rgb I" [ 2.2 2.4 3 ]\n',
         'Texture "board" "spectrum" "checkerboard" "float uscale" [ 8 ] "float vscale" [ 8 ]\n'
         '    "rgb tex1" [ 0.72 0.62 0.45 ] "rgb tex2" [ 0.2 0.12 0.07 ]\n',
         'MakeNamedMaterial "board" "string type" "phong" "texture Kd" "board" "rgb Ks" [ 0.03 0.03 0.03 ] "float exponent" [ 12 ]\n',
         'MakeNamedMaterial "frame" "string type" "diffuse" "rgb reflectance" [ 0.25 0.14 0.08 ]\n',
         'MakeNamedMaterial "floor" "string type" "diffuse" "rgb reflectance" [ 0.06 0.06 0.07 ]\n',
         'MakeNamedMaterial "ivory" "string type" "phong" "rgb Kd" [ 0.75 0.7 0.6 ] "rgb Ks" [ 0.04 0.04 0.04 ] "float exponent" [ 12 ]\n',
         'MakeNamedMaterial "ebony" "string type" "phong" "rgb Kd" [ 0.07 0.06 0.06 ] "rgb Ks" [ 0.04 0.04 0.04 ] "float exponent" [ 12 ]\n',
         'NamedMaterial "floor"\n', quad_shape((-30, 0, -30), (30, 0, -30), (30, 0, 30), (-30, 0, 30)),
         'NamedMaterial "frame"\n', boxes_shape([((-4.4, 0, -4.4), (4.4, 0.28, 4.4))]),
         'NamedMaterial "board"\n', quad_shape((-4, 0.3, -4), (4, 0.3, -4), (4, 0.3, 4), (-4, 0.3, 4)),
         ]
    # square (file f, rank r) -> centre; files a..h = x -3.5..3.5, ranks 1..8 = z -3.5..3.5
    def sq(f, r):
        return ("abcdefgh".index(f) - 3.5, 0.3, r - 4.5)
    pieces = [("king", "ivory", "g", 1), ("rook", "ivory", "e", 1), ("pawn", "ivory", "f", 2), ("pawn", "ivory", "g", 2),
              ("pawn", "ivory", "h", 3), ("queen", "ivory", "d", 4),
              ("king", "ebony", "g", 8), ("rook", "ebony", "c", 8), ("bishop", "ebony", "e", 6), ("pawn", "ebony", "f", 7),
              ("pawn", "ebony", "g", 6), ("pawn", "ebony", "h", 7), ("queen", "ebony", "b", 3)]
    meshes = {k: lathe_mesh(v, 28) for k, v in prof.items()}
    for kind, mat, f, r in pieces:
        x, y, z = sq(f, r)
        s.append('AttributeBegin Translate %s %s %s Scale 1.25 1.25 1.25 NamedMaterial "%s"\n' % (fmt(x), fmt(y), fmt(z), mat))
        s.append(mesh_shape(meshes[kind]) + "AttributeEnd\n")
    return "".join(s)


CHESS_CAM = {"type": "perspective", "eye": (3.6, 4.6, -7.8), "look": (0.4, 0.5, 0.6), "fov": 38}


def mirrors_world():
    s = ["# Hall of mirrors (param_small_high): two parallel mirrors 6 units apart, a glass sphere, a\n"
         "# torus and point lights. Every further reflection needs one more level of the ray tree,\n"
         "# while specular bounces never branch.\n",
         "WorldBegin\n",
         'LightSource "point" "point3 from" [ 0.8 3.4 1.0 ] "rgb I" [ 9 8.6 8 ]\n',
         'LightSource "point" "point3 from" [ -1.5 2.2 -1.0 ] "rgb I" [ 3 3.2 4 ]\n',
         'Texture "tiles" "spectrum" "checkerboard" "float uscale" [ 12 ] "float vscale" [ 12 ]\n'
         '    "rgb tex1" [ 0.6 0.58 0.55 ] "rgb tex2" [ 0.12 0.12 0.14 ]\n',
         'MakeNamedMaterial "tiles" "string type" "diffuse" "texture reflectance" "tiles"\n',
         'MakeNamedMaterial "wall" "string type" "diffuse" "rgb reflectance" [ 0.18 0.2 0.24 ]\n',
         'MakeNamedMaterial "mirror" "string type" "mirror" "rgb Kr" [ 0.92 0.92 0.92 ]\n',
         'MakeNamedMaterial "frame" "string type" "diffuse" "rgb reflectance" [ 0.35 0.25 0.12 ]\n',
         'MakeNamedMaterial "glass" "string type" "dielectric" "float eta" [ 1.5 ]\n',
         'MakeNamedMaterial "red" "string type" "phong" "rgb Kd" [ 0.7 0.08 0.06 ] "rgb Ks" [ 0.05 0.05 0.05 ] "float exponent" [ 10 ]\n',
         'MakeNamedMaterial "gold" "string type" "phong" "rgb Kd" [ 0.6 0.44 0.12 ] "rgb Ks" [ 0.05 0.05 0.05 ] "float exponent" [ 10 ]\n',
         'NamedMaterial "tiles"\n', quad_shape((-3, 0, -6), (3, 0, -6), (3, 0, 6), (-3, 0, 6)),
         'NamedMaterial "wall"\n', quad_shape((-3, 0, 6), (3, 0, 6), (3, 4, 6), (-3, 4, 6)),
         quad_shape((3, 0, -6), (-3, 0, -6), (-3, 4, -6), (3, 4, -6)),
         quad_shape((-3, 4, -6), (-3, 4, 6), (3, 4, 6), (3, 4, -6)),
         'NamedMaterial "mirror"\n',
         quad_shape((-2.99, 0.3, -5.5), (-2.99, 0.3, 5.5), (-2.99, 3.6, 5.5), (-2.99, 3.6, -5.5)),
         quad_shape((2.99, 0.3, 5.5), (2.99, 0.3, -5.5), (2.99, 3.6, -5.5), (2.99, 3.6, 5.5)),
         'NamedMaterial "frame"\n',
         boxes_shape([((-3, 0, -6), (-2.9, 0.3, 6)), ((2.9, 0, -6), (3, 0.3, 6)),
                      ((-3, 3.6, -6), (-2.9, 4, 6)), ((2.9, 3.6, -6), (3, 4, 6))]),
         'NamedMaterial "frame"\n', boxes_shape([((-0.35, 0, 1.15), (0.35, 0.8, 1.85))]),
         'AttributeBegin Translate 0 1.3 1.5 NamedMaterial "glass" Shape "sphere" "float radius" [ 0.5 ] AttributeEnd\n',
         'AttributeBegin Translate -0.9 0.32 -0.2 Rotate 20 1 0 0 NamedMaterial "red"\n',
         mesh_shape(torus_mesh(0.55, 0.2, 40, 16)), "AttributeEnd\n",
         'AttributeBegin Translate 1.1 0.45 0.2 NamedMaterial "gold" Shape "sphere" "float radius" [ 0.45 ] AttributeEnd\n']
    return "".join(s)


MIRROR_CAM = {"type": "perspective", "eye": (2.0, 1.65, -2.2), "look": (-3.0, 1.35, 0.9), "fov": 50}


def sculpture_world():
    urn = [(0.0, 0.0), (0.45, 0.0), (0.45, 0.08), (0.3, 0.16), (0.42, 0.45), (0.55, 0.85), (0.5, 1.15), (0.3, 1.35),
           (0.32, 1.45), (0.4, 1.5), (0.0, 1.5)]
    s = ["# Sculpture court under an overcast sky (param_large_low): all light comes from the sky, which\n"
         "# the DRT gathers with the BF hemisphere rays of the first bounce; the open court returns little.\n",
         "WorldBegin\n",
         'LightSource "infinite" "rgb L" [ 1 1 1 ]\n',
         'MakeNamedMaterial "gravel" "string type" "diffuse" "rgb reflectance" [ 0.32 0.3 0.27 ]\n',
         'MakeNamedMaterial "stone" "string type" "diffuse" "rgb reflectance" [ 0.62 0.6 0.56 ]\n',
         'MakeNamedMaterial "bronze" "string type" "phong" "rgb Kd" [ 0.35 0.22 0.1 ] "rgb Ks" [ 0.25 0.2 0.12 ] "float exponent" [ 12 ]\n',
         'MakeNamedMaterial "marble" "string type" "diffuse" "rgb reflectance" [ 0.8 0.79 0.76 ]\n',
         'NamedMaterial "gravel"\n', quad_shape((-40, 0, -40), (40, 0, -40), (40, 0, 40), (-40, 0, 40)),
         '# trilithon (two uprights and a lintel), with a gap that shades the ground under it\n',
         'NamedMaterial "stone"\n',
         boxes_shape([((-3.6, 0, 1.6), (-2.9, 2.4, 2.2)), ((-1.9, 0, 1.6), (-1.2, 2.4, 2.2)), ((-3.8, 2.4, 1.5), (-1.0, 2.85, 2.3))]),
         '# low wall with niches behind the sculptures\n',
         boxes_shape([((-6, 0, 4.5), (6, 1.6, 5.0))]),
         'NamedMaterial "marble"\n',
         'AttributeBegin Translate 0.4 0 1.2\n', mesh_shape(lathe_mesh(urn, 36)), 'AttributeEnd\n',
         'AttributeBegin Translate 2.6 0.75 0.6 Rotate 70 1 0 0 NamedMaterial "bronze"\n',
         mesh_shape(torus_mesh(0.62, 0.22, 36, 14)), 'AttributeEnd\n',
         '# plinth with a sphere, and a bench\n',
         'NamedMaterial "stone"\n', boxes_shape([((2.2, 0, 2.6), (3.2, 0.6, 3.6)), ((-1.2, 0, -1.0), (0.4, 0.42, -0.6)),
                                                ((-1.15, 0, -0.95), (-1.0, 0.42, -0.65))]),
         'AttributeBegin Translate 2.7 1.1 3.1 NamedMaterial "marble" Shape "sphere" "float radius" [ 0.5 ] AttributeEnd\n']
    return "".join(s)


SCULPT_CAM = {"type": "perspective", "eye": (1.2, 2.3, -5.6), "look": (0.0, 1.0, 1.8), "fov": 48}


def room_world():
    vase = [(0.0, 0.0), (0.22, 0.0), (0.3, 0.2), (0.34, 0.45), (0.22, 0.75), (0.15, 0.95), (0.19, 1.05), (0.0, 1.05)]
    W, H, D = 3.0, 3.0, 4.0
    s = ["# Indirectly lit room (param_large_high): a closed room whose only light, a floor lamp, shines\n"
         "# up at the ceiling (60-degree cone). Everything else is lit by light bounced several times between walls\n"
         "# that reflect 50-75 %, with colour bleeding from the red and green walls.\n",
         "WorldBegin\n",
         'LightSource "spot" "point3 from" [ 1.9 1.62 2.6 ] "point3 to" [ 1.9 3 2.6 ] "float coneangle" [ 60 ]\n'
         '    "float conedeltaangle" [ 10 ] "rgb I" [ 9 8.2 7 ]\n',
         'MakeNamedMaterial "white" "string type" "diffuse" "rgb reflectance" [ 0.8 0.79 0.77 ]\n',
         'MakeNamedMaterial "red" "string type" "diffuse" "rgb reflectance" [ 0.7 0.15 0.12 ]\n',
         'MakeNamedMaterial "green" "string type" "diffuse" "rgb reflectance" [ 0.15 0.55 0.18 ]\n',
         'MakeNamedMaterial "floor" "string type" "diffuse" "rgb reflectance" [ 0.5 0.42 0.32 ]\n',
         'MakeNamedMaterial "metal" "string type" "phong" "rgb Kd" [ 0.2 0.2 0.22 ] "rgb Ks" [ 0.3 0.3 0.3 ] "float exponent" [ 20 ]\n',
         'MakeNamedMaterial "vase" "string type" "phong" "rgb Kd" [ 0.25 0.35 0.65 ] "rgb Ks" [ 0.15 0.15 0.15 ] "float exponent" [ 30 ]\n',
         'MakeNamedMaterial "wood" "string type" "diffuse" "rgb reflectance" [ 0.45 0.3 0.18 ]\n',
         # room faces point inwards
         'NamedMaterial "floor"\n', quad_shape((-W, 0, -D), (-W, 0, D), (W, 0, D), (W, 0, -D)),
         'NamedMaterial "white"\n', quad_shape((-W, H, -D), (W, H, -D), (W, H, D), (-W, H, D)),
         quad_shape((-W, 0, D), (-W, H, D), (W, H, D), (W, 0, D)),
         quad_shape((-W, 0, -D), (W, 0, -D), (W, H, -D), (-W, H, -D)),
         'NamedMaterial "red"\n', quad_shape((-W, 0, -D), (-W, H, -D), (-W, H, D), (-W, 0, D)),
         'NamedMaterial "green"\n', quad_shape((W, 0, -D), (W, 0, D), (W, H, D), (W, H, -D)),
         '# floor lamp: base and stem below the up-pointing spot light (no shade: a diffuse surface\n'
         '# a few centimetres from the light would make every path that reaches it a firefly)\n',
         'NamedMaterial "metal"\n', boxes_shape([((1.7, 0, 2.4), (2.1, 0.05, 2.8)), ((1.88, 0.05, 2.58), (1.92, 1.5, 2.62))]),
         '# table with a vase, and a sphere on the floor\n',
         'NamedMaterial "wood"\n',
         boxes_shape([((-1.6, 0.7, 0.6), (0.2, 0.78, 2.0)), ((-1.55, 0, 0.65), (-1.45, 0.7, 0.75)), ((0.05, 0, 0.65), (0.15, 0.7, 0.75)),
                      ((-1.55, 0, 1.85), (-1.45, 0.7, 1.95)), ((0.05, 0, 1.85), (0.15, 0.7, 1.95))]),
         'AttributeBegin Translate -0.7 0.78 1.3 NamedMaterial "vase"\n', mesh_shape(lathe_mesh(vase, 32)), 'AttributeEnd\n',
         'AttributeBegin Translate 0.9 0.45 0.2 NamedMaterial "white" Shape "sphere" "float radius" [ 0.45 ] AttributeEnd\n']
    return "".join(s)


ROOM_CAM = {"type": "perspective", "eye": (0.2, 1.55, -3.7), "look": (-0.1, 1.15, 1.8), "fov": 62}


# Parameter sweeps (study resolution; spp fixed per scene): MD sweep at fixed BF, BF sweep at
# fixed MD, and a converged reference (BF 1, deep MD, many samples per pixel).
PARAM_SWEEPS = {
    "param_small_low": {"world": "chess", "res": (400, 300), "spp": 16, "md": [1, 2, 3, 5, 8], "md_bf": 1,
                        "bf": [1, 2, 4, 16], "bf_md": 2, "ref": (1, 10, 2048)},
    "param_small_high": {"world": "mirrors", "res": (400, 300), "spp": 16, "md": [1, 2, 3, 5, 8, 12, 16, 24, 40],
                         "md_bf": 1, "bf": [1, 2, 4], "bf_md": 6, "ref": (1, 48, 256)},
    "param_large_low": {"world": "sculpture", "res": (400, 300), "spp": 4, "md": [1, 2, 3, 4], "md_bf": 4,
                        "bf": [1, 4, 16, 64], "bf_md": 2, "ref": (1, 6, 4096)},
    "param_large_high": {"world": "room", "res": (320, 240), "spp": 4, "md": [1, 2, 3, 4, 6, 8], "md_bf": 2,
                         "bf": [1, 2, 3, 4, 6], "bf_md": 6, "ref": (1, 20, 4096)},
}


# ================================================================ writing everything
def main():
    # ---------------- worlds
    worlds = {"town": town_world(), "railway": railway_world(), "gallery": gallery_world(), "garden": garden_world(),
              "study": study_world(), "study_open": study_world(occluders=False), "chess": chess_world(), "mirrors": mirrors_world(), "sculpture": sculpture_world(),
              "room": room_world()}
    inc = {}
    for k, text in worlds.items():
        inc[k] = os.path.join(INC, "m2_%s.pbrt" % k)
        write(inc[k], "# Generated by scenes/tools/make_module2_scenes.py\n" + text)
        print("wrote %s" % rel(inc[k]))

    # ---------------- 2.2.1 camera
    res = (800, 600)
    c = town_cam("orthographic")
    scene_file(os.path.join(SCENES, "camera_ortho.pbrt"),
               "Module 2, 2.2.1: orthographic projection, isometric view of a town block of identical\n"
               "houses. Parallel edges stay parallel and every house has the same size in the image.", c, res,
               "camera_ortho", stratified(3), whitted(2), inc["town"])
    register("camera_ortho", c, res, [
        ("near house: same size", (2 * TOWN_SPACING - TOWN_SPACING * 1.5, 1.0, -TOWN_SPACING * 1.5), 0.06, (-1, 1)),
        ("far house: same size", (-TOWN_SPACING * 1.5, 1.0, TOWN_SPACING * 1.5), 0.06, (1, -1)),
        ("streets stay parallel: no vanishing point", (8.4, 0.0, 0.0), 0.04, (1, 1))])
    c = town_cam("perspective")
    scene_file(os.path.join(M2, "camera", "camera_ortho_as_persp.pbrt"),
               "Module 2, 2.2.1: the town block of camera_ortho through a perspective camera from the same\n"
               "direction: near houses are drawn larger than far ones and parallel streets converge.", c, res,
               "camera_ortho_as_persp", stratified(3), whitted(2), inc["town"])
    register("camera_ortho_as_persp", c, res, [
        ("near house: larger", (TOWN_SPACING * 0.5, 1.0, -TOWN_SPACING * 1.5), 0.08, (-1, 1)),
        ("far house: smaller", (-TOWN_SPACING * 1.5, 1.0, TOWN_SPACING * 1.5), 0.05, (1, -1))])
    c = railway_cam("perspective")
    scene_file(os.path.join(SCENES, "camera_persp.pbrt"),
               "Module 2, 2.2.1: perspective projection of a railway running to the horizon: the rails meet\n"
               "at a vanishing point and the poles shrink with distance, which conveys depth.", c, res,
               "camera_persp", stratified(3), whitted(2), inc["railway"])
    register("camera_persp", c, res, [
        ("rails converge to a vanishing point", (0.0, 0.2, 140.0), 0.04, (1, 1)),
        ("poles shrink as 1/z", (-3.2, 3.0, 40.0), 0.05, (0, -1)),
        ("near pole", (-3.2, 2.6, 10.0), 0.06, (-1, 1))])
    c = railway_cam("orthographic")
    scene_file(os.path.join(M2, "camera", "camera_persp_as_ortho.pbrt"),
               "Module 2, 2.2.1: the railway of camera_persp through an orthographic camera from the same\n"
               "position and direction: all poles have the same size and the depth cues disappear.", c, res,
               "camera_persp_as_ortho", stratified(3), whitted(2), inc["railway"])
    register("camera_persp_as_ortho", c, res, [])
    for name, fov in FOVS:
        c = gallery_cam(fov)
        scene_file(os.path.join(SCENES, name + ".pbrt"),
                   "Module 2, 2.2.1: field of view %g degrees (vertical: the shorter image axis), camera fixed at\n"
                   "(0, 1.6, -6). The red sphere (0, 0.5, 4) is the reference subject." % fov, c, res, name,
                   stratified(3), whitted(2), inc["gallery"])
        register(name, c, res, [("reference sphere", GALLERY_RED, 0.05, (1, -1))], {"fov": fov})
        cd = gallery_cam(fov, dolly=True)
        scene_file(os.path.join(M2, "camera", name + "_dolly.pbrt"),
                   "Module 2, 2.2.1: field of view %g degrees with the camera moved along the view axis so that the\n"
                   "red reference sphere keeps its size from the 60-degree view (dolly zoom)." % fov, cd, res,
                   name + "_dolly", stratified(3), whitted(2), inc["gallery"])
        register(name + "_dolly", cd, res, [("reference sphere", GALLERY_RED, 0.05, (1, -1))], {"fov": fov})

    # ---------------- 2.2.2 antialiasing
    res = (800, 600)
    c = GARDEN_CAM
    scene_file(os.path.join(SCENES, "aa_wsrt.pbrt"),
               "Module 2, 2.2.2: aliasing in the WSRT. One ray through each pixel centre: the fence, wires,\n"
               "spokes and the checker lawn are sampled below their Nyquist rate.", c, res, "aa_wsrt",
               independent(1), whitted(3), inc["garden"])
    scene_file(os.path.join(SCENES, "aa_drt.pbrt"),
               "Module 2, 2.2.2: aliasing in the DRT. One camera ray per pixel centre, but 32 indirect rays per\n"
               "bounce: the shading is smooth, the geometry and texture edges still alias.", c, res, "aa_drt",
               independent(1), distributed(2, bf=32, ls=1), inc["garden"],
               ' "string tonemap" "reinhard" "float whitepoint" [ 3 ]')
    garden_callouts = [("moire on the checker lawn", (9.0, 0.0, 70.0), 0.07, (-1, 1)),
                       ("broken power lines (thinner than a pixel)", (0.0, 5.2, 23.2), 0.06, (-1, -1)),
                       ("picket fence: slats merge and alias", (-5.0, 0.6, 9.0), 0.06, (-1, 1)),
                       ("spokes: jagged and broken", (-2.2, 1.35, 5.0), 0.06, (0, 1)),
                       ("checkered ball: texture aliasing", (2.0, 0.7, 4.0), 0.06, (1, -1)),
                       ("jagged silhouette edges (crate)", (4.3, 1.2, 6.0), 0.05, (1, 1))]
    register("aa_wsrt", c, res, garden_callouts)
    register("aa_drt", c, res, garden_callouts)
    for n in (1, 2, 3, 4):
        name = "aa_ss%d" % (n * n)
        sampler = independent(1) if n == 1 else stratified(n)
        scene_file(os.path.join(SCENES, name + ".pbrt"),
                   "Module 2, 2.2.2: supersampling with %d sample(s) per pixel (%s), averaged with equal weights." %
                   (n * n, "the pixel centre" if n == 1 else "%dx%d jittered strata" % (n, n)), c, res, name, sampler,
                   whitted(3), inc["garden"])
        register(name, c, res, garden_callouts, {"spp": n * n})
    # supplementary: regular-grid and random supersampling, and a converged reference
    for n in (2, 4):
        for kind in ("regular", "random"):
            name = "aa_ss%d_%s" % (n * n, kind)
            smp = stratified(n, jitter=False) if kind == "regular" else independent(n * n)
            scene_file(os.path.join(M2, "aa", name + ".pbrt"),
                       "Module 2, 2.2.2: %d samples per pixel placed %s." % (
                           n * n, "at the centres of a %dx%d grid (no jitter)" % (n, n) if kind == "regular" else "uniformly at random"),
                       c, res, name, smp, whitted(3), inc["garden"])
            register(name, c, res, garden_callouts, {"spp": n * n})
    scene_file(os.path.join(M2, "aa", "aa_ref.pbrt"),
               "Module 2, 2.2.2: converged reference for the antialiasing errors (32x32 jittered strata).", c, res,
               "aa_ref", stratified(32), whitted(3), inc["garden"])
    register("aa_ref", c, res, garden_callouts)

    # ---------------- 2.2.3 sampler comparison
    res = SAMPLER_RES
    c = SAMPLER_CAM
    lx, lz = LIGHT_C
    sampler_callouts = [("axis-aligned box: edges parallel to the light grid", (-1.5, 0.0, -0.25), 0.07, (-1, -1)),
                        ("rotated box", (1.15, 0.0, -0.25), 0.07, (1, -1)),
                        ("sphere: curved penumbra", (-0.15, 0.0, 0.0), 0.06, (0, -1)),
                        ("thin pole: narrow penumbra", (0.86, 0.0, -1.55), 0.05, (1, 1)),
                        ("grille: overlapping penumbrae", (-0.95, 0.0, -1.75), 0.07, (-1, 1))]
    for strat, tag in (("uniform", "unif"), ("grid", "grid"), ("halton", "halton"), ("stratified", "strat")):
        for n in SAMPLER_NS:
            name = "sampler_%s_%d" % (tag, n)
            path = os.path.join(SCENES, name + ".pbrt") if tag != "strat" and n in (4, 16, 64) else \
                os.path.join(M2, "sampler", name + ".pbrt")
            scene_file(path,
                       "Module 2, 2.2.3: soft shadows of a rectangular area light with %d %s light sample(s) per\n"
                       "shading point. One camera ray through each pixel centre and direct light only (maxdepth 1),\n"
                       "so the light samples are the only source of error." % (n, strat), c, res, name, independent(1),
                       distributed(1, bf=1, ls=n, sampling=strat), inc["study"], TONEMAP_NONE)
            register(name, c, res, sampler_callouts, {"lightsamples": n, "lightsampling": strat})
    name = "sampler_unoccluded"
    scene_file(os.path.join(M2, "sampler", name + ".pbrt"),
               "Module 2, 2.2.3: the sampler scene without its occluders (16384 stratified light samples): the\n"
               "unshadowed floor, used to find the penumbra pixels (0.02 < visible fraction < 0.98).", c, res, name,
               independent(1), distributed(1, bf=1, ls=16384, sampling="stratified"), inc["study_open"], TONEMAP_NONE)
    register(name, c, res, [])
    name = "sampler_ref_ours"
    scene_file(os.path.join(M2, "sampler", name + ".pbrt"),
               "Module 2, 2.2.3: converged reference from this renderer (128 x 128 = 16384 stratified light\n"
               "samples per shading point).", c, res, name, independent(1),
               distributed(1, bf=1, ls=16384, sampling="stratified"), inc["study"], TONEMAP_NONE)
    register(name, c, res, sampler_callouts)
    pbrt_path = os.path.join(M2, "sampler", "sampler_ref_pbrt.pbrt")
    write(pbrt_path, study_pbrt_header(16384) + 'Include "%s"\n' % os.path.relpath(inc["study"], os.path.dirname(pbrt_path)))
    register("sampler_ref_pbrt", c, res, sampler_callouts)

    # ---------------- 2.2.4 DRT parameter study
    params = [
        ("param_small_low", CHESS_CAM, (800, 600), "chess", 1, 2, 16,
         "BF 1, MD 2: direct light from the spot dominates and the dark open room returns little light,\n"
         "so one indirect ray per bounce and two levels already give the converged image.",
         [("spot-lit pieces: direct light, hard shadows", (0.0, 0.8, -3.5), 0.07, (-1, 1)),
          ("dark surroundings: little indirect light", (-6.0, 0.0, 7.0), 0.06, (1, -1)),
          ("board bounce onto the pieces' undersides", (-0.5, 0.7, -0.5), 0.05, (1, -1))]),
        ("param_small_high", MIRROR_CAM, (800, 600), "mirrors", 1, 24, 32,
         "BF 1, MD 24: two facing mirrors; each further reflection needs one more level of recursion,\n"
         "but specular reflections never branch, so one ray per bounce is enough.",
         # images of the glass sphere (x = 0) seen through the left mirror (x = -3): after k
         # reflections it appears at x = -6k, alternately mirrored by the left and right mirrors
         [("1st reflection (needs MD >= 2)", (-6.0, 1.3, 1.5), 0.05, (0, -1)),
          ("2nd reflection (MD >= 3)", (-12.0, 1.3, 1.5), 0.04, (0, 1)),
          ("deep reflections need high MD", (-36.0, 1.3, 1.5), 0.04, (-1, -1)),
          ("glass sphere: refraction chain", (0.0, 1.3, 1.5), 0.05, (-1, 1))]),
        ("param_large_low", SCULPT_CAM, (800, 600), "sculpture", 32, 2, 4,
         "BF 32, MD 2: the overcast sky is the only light and is found only by the hemisphere rays;\n"
         "the open court returns little light, so two levels hold 99 % of it, but each level needs many rays.",
         [("soft sky shadow under the lintel", (-2.4, 1.0, 1.9), 0.06, (1, -1)),
          ("contact shadow of the urn", (0.4, 0.05, 0.6), 0.05, (1, 1)),
          ("large softly lit surfaces", (4.6, 1.0, 4.5), 0.06, (-1, -1))]),
        ("param_large_high", ROOM_CAM, (640, 480), "room", 4, 6, 16,
         "BF 4, MD 6: a closed room lit only by light bounced off the ceiling: several bounces carry\n"
         "most of the light (MD) and every bounce needs many rays to average it (BF).",
         [("ceiling lit by the lamp (1 bounce from the camera)", (1.9, 3.0, 2.6), 0.07, (-1, 1)),
          ("colour bleeding from the red wall", (-2.6, 0.5, 0.5), 0.06, (-1, -1)),
          ("corner lit after several bounces", (-3.0, 0.2, 4.0), 0.06, (0, -1)),
          ("shadow under the table: indirect only", (-0.7, 0.0, 1.3), 0.06, (1, 1))]),
    ]
    for name, cam, pres, world, bf, md, spp, why, callouts in params:
        scene_file(os.path.join(SCENES, name + ".pbrt"), "Module 2, 2.2.4: " + why, cam, pres, name,
                   stratified(int(round(math.sqrt(spp)))) if int(round(math.sqrt(spp))) ** 2 == spp else independent(spp),
                   distributed(md, bf=bf, ls=1), inc[world], ' "string tonemap" "reinhard"')
        register(name, cam, pres, callouts, {"bf": bf, "md": md, "spp": spp, "world": world})
    VIEWS["_params"] = {p[0]: {"world": p[3], "bf": p[4], "md": p[5], "spp": p[6], "res": list(p[2])} for p in params}
    cams = {"chess": CHESS_CAM, "mirrors": MIRROR_CAM, "sculpture": SCULPT_CAM, "room": ROOM_CAM}
    sweeps = {}
    for out, sw in PARAM_SWEEPS.items():
        world = sw["world"]
        cam = cams[world]
        points = sorted(set([(sw["md_bf"], m) for m in sw["md"]] + [(b, sw["bf_md"]) for b in sw["bf"]]))
        files = []
        for bf, md in points:
            name = "%s_bf%d_md%d" % (world, bf, md)
            scene_file(os.path.join(M2, "param", name + ".pbrt"),
                       "Module 2, 2.2.4 sweep for %s: BF %d, MD %d, %d samples per pixel (study resolution)." % (out, bf, md, sw["spp"]),
                       cam, sw["res"], name, independent(sw["spp"]), distributed(md, bf=bf, ls=1), inc[world], TONEMAP_NONE)
            register(name, cam, sw["res"], [], {"bf": bf, "md": md, "spp": sw["spp"]})
            files.append(name)
        rbf, rmd, rspp = sw["ref"]
        name = "%s_ref" % world
        scene_file(os.path.join(M2, "param", name + ".pbrt"),
                   "Module 2, 2.2.4: converged reference for %s (BF %d, MD %d, %d samples per pixel)." % (out, rbf, rmd, rspp),
                   cam, sw["res"], name, independent(rspp), distributed(rmd, bf=rbf, ls=1), inc[world], TONEMAP_NONE)
        register(name, cam, sw["res"], [], {"bf": rbf, "md": rmd, "spp": rspp})
        sweeps[out] = dict(sw, files=files, refname=name)
    VIEWS["_sweeps"] = sweeps
    # remove sweep files of earlier sweep definitions
    pdir = os.path.join(M2, "param")
    for f in sorted(os.listdir(pdir)):
        if f.endswith(".pbrt") and f[:-5] not in VIEWS:
            os.remove(os.path.join(pdir, f))
            print("removed stale %s" % rel(os.path.join(pdir, f)))
    write(os.path.join(M2, "views.json"), json.dumps(VIEWS, indent=1))
    print("wrote %d scene views; scenes/module2/views.json" % len(VIEWS))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Coarse torus meshes for the Module 1 report's mesh test (scenes/validation/val_drt_meshnormals.pbrt).
Writes meshes/torus_coarse_smooth.obj (positions, UVs and per-vertex normals) and
meshes/torus_coarse_flat.obj (the same positions and UVs, no normals). Python standard library only."""
import math
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, r, NU, NV = 1.0, 0.4, 24, 12  # ring radius, tube radius, segments around the ring / the tube


def write(name, normals):
    lines = ["# coarse torus R=%g r=%g, %dx%d quads = %d triangles%s" % (R, r, NU, NV, 2 * NU * NV,
             ", per-vertex normals" if normals else ", no normals (flat shading)")]
    for i in range(NU + 1):  # duplicated seam vertices keep the UVs continuous
        a = 2 * math.pi * i / NU
        for j in range(NV + 1):
            b = 2 * math.pi * j / NV
            x, y, z = (R + r * math.cos(b)) * math.cos(a), r * math.sin(b), (R + r * math.cos(b)) * math.sin(a)
            lines.append("v %.6f %.6f %.6f" % (x, y, z))
    for i in range(NU + 1):
        for j in range(NV + 1):
            lines.append("vt %.6f %.6f" % (i / NU, j / NV))
    if normals:
        for i in range(NU + 1):
            a = 2 * math.pi * i / NU
            for j in range(NV + 1):
                b = 2 * math.pi * j / NV
                lines.append("vn %.6f %.6f %.6f" % (math.cos(b) * math.cos(a), math.sin(b), math.cos(b) * math.sin(a)))
    idx = lambda i, j: i * (NV + 1) + j + 1
    for i in range(NU):
        for j in range(NV):
            a, b, c, d = idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)
            for tri in ((a, c, b), (a, d, c)):
                if normals:
                    lines.append("f " + " ".join("%d/%d/%d" % (k, k, k) for k in tri))
                else:
                    lines.append("f " + " ".join("%d/%d" % (k, k) for k in tri))
    with open(os.path.join(HERE, "meshes", name), "w") as f:
        f.write("\n".join(lines) + "\n")


write("torus_coarse_smooth.obj", True)
write("torus_coarse_flat.obj", False)
print("wrote meshes/torus_coarse_smooth.obj and meshes/torus_coarse_flat.obj")

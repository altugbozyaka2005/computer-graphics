// Triangle mesh file loaders using only the standard library.
#pragma once

#include <string>
#include <vector>

#include "../core/math.h"

struct MeshData {
    std::vector<Vec3> p, n;
    std::vector<Vec2> uv;
    std::vector<int> indices;  // triangles
};

// Wavefront OBJ: v, vt, vn, f (polygons are fan-triangulated, negative indices
// allowed). Other statements are ignored and reported via *notes.
bool loadOBJ(const std::string& path, MeshData* mesh, std::string* err, std::string* notes);
// PLY: ascii, binary_little_endian, binary_big_endian. Vertex x,y,z with optional
// nx,ny,nz and u,v (or s,t); faces "vertex_indices" lists (fan-triangulated).
bool loadPLY(const std::string& path, MeshData* mesh, std::string* err, std::string* notes);

#include "meshio.h"

#include <cstdint>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

// =============================================================== OBJ
bool loadOBJ(const std::string& path, MeshData* mesh, std::string* err, std::string* notes) {
    std::ifstream f(path);
    if (!f) { *err = "cannot open OBJ file '" + path + "'"; return false; }
    std::vector<Vec3> pos, nrm;
    std::vector<Vec2> tex;
    struct Corner { int v, t, n; };
    std::vector<std::vector<Corner>> faces;
    std::set<std::string> ignored;
    std::string line;
    int lineNo = 0;
    while (std::getline(f, line)) {
        ++lineNo;
        size_t hash = line.find('#');
        if (hash != std::string::npos) line = line.substr(0, hash);
        std::istringstream ls(line);
        std::string tag;
        if (!(ls >> tag)) continue;
        if (tag == "v") {
            double x, y, z;
            if (!(ls >> x >> y >> z)) { *err = "malformed vertex at line " + std::to_string(lineNo); return false; }
            pos.push_back(Vec3(x, y, z));
        } else if (tag == "vt") {
            double u, v = 0;
            if (!(ls >> u)) { *err = "malformed texture coordinate at line " + std::to_string(lineNo); return false; }
            ls >> v;
            tex.push_back(Vec2(u, v));
        } else if (tag == "vn") {
            double x, y, z;
            if (!(ls >> x >> y >> z)) { *err = "malformed normal at line " + std::to_string(lineNo); return false; }
            nrm.push_back(Vec3(x, y, z));
        } else if (tag == "f") {
            std::vector<Corner> face;
            std::string tok;
            while (ls >> tok) {
                Corner c{0, 0, 0};
                int* slots[3] = {&c.v, &c.t, &c.n};
                size_t start = 0;
                for (int k = 0; k < 3; ++k) {
                    size_t slash = tok.find('/', start);
                    std::string part = tok.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
                    if (!part.empty()) {
                        try {
                            *slots[k] = std::stoi(part);
                        } catch (...) {
                            *err = "malformed face index '" + tok + "' at line " + std::to_string(lineNo);
                            return false;
                        }
                    }
                    if (slash == std::string::npos) break;
                    start = slash + 1;
                }
                // Resolve 1-based / negative (relative) indices to 0-based, -1 = absent.
                auto resolve = [&](int idx, size_t count, int* out) {
                    if (idx == 0) { *out = -1; return true; }
                    long r = idx > 0 ? idx - 1 : (long)count + idx;
                    if (r < 0 || r >= (long)count) return false;
                    *out = (int)r;
                    return true;
                };
                if (!resolve(c.v, pos.size(), &c.v) || c.v < 0 || !resolve(c.t, tex.size(), &c.t) ||
                    !resolve(c.n, nrm.size(), &c.n)) {
                    *err = "face index out of range at line " + std::to_string(lineNo);
                    return false;
                }
                face.push_back(c);
            }
            if (face.size() < 3) { *err = "face with fewer than 3 vertices at line " + std::to_string(lineNo); return false; }
            faces.push_back(face);
        } else {
            ignored.insert(tag);
        }
    }
    if (faces.empty()) { *err = "OBJ file contains no faces"; return false; }

    bool allT = true, allN = true;
    for (auto& fc : faces)
        for (auto& c : fc) {
            allT = allT && c.t >= 0;
            allN = allN && c.n >= 0;
        }
    bool anyT = false, anyN = false;
    for (auto& fc : faces)
        for (auto& c : fc) {
            anyT = anyT || c.t >= 0;
            anyN = anyN || c.n >= 0;
        }
    if (anyT && !allT) *notes += "some faces lack texture coordinates; UVs ignored. ";
    if (anyN && !allN) *notes += "some faces lack normals; vertex normals ignored. ";
    if (!ignored.empty()) {
        *notes += "ignored OBJ statements:";
        for (auto& s : ignored) *notes += " " + s;
        *notes += ". ";
    }

    // Unify (v, vt, vn) triples into single-index vertices.
    std::map<std::tuple<int, int, int>, int> remap;
    auto vertexFor = [&](const Corner& c) {
        auto key = std::make_tuple(c.v, allT ? c.t : -1, allN ? c.n : -1);
        auto it = remap.find(key);
        if (it != remap.end()) return it->second;
        int id = (int)mesh->p.size();
        mesh->p.push_back(pos[c.v]);
        if (allT) mesh->uv.push_back(tex[c.t]);
        if (allN) mesh->n.push_back(nrm[c.n]);
        remap[key] = id;
        return id;
    };
    for (auto& fc : faces) {
        int a = vertexFor(fc[0]);
        for (size_t i = 1; i + 1 < fc.size(); ++i) {
            mesh->indices.push_back(a);
            mesh->indices.push_back(vertexFor(fc[i]));
            mesh->indices.push_back(vertexFor(fc[i + 1]));
        }
    }
    return true;
}

// =============================================================== PLY
namespace {
enum class PType { I8, U8, I16, U16, I32, U32, F32, F64, Invalid };
PType parsePType(const std::string& s) {
    if (s == "char" || s == "int8") return PType::I8;
    if (s == "uchar" || s == "uint8") return PType::U8;
    if (s == "short" || s == "int16") return PType::I16;
    if (s == "ushort" || s == "uint16") return PType::U16;
    if (s == "int" || s == "int32") return PType::I32;
    if (s == "uint" || s == "uint32") return PType::U32;
    if (s == "float" || s == "float32") return PType::F32;
    if (s == "double" || s == "float64") return PType::F64;
    return PType::Invalid;
}
int ptypeSize(PType t) {
    switch (t) {
        case PType::I8: case PType::U8: return 1;
        case PType::I16: case PType::U16: return 2;
        case PType::I32: case PType::U32: case PType::F32: return 4;
        case PType::F64: return 8;
        default: return 0;
    }
}
struct PProp {
    std::string name;
    PType type = PType::Invalid;
    bool isList = false;
    PType countType = PType::Invalid;
};
struct PElem {
    std::string name;
    size_t count = 0;
    std::vector<PProp> props;
};

class PlyReader {
public:
    std::ifstream& f;
    bool ascii, bigEndian;
    PlyReader(std::ifstream& file, bool a, bool be) : f(file), ascii(a), bigEndian(be) {}
    bool read(PType t, double* out) {
        if (ascii) return (bool)(f >> *out);
        unsigned char b[8];
        int n = ptypeSize(t);
        if (!f.read((char*)b, n)) return false;
        uint16_t probe = 1;
        bool hostLittle = *(unsigned char*)&probe == 1;
        if (bigEndian == hostLittle) std::reverse(b, b + n);
        switch (t) {
            case PType::I8: { int8_t v; std::memcpy(&v, b, 1); *out = v; break; }
            case PType::U8: { uint8_t v; std::memcpy(&v, b, 1); *out = v; break; }
            case PType::I16: { int16_t v; std::memcpy(&v, b, 2); *out = v; break; }
            case PType::U16: { uint16_t v; std::memcpy(&v, b, 2); *out = v; break; }
            case PType::I32: { int32_t v; std::memcpy(&v, b, 4); *out = v; break; }
            case PType::U32: { uint32_t v; std::memcpy(&v, b, 4); *out = v; break; }
            case PType::F32: { float v; std::memcpy(&v, b, 4); *out = v; break; }
            case PType::F64: { double v; std::memcpy(&v, b, 8); *out = v; break; }
            default: return false;
        }
        return true;
    }
};
}  // namespace

bool loadPLY(const std::string& path, MeshData* mesh, std::string* err, std::string* notes) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { *err = "cannot open PLY file '" + path + "'"; return false; }
    std::string line;
    std::getline(f, line);
    if (line.substr(0, 3) != "ply") { *err = "not a PLY file (missing 'ply' magic)"; return false; }
    bool ascii = false, bigEndian = false, haveFormat = false;
    std::vector<PElem> elems;
    while (std::getline(f, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::istringstream ls(line);
        std::string kw;
        ls >> kw;
        if (kw == "format") {
            std::string fmt;
            ls >> fmt;
            haveFormat = true;
            if (fmt == "ascii") ascii = true;
            else if (fmt == "binary_little_endian") bigEndian = false;
            else if (fmt == "binary_big_endian") bigEndian = true;
            else { *err = "unknown PLY format '" + fmt + "'"; return false; }
        } else if (kw == "element") {
            PElem e;
            ls >> e.name >> e.count;
            elems.push_back(e);
        } else if (kw == "property") {
            if (elems.empty()) { *err = "PLY property before any element"; return false; }
            PProp p;
            std::string t;
            ls >> t;
            if (t == "list") {
                std::string ct, it;
                ls >> ct >> it >> p.name;
                p.isList = true;
                p.countType = parsePType(ct);
                p.type = parsePType(it);
                if (p.countType == PType::Invalid || p.type == PType::Invalid) { *err = "bad PLY list type"; return false; }
            } else {
                p.type = parsePType(t);
                ls >> p.name;
                if (p.type == PType::Invalid) { *err = "unknown PLY property type '" + t + "'"; return false; }
            }
            elems.back().props.push_back(p);
        } else if (kw == "end_header") {
            break;
        }
    }
    if (!haveFormat) { *err = "PLY header has no format line"; return false; }
    PlyReader rd(f, ascii, bigEndian);
    bool haveN = false, haveUV = false;
    for (auto& e : elems) {
        if (e.name == "vertex") {
            int ix = -1, iy = -1, iz = -1, inx = -1, iny = -1, inz = -1, iu = -1, iv = -1;
            for (size_t k = 0; k < e.props.size(); ++k) {
                const std::string& n = e.props[k].name;
                if (n == "x") ix = (int)k; else if (n == "y") iy = (int)k; else if (n == "z") iz = (int)k;
                else if (n == "nx") inx = (int)k; else if (n == "ny") iny = (int)k; else if (n == "nz") inz = (int)k;
                else if (n == "u" || n == "s" || n == "texture_u" || n == "texture_s") iu = (int)k;
                else if (n == "v" || n == "t" || n == "texture_v" || n == "texture_t") iv = (int)k;
            }
            if (ix < 0 || iy < 0 || iz < 0) { *err = "PLY vertex element lacks x/y/z"; return false; }
            haveN = inx >= 0 && iny >= 0 && inz >= 0;
            haveUV = iu >= 0 && iv >= 0;
            std::vector<double> vals(e.props.size());
            for (size_t i = 0; i < e.count; ++i) {
                for (size_t k = 0; k < e.props.size(); ++k) {
                    if (e.props[k].isList) {
                        double cnt, dummy;
                        if (!rd.read(e.props[k].countType, &cnt)) { *err = "PLY vertex data truncated"; return false; }
                        for (int j = 0; j < (int)cnt; ++j) rd.read(e.props[k].type, &dummy);
                        vals[k] = 0;
                    } else if (!rd.read(e.props[k].type, &vals[k])) {
                        *err = "PLY vertex data truncated";
                        return false;
                    }
                }
                mesh->p.push_back(Vec3(vals[ix], vals[iy], vals[iz]));
                if (haveN) mesh->n.push_back(Vec3(vals[inx], vals[iny], vals[inz]));
                if (haveUV) mesh->uv.push_back(Vec2(vals[iu], vals[iv]));
            }
        } else if (e.name == "face") {
            bool polygonsSeen = false;
            for (size_t i = 0; i < e.count; ++i) {
                for (auto& p : e.props) {
                    if (p.isList) {
                        double cnt;
                        if (!rd.read(p.countType, &cnt)) { *err = "PLY face data truncated"; return false; }
                        std::vector<int> idx((size_t)cnt);
                        for (auto& v : idx) {
                            double d;
                            if (!rd.read(p.type, &d)) { *err = "PLY face data truncated"; return false; }
                            v = (int)d;
                        }
                        if (p.name == "vertex_indices" || p.name == "vertex_index") {
                            if (idx.size() > 3) polygonsSeen = true;
                            for (size_t j = 1; j + 1 < idx.size(); ++j) {
                                mesh->indices.push_back(idx[0]);
                                mesh->indices.push_back(idx[j]);
                                mesh->indices.push_back(idx[j + 1]);
                            }
                        }
                    } else {
                        double d;
                        if (!rd.read(p.type, &d)) { *err = "PLY face data truncated"; return false; }
                    }
                }
            }
            if (polygonsSeen) *notes += "PLY polygons with >3 vertices were fan-triangulated. ";
        } else {
            // Skip unknown elements.
            for (size_t i = 0; i < e.count; ++i)
                for (auto& p : e.props) {
                    double d;
                    if (p.isList) {
                        double cnt;
                        if (!rd.read(p.countType, &cnt)) { *err = "PLY data truncated"; return false; }
                        for (int j = 0; j < (int)cnt; ++j) rd.read(p.type, &d);
                    } else if (!rd.read(p.type, &d)) {
                        *err = "PLY data truncated";
                        return false;
                    }
                }
            *notes += "ignored PLY element '" + e.name + "'. ";
        }
    }
    for (int i : mesh->indices)
        if (i < 0 || i >= (int)mesh->p.size()) { *err = "PLY face index out of range"; return false; }
    if (mesh->indices.empty()) { *err = "PLY file contains no faces"; return false; }
    return true;
}

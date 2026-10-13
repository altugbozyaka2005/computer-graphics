// Shape directive (+ attached AreaLightSource).
#include "builders.h"
#include "meshio.h"

std::vector<Shape*> SceneBuilder::addMesh(const MeshData& mdIn, const Transform& ctm, bool ro, int materialId,
                                          const FileLoc& loc, const std::string& label) {
    std::vector<Shape*> out;
    MeshData md = mdIn;
    if (md.p.empty()) {
        LOG().error(label + ": no vertex positions (\"point3 P\" is required); shape ignored", loc);
        return out;
    }
    if (md.indices.empty() || md.indices.size() % 3 != 0) {
        LOG().error(label + ": index count " + std::to_string(md.indices.size()) +
                        " is not a positive multiple of 3; shape ignored",
                    loc);
        return out;
    }
    for (int i : md.indices)
        if (i < 0 || i >= (int)md.p.size()) {
            LOG().error(label + ": vertex index " + std::to_string(i) + " out of range [0," +
                            std::to_string(md.p.size() - 1) + "]; shape ignored",
                        loc);
            return out;
        }
    if (!md.n.empty() && md.n.size() != md.p.size()) {
        LOG().error(label + ": " + std::to_string(md.n.size()) + " normals for " + std::to_string(md.p.size()) +
                        " vertices; normals ignored",
                    loc);
        md.n.clear();
    }
    if (!md.uv.empty() && md.uv.size() != md.p.size()) {
        LOG().error(label + ": " + std::to_string(md.uv.size()) + " uvs for " + std::to_string(md.p.size()) +
                        " vertices; uvs ignored",
                    loc);
        md.uv.clear();
    }
    auto mesh = std::make_shared<TriangleMesh>();
    mesh->p.reserve(md.p.size());
    for (const auto& p : md.p) mesh->p.push_back(ctm.point(p));
    for (const auto& n : md.n) mesh->n.push_back(normalize(ctm.normal(n)));
    mesh->uv = md.uv;
    mesh->indices = md.indices;
    mesh->flipNormals = ro != ctm.swapsHandedness();
    scene_->meshes.push_back(mesh);
    int degenerate = 0;
    for (size_t t = 0; t < md.indices.size() / 3; ++t) {
        auto tri = std::make_unique<Triangle>(mesh, (int)t);
        if (!(tri->area() > 0)) {
            ++degenerate;
            continue;
        }
        tri->materialId = materialId;
        out.push_back(tri.get());
        scene_->shapes.push_back(std::move(tri));
    }
    if (degenerate)
        LOG().warning(label + ": skipped " + std::to_string(degenerate) + " degenerate (zero-area) triangles", loc);
    LOG().info(label + ": " + std::to_string(out.size()) + " triangles, " + std::to_string(md.p.size()) +
               " vertices" + (md.n.empty() ? "" : ", normals") + (md.uv.empty() ? "" : ", uvs"));
    return out;
}

void SceneBuilder::shape(const std::string& type, const ParamSet& ps, const Transform& ctm, bool ro, int materialId,
                         const AreaLightState& area, const FileLoc& loc) {
    if (!ctm.valid()) {
        LOG().error("shape '" + type + "' has a singular transform (e.g. zero scale); ignored", loc);
        return;
    }
    std::vector<Shape*> created;
    // Every Shape directive becomes one object (with its own bounding box).
    struct ObjectRecorder {
        Scene* scene;
        size_t first;
        ~ObjectRecorder() {
            if (scene->shapes.size() > first) scene->addObject(first, scene->shapes.size());
        }
    } recorder{scene_, scene_->shapes.size()};
    auto addShape = [&](std::unique_ptr<Shape> s) {
        s->materialId = materialId;
        created.push_back(s.get());
        if (s->bounded()) scene_->shapes.push_back(std::move(s));
        else scene_->unbounded.push_back(std::move(s));
    };
    auto checkPhi = [&](double phimax) {
        if (phimax <= 0 || phimax > 360) {
            LOG().error("phimax must be in (0,360]; using 360", loc);
            return 360.0;
        }
        return phimax;
    };
    auto uniformScaleCheck = [&]() {
        double sx = length(ctm.vector(Vec3(1, 0, 0))), sy = length(ctm.vector(Vec3(0, 1, 0))),
               sz = length(ctm.vector(Vec3(0, 0, 1)));
        double mx = std::max(sx, std::max(sy, sz)), mn = std::min(sx, std::min(sy, sz));
        return mx - mn <= 1e-6 * mx;
    };

    if (type == "sphere") {
        double r = ps.getFloat("radius", 1);
        if (!(r > 0)) {
            LOG().error("sphere radius must be > 0 (got " + std::to_string(r) + "); shape ignored", loc);
            for (const auto& p : ps.params) p.used = true;
            return;
        }
        double zmin = ps.getFloat("zmin", -r), zmax = ps.getFloat("zmax", r);
        double phimax = checkPhi(ps.getFloat("phimax", 360));
        if (zmin >= zmax) {
            LOG().error("sphere zmin must be < zmax; using full sphere", loc);
            zmin = -r;
            zmax = r;
        }
        if (area.active && !uniformScaleCheck())
            LOG().warning("sphere under non-uniform scale: intersection is exact but its area (used for area lights) "
                          "is approximate",
                          loc);
        auto s = std::make_unique<Sphere>(ctm, ro, r, zmin, zmax, phimax);
        if (area.active && !s->isFullSphere())
            LOG().warning("partial sphere area light is sampled as a full sphere", loc);
        addShape(std::move(s));
    } else if (type == "disk") {
        double r = ps.getFloat("radius", 1), ri = ps.getFloat("innerradius", 0), h = ps.getFloat("height", 0);
        double phimax = checkPhi(ps.getFloat("phimax", 360));
        if (!(r > 0)) {
            LOG().error("disk radius must be > 0; shape ignored", loc);
            return;
        }
        if (ri < 0 || ri >= r) {
            LOG().error("disk innerradius must be in [0, radius); using 0", loc);
            ri = 0;
        }
        if (area.active && (ri > 0 || phimax < 360))
            LOG().warning("annulus/partial disk area light is sampled as a full disk", loc);
        addShape(std::make_unique<Disk>(ctm, ro, h, r, ri, phimax));
    } else if (type == "trianglemesh") {
        MeshData md;
        md.p = ps.getPoint3s("P");
        md.indices = ps.getInts("indices");
        if (md.indices.empty() && md.p.size() == 3) md.indices = {0, 1, 2};
        else if (md.indices.empty() && !md.p.empty())
            LOG().error("trianglemesh: \"integer indices\" is required unless exactly 3 vertices are given", loc);
        md.n = ps.getPoint3s("N");
        md.uv = ps.getPoint2s(ps.has("uv") ? "uv" : "st");
        if (const Param* p = ps.find("S")) { p->used = true; LOG().info("trianglemesh tangents 'S' ignored"); }
        if (const Param* p = ps.find("faceIndices")) p->used = true;
        for (Shape* s : addMesh(md, ctm, ro, materialId, loc, "trianglemesh")) created.push_back(s);
    } else if (type == "bilinearmesh") {
        std::vector<Vec3> P = ps.getPoint3s("P");
        std::vector<int> idx = ps.getInts("indices");
        if (idx.empty() && P.size() == 4) idx = {0, 1, 2, 3};
        if (idx.size() % 4 != 0 || idx.empty()) {
            LOG().error("bilinearmesh: indices must be a positive multiple of 4; shape ignored", loc);
            return;
        }
        MeshData md;
        md.p = P;
        md.uv = ps.getPoint2s("uv");
        md.n = ps.getPoint3s("N");
        // Patch vertices are ordered p00, p10, p01, p11; split along p00-p11.
        for (size_t i = 0; i < idx.size(); i += 4) {
            int a = idx[i], b = idx[i + 1], c = idx[i + 2], d = idx[i + 3];
            md.indices.insert(md.indices.end(), {a, b, d, a, d, c});
        }
        if (md.uv.empty() && P.size() == 4 && idx.size() == 4)
            md.uv = {Vec2(0, 0), Vec2(1, 0), Vec2(0, 1), Vec2(1, 1)};  // pbrt default patch parameterisation
        if (md.uv.size() != md.p.size()) md.uv.clear();
        for (Shape* s : addMesh(md, ctm, ro, materialId, loc, "bilinearmesh")) created.push_back(s);
        LOG().info("bilinearmesh triangulated (exact for planar parallelograms)");
    } else if (type == "plymesh" || type == "objmesh") {
        std::string file = ps.getString("filename", "");
        for (const char* n : {"displacement", "edgelength"})
            if (const Param* p = ps.find(n)) {
                p->used = true;
                LOG().warning(std::string("plymesh '") + n + "' (displacement) not supported", loc);
            }
        if (file.empty()) {
            LOG().error(type + " requires \"string filename\"; shape ignored", loc);
            return;
        }
        MeshData md;
        std::string err, notes;
        std::string path = resolvePath(file);
        bool ok = type == "plymesh" ? loadPLY(path, &md, &err, &notes) : loadOBJ(path, &md, &err, &notes);
        if (!ok) {
            LOG().error("failed to load mesh '" + file + "': " + err + "; shape ignored", loc);
            return;
        }
        if (!notes.empty()) LOG().info(file + ": " + notes);
        for (Shape* s : addMesh(md, ctm, ro, materialId, loc, type + " '" + file + "'")) created.push_back(s);
    } else if (type == "plane") {
        Vec3 p = ps.getPoint3(ps.has("point") ? "point" : "p", Vec3(0, 0, 0));
        Vec3 n = ps.getPoint3(ps.has("normal") ? "normal" : "n", Vec3(0, 0, 1));
        if (length(n) == 0) {
            LOG().error("plane normal must be non-zero; shape ignored", loc);
            return;
        }
        if (area.active) {
            LOG().error("area lights on infinite planes are not supported; plane is not emissive", loc);
        }
        auto pl = std::make_unique<Plane>(ctm.point(p), normalize(ctm.normal(n)), ro);
        pl->materialId = materialId;
        scene_->unbounded.push_back(std::move(pl));
        ps.reportUnused("Shape \"plane\"");
        return;
    } else if (type == "cylinder" || type == "curve" || type == "loopsubdiv" || type == "nurbs" ||
               type == "heightfield") {
        LOG().warning("shape type '" + type + "' not supported; ignored", loc);
        for (const auto& p : ps.params) p.used = true;
        return;
    } else {
        LOG().error("unknown shape type '" + type + "'; ignored", loc);
        for (const auto& p : ps.params) p.used = true;
        return;
    }
    if (ps.has("alpha")) {
        TexturePtr alphaTex = spectrumTexture(ps, "alpha", Color(1), SpectrumKind::Unbounded);
        Color c;
        bool opaque = alphaTex->constantValue(&c) && c.average() >= 0.5;
        if (!opaque) {
            for (Shape* s : created) s->alpha = alphaTex;
            if (std::string(created.empty() ? "" : created[0]->typeName()) == "sphere")
                LOG().warning("alpha on a sphere tests only the nearest hit against the mask", loc);
        }
    }
    ps.reportUnused("Shape \"" + type + "\"");

    if (area.active && !created.empty()) {
        if (area.type != "diffuse") {
            LOG().error("unknown AreaLightSource type '" + area.type + "' (supported: diffuse); shape not emissive",
                        area.loc);
            return;
        }
        auto al = std::make_unique<AreaLight>();
        Color L(1);
        if (area.params.has("L")) area.params.getRGB("L", SpectrumKind::Illuminant, &L);
        al->twoSided = area.params.getBool("twosided", false);
        double sc = area.params.getFloat("scale", 1);
        if (sc < 0) {
            LOG().error("area light scale must be >= 0; using 1", area.loc);
            sc = 1;
        }
        int ns = area.params.has("samples") ? area.params.getInt("samples", -1) : area.params.getInt("nsamples", -1);
        if (ns < -1) {
            LOG().error("area light samples must be >= 0; using the integrator default", area.loc);
            ns = -1;
        }
        if (ns == 0)
            LOG().info("area light with samples 0: visible and emitting, but not sampled with shadow rays");
        al->nSamples = ns;
        if (area.params.has("filename")) {
            area.params.getString("filename", "");
            LOG().warning("image area lights not supported; using L", area.loc);
        }
        al->shapes.assign(created.begin(), created.end());
        al->finalize();
        double pw = area.params.getFloat("power", -1);
        if (pw > 0 && al->totalArea > 0) sc *= pw / (Pi * (al->twoSided ? 2 : 1) * al->totalArea);
        al->L = L * sc;
        for (Shape* s : created) s->areaLight = al.get();
        LOG().info("area light: " + std::to_string(created.size()) + " shape(s), area " +
                   std::to_string(al->totalArea) +
                   (al->twoSided ? ", two-sided" : ""));
        area.params.reportUnused("AreaLightSource \"diffuse\"");
        scene_->areaLights.push_back(std::move(al));
    }
}

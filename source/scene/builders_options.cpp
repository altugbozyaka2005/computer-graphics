// Render-option directives: Camera, Film, Sampler, PixelFilter, Integrator, Accelerator.
#include "builders.h"

namespace {
void ignoreQuietly(const ParamSet& ps, std::initializer_list<const char*> names, const std::string& ctx) {
    for (const char* n : names)
        if (const Param* p = ps.find(n)) {
            p->used = true;
            LOG().info("ignoring pbrt parameter \"" + p->type + " " + p->name + "\" in " + ctx + " (no effect here)");
        }
}
}  // namespace

void SceneBuilder::camera(const std::string& type, const ParamSet& ps, const Transform& ctm, const FileLoc& loc) {
    CameraSettings& c = scene_->camera;
    if (type == "perspective" || type == "orthographic") {
        c.type = type;
    } else {
        LOG().error("unsupported camera type '" + type + "' (supported: perspective, orthographic); using perspective",
                    loc);
        c.type = "perspective";
    }
    if (!ctm.valid()) {
        LOG().error("camera transform is singular; using identity", loc);
        c.worldFromCamera = Transform();
    } else {
        c.worldFromCamera = ctm.inverse();
    }
    // pbrt's orthographic camera has no field of view: its extent is the screen window
    // (camera-space units), so a "fov" given to it is reported as unused.
    if (c.type == "perspective") {
        c.fov = ps.getFloat("fov", 90);
        if (!(c.fov > 0 && c.fov < 180)) {
            LOG().error("camera fov " + std::to_string(c.fov) + " out of range (0,180); using 90", loc);
            c.fov = 90;
        }
    }
    c.lensRadius = ps.getFloat("lensradius", 0);
    if (c.lensRadius < 0) {
        LOG().error("lensradius must be >= 0; using 0", loc);
        c.lensRadius = 0;
    }
    c.focalDistance = ps.getFloat("focaldistance", 1e6);
    if (c.focalDistance <= 0) {
        LOG().error("focaldistance must be > 0; using 1e6", loc);
        c.focalDistance = 1e6;
    }
    std::vector<double> sw = ps.getFloats("screenwindow");
    if (!sw.empty()) {
        if (sw.size() == 4 && sw[0] < sw[1] && sw[2] < sw[3]) {
            c.hasScreenWindow = true;
            for (int i = 0; i < 4; ++i) c.screenWindow[i] = sw[i];
        } else {
            LOG().error("screenwindow needs 4 values xmin xmax ymin ymax with min < max; ignored", loc);
        }
    }
    c.frameAspect = ps.getFloat("frameaspectratio", 0);
    if (c.frameAspect < 0) {
        LOG().error("frameaspectratio must be > 0; ignored", loc);
        c.frameAspect = 0;
    }
    ignoreQuietly(ps, {"shutteropen", "shutterclose"}, "Camera");
    ps.reportUnused("Camera \"" + type + "\"");
    cameraSet_ = true;
}

void SceneBuilder::film(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    if (type != "rgb") LOG().warning("film type '" + type + "' treated as \"rgb\"", loc);
    FilmSettings& f = scene_->film;
    int xr = ps.getInt("xresolution", 1280), yr = ps.getInt("yresolution", 720);
    if (xr <= 0 || xr > 16384) {
        LOG().error("xresolution " + std::to_string(xr) + " out of range [1,16384]; using 1280", loc);
        xr = 1280;
    }
    if (yr <= 0 || yr > 16384) {
        LOG().error("yresolution " + std::to_string(yr) + " out of range [1,16384]; using 720", loc);
        yr = 720;
    }
    f.xRes = xr;
    f.yRes = yr;
    f.filenameSpecified = ps.has("filename");
    f.filename = ps.getString("filename", f.filename);
    std::vector<double> cw = ps.getFloats("cropwindow");
    if (!cw.empty()) {
        bool ok = cw.size() == 4 && cw[0] >= 0 && cw[1] <= 1 && cw[0] < cw[1] && cw[2] >= 0 && cw[3] <= 1 &&
                  cw[2] < cw[3];
        if (ok) for (int i = 0; i < 4; ++i) f.crop[i] = cw[i];
        else LOG().error("cropwindow must be 4 values in [0,1] with min < max; ignored", loc);
    }
    std::vector<int> pb = ps.getInts("pixelbounds");
    if (!pb.empty()) {
        bool ok = pb.size() == 4 && pb[0] >= 0 && pb[0] < pb[1] && pb[1] <= xr && pb[2] >= 0 && pb[2] < pb[3] &&
                  pb[3] <= yr;
        if (ok) {
            f.hasPixelBounds = true;
            for (int i = 0; i < 4; ++i) f.pixelBounds[i] = pb[i];
        } else {
            LOG().error("pixelbounds must be 4 integers x0 x1 y0 y1 inside the image with x0 < x1, y0 < y1; ignored",
                        loc);
        }
    }
    // Renderer extensions for tone mapping (Module 1 DRT requirement).
    if (ps.has("tonemap")) {
        f.tonemapSpecified = true;
        std::string op = ps.getString("tonemap", "reinhard");
        if (op != "reinhard" && op != "none") {
            LOG().error("unknown tonemap '" + op + "' (reinhard|none); using reinhard", loc);
            op = "reinhard";
        }
        f.tonemap.op = op;
    }
    std::string mode = ps.getString("tonemapmode", "luminance");
    if (mode != "luminance" && mode != "rgb") {
        LOG().error("unknown tonemapmode '" + mode + "' (luminance|rgb); using luminance", loc);
        mode = "luminance";
    }
    f.tonemap.mode = mode;
    f.tonemap.whitePoint = ps.getFloat("whitepoint", 0);
    if (f.tonemap.whitePoint < 0) {
        LOG().error("whitepoint must be >= 0 (0 = automatic); using automatic", loc);
        f.tonemap.whitePoint = 0;
    }
    f.tonemap.key = ps.getFloat("key", 0);
    if (f.tonemap.key < 0) {
        LOG().error("key must be >= 0; disabling key scaling", loc);
        f.tonemap.key = 0;
    }
    f.tonemap.exposure = ps.getFloat("exposure", 1);
    if (f.tonemap.exposure <= 0) {
        LOG().error("exposure must be > 0; using 1", loc);
        f.tonemap.exposure = 1;
    }
    ignoreQuietly(ps, {"iso", "whitebalance", "sensor", "savefp16", "maxcomponentvalue", "diagonal"},
                  "Film");
    ps.reportUnused("Film \"" + type + "\"");
}

void SceneBuilder::sampler(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    SamplerSettings& s = scene_->sampler;
    scene_->samplerSpecified = true;
    if (type == "independent" || type == "stratified" || type == "halton") {
        s.type = type;
    } else if (type == "zsobol" || type == "sobol" || type == "paddedsobol" || type == "pmj02bn") {
        LOG().warning("sampler '" + type + "' not implemented; using the (also low-discrepancy) halton sampler", loc);
        s.type = "halton";
    } else {
        LOG().error("unknown sampler '" + type + "' (supported: independent, stratified, halton); using independent",
                    loc);
        s.type = "independent";
    }
    if (s.type == "stratified") {
        s.xSamples = ps.getInt("xsamples", 4);
        s.ySamples = ps.getInt("ysamples", 4);
        if (s.xSamples <= 0 || s.ySamples <= 0 || s.xSamples > 256 || s.ySamples > 256) {
            LOG().error("xsamples/ysamples must be in [1,256]; using 4x4", loc);
            s.xSamples = s.ySamples = 4;
        }
        s.jitter = ps.getBool("jitter", true);
    } else {
        s.pixelSamples = ps.getInt("pixelsamples", 16);
        if (s.pixelSamples <= 0 || s.pixelSamples > 65536) {
            LOG().error("pixelsamples must be in [1,65536]; using 16", loc);
            s.pixelSamples = 16;
        }
    }
    if (const Param* r = ps.find("randomization")) {
        std::string v = ps.getString("randomization", "permutedigits");
        if (s.type == "halton") {
            s.randomize = v != "none";
            if (s.randomize && v != "permutedigits" && v != "owen" && v != "fastowen")
                LOG().error("unknown halton randomization '" + v + "' (permutedigits|owen|fastowen|none)", loc);
            else if (s.randomize)
                LOG().info("halton randomization '" + v + "' approximated by a Cranley-Patterson rotation per pixel");
        } else {
            r->used = true;
            LOG().info("ignoring \"randomization\" for the " + s.type + " sampler");
        }
    }
    s.seed = ps.getInt("seed", 0);
    ps.reportUnused("Sampler \"" + type + "\"");
}

void SceneBuilder::pixelFilter(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    // The film averages the samples of a pixel with equal weights. As in pbrt-v4 (filter
    // importance sampling), a box filter of radius r draws the samples from [-r, r]^2 around
    // the pixel centre; the default r = 0.5 covers exactly the pixel.
    FilterSettings& f = scene_->filter;
    if (type == "box") {
        double rx = ps.getFloat("xradius", 0.5), ry = ps.getFloat("yradius", 0.5);
        if (rx > 0 && ry > 0 && rx <= 4 && ry <= 4) {
            f.xRadius = rx;
            f.yRadius = ry;
        } else {
            LOG().error("box filter radius must be in (0,4]; using 0.5", loc);
        }
        ps.reportUnused("PixelFilter \"box\"");
    } else {
        LOG().warning("PixelFilter \"" + type + "\" not implemented: pixel samples are averaged with equal weights "
                      "(box filter, radius 0.5)", loc);
        for (const auto& p : ps.params) p.used = true;
    }
}

void SceneBuilder::integrator(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    IntegratorSettings& in = scene_->integrator;
    if (type == "whitted" || type == "distributed") {
        in.type = type;
    } else if (type == "path" || type == "volpath" || type == "simplepath" || type == "bdpt" ||
               type == "directlighting" || type == "simplevolpath") {
        LOG().warning("integrator '" + type + "' mapped to 'distributed' (for comparison with pbrt)", loc);
        in.type = "distributed";
    } else {
        LOG().error("unknown integrator '" + type + "' (supported: whitted, distributed); using distributed", loc);
        in.type = "distributed";
    }
    in.maxDepth = ps.getInt("maxdepth", 5);
    if (in.maxDepth < 0 || in.maxDepth > 64) {
        LOG().error("maxdepth " + std::to_string(in.maxDepth) + " out of range [0,64]; using 5", loc);
        in.maxDepth = 5;
    }
    Color amb;
    if (ps.getRGB("ambient", SpectrumKind::Unbounded, &amb)) in.ambient = amb;
    in.transparentShadows = ps.getBool("transparentshadows", false);
    in.minWeight = ps.getFloat("minweight", 0);
    in.caustics = ps.getBool("caustics", true);
    if (in.minWeight < 0 || in.minWeight >= 1) {
        LOG().error("minweight must be in [0,1); using 0 (off)", loc);
        in.minWeight = 0;
    }
    in.lightSamples = ps.getInt("lightsamples", 16);
    if (in.lightSamples < 1 || in.lightSamples > 65536) {
        LOG().error("lightsamples must be in [1,65536]; using 16", loc);
        in.lightSamples = 16;
    }
    std::string ls = ps.getString("lightsampling", "uniform");
    if (!parseLightSampling(ls, &in.lightSampling)) {
        LOG().error("unknown lightsampling '" + ls + "' (uniform|grid|stratified|halton); using uniform", loc);
        in.lightSampling = LightSampling::Uniform;
    }
    std::string hr = ps.getString("haltonrandomization", "cp");
    if (hr != "cp" && hr != "none") {
        LOG().error("unknown haltonrandomization '" + hr + "' (cp|none); using cp", loc);
        hr = "cp";
    }
    in.haltonRandomize = hr == "cp";
    int eff = effectiveLightSamples(in.lightSampling, in.lightSamples);
    if (eff != in.lightSamples)
        LOG().warning("lightsampling " + ls + " needs a square number of samples: lightsamples " +
                      std::to_string(in.lightSamples) + " -> " + std::to_string(eff), loc);
    in.branchingFactor = ps.getInt("branchingfactor", 1);
    if (in.branchingFactor < 1 || in.branchingFactor > 4096) {
        LOG().error("branchingfactor must be in [1,4096]; using 1", loc);
        in.branchingFactor = 1;
    }
    if (type == "whitted" && (ps.has("branchingfactor") || ps.has("lightsampling")))
        LOG().warning("branchingfactor/lightsampling only affect the distributed integrator", loc);
    ignoreQuietly(ps, {"lightsampler", "regularize"}, "Integrator");
    ps.reportUnused("Integrator \"" + type + "\"");
}

void SceneBuilder::accelerator(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    LOG().warning("Accelerator \"" + type + "\" ignored: every ray is tested against every primitive", loc);
    for (const auto& p : ps.params) p.used = true;
}

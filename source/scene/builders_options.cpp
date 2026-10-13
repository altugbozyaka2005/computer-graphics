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
    if (type == "perspective") {
        c.type = type;
    } else {
        LOG().error("unsupported camera type '" + type + "' (supported: perspective); using perspective", loc);
        c.type = "perspective";
    }
    if (!ctm.valid()) {
        LOG().error("camera transform is singular; using identity", loc);
        c.worldFromCamera = Transform();
    } else {
        c.worldFromCamera = ctm.inverse();
    }
    c.fov = ps.getFloat("fov", 90);
    if (!(c.fov > 0 && c.fov < 180)) {
        LOG().error("camera fov " + std::to_string(c.fov) + " out of range (0,180); using 90", loc);
        c.fov = 90;
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
    ignoreQuietly(ps, {"iso", "whitebalance", "sensor", "savefp16", "maxcomponentvalue", "diagonal", "pixelbounds"},
                  "Film");
    ps.reportUnused("Film \"" + type + "\"");
}

void SceneBuilder::sampler(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    SamplerSettings& s = scene_->sampler;
    scene_->samplerSpecified = true;
    if (type != "independent")
        LOG().warning("sampler '" + type + "' not implemented; using independent random pixel samples", loc);
    s.pixelSamples = ps.getInt("pixelsamples", 16);
    if (s.pixelSamples <= 0) {
        LOG().error("pixelsamples must be > 0; using 16", loc);
        s.pixelSamples = 16;
    }
    s.seed = ps.getInt("seed", 0);
    ignoreQuietly(ps, {"randomization", "xsamples", "ysamples", "jitter"}, "Sampler");
    ps.reportUnused("Sampler \"" + type + "\"");
}

void SceneBuilder::pixelFilter(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    LOG().warning("PixelFilter \"" + type + "\" ignored: pixel samples are averaged with equal weights (box)", loc);
    for (const auto& p : ps.params) p.used = true;
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
    ignoreQuietly(ps, {"lightsampler", "regularize"}, "Integrator");
    ps.reportUnused("Integrator \"" + type + "\"");
}

void SceneBuilder::accelerator(const std::string& type, const ParamSet& ps, const FileLoc& loc) {
    LOG().warning("Accelerator \"" + type + "\" ignored: every ray is tested against every primitive", loc);
    for (const auto& p : ps.params) p.used = true;
}

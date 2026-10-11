// CGR26_renderer: physically based renderer for the CGR 2026 coursework.
// Usage: CGR26_renderer <scene.pbrt> [options]   (see --help)
#include <cstdio>
#include <ctime>
#include <exception>
#include <iostream>
#include <new>
#include <string>
#include <thread>

#include "core/image.h"
#include "core/log.h"
#include "render/renderer.h"
#include "scene/parser.h"

namespace {

const char* kUsage =
    "Usage: CGR26_renderer <scene.pbrt> [options]\n"
    "Options (override the scene file; every override is recorded in the log):\n"
    "  --outdir DIR          output directory (default: the executable's directory, i.e. output/)\n"
    "  --out NAME            output file stem (default: stem of the Film \"filename\")\n"
    "  --threads N           worker threads (default: all hardware threads)\n"
    "  --seed N              random seed (default 0)\n"
    "  --spp N               camera rays per pixel\n"
    "  --integrator I        whitted | distributed\n"
    "  --maxdepth N          maximum ray depth\n"
    "  --lightsamples N      DRT shadow rays per area light\n"
    "  --res WxH             film resolution\n"
    "  --ppm                 also write an 8-bit PPM\n"
    "  --quiet               no progress output\n";

std::string dirName(const std::string& p) {
    size_t s = p.find_last_of('/');
    return s == std::string::npos ? "." : (s == 0 ? "/" : p.substr(0, s));
}
std::string stemOf(const std::string& p) {
    size_t s = p.find_last_of('/');
    std::string b = s == std::string::npos ? p : p.substr(s + 1);
    size_t d = b.find_last_of('.');
    return d == std::string::npos || d == 0 ? b : b.substr(0, d);
}
bool toInt(const std::string& s, long* v) {
    try {
        size_t idx;
        *v = std::stol(s, &idx);
        return idx == s.size();
    } catch (...) {
        return false;
    }
}
std::string nowString() {
    std::time_t t = std::time(nullptr);
    char buf[64];
    std::strftime(buf, sizeof buf, "%Y-%m-%d %H:%M:%S", std::localtime(&t));
    return buf;
}
std::string fmt(double v, int prec = 3) {
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.*f", prec, v);
    return buf;
}

struct CliOverrides {
    long spp = -1, maxDepth = -1, lightSamples = -1, xres = -1, yres = -1;
    std::string integrator;
};

int run(int argc, char** argv) {
    std::string scenePath;
    RenderOptions opt;
    CliOverrides ov;
    std::string cmdline;
    for (int i = 0; i < argc; ++i) cmdline += (i ? " " : "") + std::string(argv[i]);

    auto need = [&](int& i) -> std::string {
        if (i + 1 >= argc) throw std::runtime_error(std::string("missing value after ") + argv[i]);
        return argv[++i];
    };
    try {
        for (int i = 1; i < argc; ++i) {
            std::string a = argv[i];
            long n;
            auto num = [&](long* out, long lo) {
                std::string v = need(i);
                if (!toInt(v, &n) || n < lo) throw std::runtime_error("invalid value '" + v + "' for " + a);
                *out = n;
            };
            if (a == "--help" || a == "-h") { std::cout << kUsage; return 0; }
            else if (a == "--outdir") opt.outDir = need(i);
            else if (a == "--out") opt.outStem = need(i);
            else if (a == "--threads") { long t; num(&t, 1); opt.threads = (int)t; }
            else if (a == "--seed") { long t; num(&t, 0); opt.seed = (uint64_t)t; }
            else if (a == "--spp") num(&ov.spp, 1);
            else if (a == "--maxdepth") num(&ov.maxDepth, 0);
            else if (a == "--lightsamples") num(&ov.lightSamples, 1);
            else if (a == "--integrator") ov.integrator = need(i);
            else if (a == "--res") {
                std::string v = need(i);
                size_t x = v.find('x');
                long w, h;
                if (x == std::string::npos || !toInt(v.substr(0, x), &w) || !toInt(v.substr(x + 1), &h) || w < 1 ||
                    h < 1)
                    throw std::runtime_error("invalid --res '" + v + "' (expected WxH)");
                ov.xres = w;
                ov.yres = h;
            } else if (a == "--ppm") opt.writePPM = true;
            else if (a == "--quiet") opt.quiet = true;
            else if (!a.empty() && a[0] == '-') throw std::runtime_error("unknown option '" + a + "'");
            else if (scenePath.empty()) scenePath = a;
            else throw std::runtime_error("more than one scene file given ('" + scenePath + "', '" + a + "')");
        }
        if (scenePath.empty()) throw std::runtime_error("no scene file given");
    } catch (const std::exception& e) {
        std::cerr << "CGR26_renderer: " << e.what() << "\n\n" << kUsage;
        return 2;
    }

    if (opt.outDir.empty()) opt.outDir = dirName(argv[0]);
    LOG().setEcho(opt.quiet);
    Timer total;
    LOG().raw("==== CGR26_renderer log ====");
    LOG().info("date: " + nowString());
    LOG().info("command: " + cmdline);
    LOG().info("scene: " + scenePath);
    LOG().info("hardware threads: " + std::to_string(std::thread::hardware_concurrency()));

    // ------------------------------------------------------------ parse
    Scene scene;
    Timer tParse;
    bool ok = parseScene(scenePath, &scene);
    double parseSec = tParse.seconds();
    std::string stem = !opt.outStem.empty() ? opt.outStem
                                             : (scene.film.filenameSpecified ? stemOf(scene.film.filename) : stemOf(scenePath));
    if (stem.empty()) stem = "render";
    opt.outStem = stem;
    std::string logPath = opt.outDir + "/" + stem + ".log";
    if (!LOG().openFile(logPath)) {
        std::cerr << "CGR26_renderer: cannot write to output directory '" << opt.outDir << "'\n";
        return 1;
    }
    if (!ok) {
        LOG().raw("---- result ----");
        LOG().raw("FAILED: scene could not be parsed; no image written.");
        LOG().raw("errors: " + std::to_string(LOG().errorCount()) + ", warnings: " +
                  std::to_string(LOG().warningCount()));
        LOG().close();
        return 1;
    }

    scene.prepare();

    // ------------------------------------------------------------ overrides & defaults
    if (!ov.integrator.empty()) {
        if (ov.integrator != "whitted" && ov.integrator != "distributed")
            LOG().error("--integrator must be whitted or distributed; ignored");
        else { scene.integrator.type = ov.integrator; LOG().info("override: integrator = " + ov.integrator); }
    }
    bool whitted = scene.integrator.type == "whitted";
    if (!scene.samplerSpecified) {
        scene.sampler.pixelSamples = whitted ? 1 : 16;
        LOG().info(std::string("no Sampler given; default ") +
                   (whitted ? "1 ray through the pixel centre (classic Whitted)" : "16 random samples per pixel"));
    }
    if (ov.spp > 0) { scene.sampler.pixelSamples = (int)ov.spp; LOG().info("override: spp = " + std::to_string(ov.spp)); }
    if (ov.maxDepth >= 0) { scene.integrator.maxDepth = (int)ov.maxDepth; LOG().info("override: maxdepth = " + std::to_string(ov.maxDepth)); }
    if (ov.lightSamples > 0) { scene.integrator.lightSamples = (int)ov.lightSamples; LOG().info("override: lightsamples = " + std::to_string(ov.lightSamples)); }
    if (ov.xres > 0) { scene.film.xRes = (int)ov.xres; scene.film.yRes = (int)ov.yres; LOG().info("override: resolution"); }
    if (!scene.film.tonemapSpecified) scene.film.tonemap.op = whitted ? "none" : "reinhard";

    // ------------------------------------------------------------ scene summary
    size_t tris = 0;
    for (auto& m : scene.meshes) tris += m->indices.size() / 3;
    const IntegratorSettings& is = scene.integrator;
    LOG().info("integrator: " + is.type + ", maxdepth " + std::to_string(is.maxDepth) +
               (whitted ? "" : ", lightsamples " + std::to_string(is.lightSamples)));
    LOG().info("camera: " + scene.camera.type + ", fov " + fmt(scene.camera.fov, 2) + ", lensradius " +
               fmt(scene.camera.lensRadius, 4) + ", focaldistance " + fmt(scene.camera.focalDistance, 3));
    LOG().info("film: " + std::to_string(scene.film.xRes) + "x" + std::to_string(scene.film.yRes) + ", " +
               std::to_string(scene.sampler.pixelSamples) + " spp, tonemap " + scene.film.tonemap.op +
               (scene.film.tonemap.op == "reinhard" ? " (" + scene.film.tonemap.mode + ")" : ""));
    LOG().info("scene: " + std::to_string(scene.primitiveCount()) + " primitives (" + std::to_string(tris) +
               " triangles, " + std::to_string(scene.unbounded.size()) + " planes), " +
               std::to_string(scene.deltaLights.size()) + " point/spot/distant lights, " +
               std::to_string(scene.areaLights.size()) + " area lights, " + std::to_string(scene.objects.size()) +
               " objects, " +
               std::to_string(scene.materials.size() - 1) + " materials" + (scene.hasEnv ? ", environment" : ""));
    if (scene.deltaLights.empty() && scene.areaLights.empty() && !scene.hasEnv)
        LOG().warning("scene has no light sources; the image will be black (apart from ambient terms)");

    // ------------------------------------------------------------ render
    LOG().info("rendering with " + std::to_string(opt.threads > 0 ? opt.threads : (int)std::thread::hardware_concurrency()) +
               " threads ...");
    RenderResult rr = renderImage(scene, opt);
    if (rr.stats.nanSamples)
        LOG().warning(std::to_string(rr.stats.nanSamples) + " samples were NaN/Inf and were discarded");

    // ------------------------------------------------------------ output
    Timer tOut;
    ToneMapReport tmr;
    Image ldr = toneMapAndEncode(rr.hdr, scene.film.tonemap, &tmr);
    std::string base = opt.outDir + "/" + stem;
    bool wok = writePNG(base + ".png", ldr);
    if (!wok) LOG().error("could not write " + base + ".png");
    if (!writePFM(base + ".pfm", rr.hdr)) LOG().error("could not write " + base + ".pfm");
    if (opt.writePPM && !writePPM(base + ".ppm", ldr)) LOG().error("could not write " + base + ".ppm");
    double outSec = tOut.seconds();
    if (scene.film.tonemap.op == "reinhard")
        LOG().info("Reinhard: mode " + scene.film.tonemap.mode + ", log-average luminance " + fmt(tmr.logAverageLum, 5) +
                   ", max luminance " + fmt(tmr.maxLum, 5) + ", scale " + fmt(tmr.scale, 5) + ", white point " +
                   fmt(tmr.usedWhite, 5) + (scene.film.tonemap.whitePoint > 0 ? "" : " (auto = max)"));
    LOG().info("wrote " + base + ".png (display), " + base + ".pfm (linear HDR)" +
               (opt.writePPM ? ", " + base + ".ppm" : ""));

    // ------------------------------------------------------------ profile
    const RayStats& s = rr.stats;
    uint64_t rays = s.cameraRays + s.shadowRays + s.secondaryRays;
    LOG().raw("---- profile ----");
    LOG().raw("parse+load (s):      " + fmt(parseSec, 4));
    LOG().raw("render (s):          " + fmt(rr.seconds, 4));
    LOG().raw("tonemap+write (s):   " + fmt(outSec, 4));
    LOG().raw("total (s):           " + fmt(total.seconds(), 4));
    LOG().raw("camera rays:         " + std::to_string(s.cameraRays));
    LOG().raw("secondary rays:      " + std::to_string(s.secondaryRays));
    LOG().raw("shadow rays:         " + std::to_string(s.shadowRays));
    LOG().raw("ray-primitive tests: " + std::to_string(s.primTests));
    if (rr.seconds > 0) LOG().raw("Mrays/s:             " + fmt(rays / rr.seconds / 1e6, 3));
    LOG().raw("---- result ----");
    LOG().raw(std::string(wok ? "OK" : "FAILED") + ": errors: " + std::to_string(LOG().errorCount()) +
              ", warnings: " + std::to_string(LOG().warningCount()));
    LOG().close();
    if (!opt.quiet) std::cout << "log: " << logPath << "\n";
    return wok ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        return run(argc, argv);
    } catch (const std::bad_alloc&) {
        LOG().error("out of memory");
    } catch (const std::exception& e) {
        LOG().error(std::string("internal error: ") + e.what());
    } catch (...) {
        LOG().error("internal error: unknown exception");
    }
    LOG().raw("FAILED: aborted after an internal error");
    LOG().close();
    return 3;
}

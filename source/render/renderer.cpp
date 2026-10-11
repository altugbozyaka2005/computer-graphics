#include "renderer.h"

#include <atomic>
#include <cstdio>
#include <memory>
#include <mutex>
#include <thread>

#include "camera.h"
#include "integrators.h"

namespace {

std::unique_ptr<Integrator> makeIntegrator(const Scene& scene) {
    if (scene.integrator.type == "whitted") return std::make_unique<WhittedIntegrator>(scene);
    return std::make_unique<DistributedIntegrator>(scene);
}

int threadCount(int requested) {
    if (requested > 0) return requested;
    unsigned hc = std::thread::hardware_concurrency();
    return hc ? (int)hc : 4;
}

// One independent, reproducible random stream per pixel.
RNG pixelRNG(int px, int py, uint64_t seed) {
    uint64_t key = hashCombine(hashCombine((uint64_t)px, (uint64_t)py), seed);
    return RNG(key, mixBits(key ^ 0x5bd1e995ULL));
}

}  // namespace

RenderResult renderImage(const Scene& scene, const RenderOptions& opt) {
    RenderResult res;
    const FilmSettings& film = scene.film;
    int x0 = (int)std::ceil(film.xRes * film.crop[0]), x1 = (int)std::ceil(film.xRes * film.crop[1]);
    int y0 = (int)std::ceil(film.yRes * film.crop[2]), y1 = (int)std::ceil(film.yRes * film.crop[3]);
    if (x1 <= x0) x1 = x0 + 1;
    if (y1 <= y0) y1 = y0 + 1;
    int w = x1 - x0, h = y1 - y0;
    res.hdr = Image(w, h);
    Camera cam(scene.camera, film.xRes, film.yRes);
    auto integ = makeIntegrator(scene);
    int spp = scene.sampler.pixelSamples;

    const int tile = 16;
    int tilesX = (w + tile - 1) / tile, tilesY = (h + tile - 1) / tile;
    int nTiles = tilesX * tilesY;
    std::atomic<int> next{0}, done{0};
    std::mutex mu;
    Timer timer;

    auto worker = [&]() {
        tlsStats = RayStats();
        while (true) {
            int t = next.fetch_add(1);
            if (t >= nTiles) break;
            int tx = t % tilesX, ty = t / tilesX;
            for (int y = ty * tile; y < std::min(h, (ty + 1) * tile); ++y)
                for (int x = tx * tile; x < std::min(w, (tx + 1) * tile); ++x) {
                    int px = x0 + x, py = y0 + y;
                    RNG rng = pixelRNG(px, py, opt.seed + (uint64_t)scene.sampler.seed);
                    Color sum(0);
                    for (int s = 0; s < spp; ++s) {
                        // One sample: the pixel centre (classic Whitted); several samples:
                        // random positions inside the pixel.
                        Vec2 off = spp == 1 ? Vec2(0.5, 0.5) : rng.uniform2();
                        Vec2 uLens = rng.uniform2();
                        Ray ray = cam.generateRay(Vec2(px + off.x, py + off.y), uLens);
                        ++tlsStats.cameraRays;
                        Color c = integ->Li(ray, rng);
                        if (!c.isFinite()) {
                            ++tlsStats.nanSamples;
                            continue;
                        }
                        sum += c;
                    }
                    res.hdr.at(x, y) = sum / (double)spp;
                }
            int d = ++done;
            if (!opt.quiet && (d % std::max(1, nTiles / 20) == 0 || d == nTiles)) {
                std::lock_guard<std::mutex> lock(mu);
                std::fprintf(stdout, "\r  rendering: %3d%%  (%.1fs)", (int)(100.0 * d / nTiles), timer.seconds());
                std::fflush(stdout);
            }
        }
        std::lock_guard<std::mutex> lock(mu);
        res.stats.add(tlsStats);
    };

    std::vector<std::thread> pool;
    for (int i = 0; i < threadCount(opt.threads); ++i) pool.emplace_back(worker);
    for (auto& th : pool) th.join();
    if (!opt.quiet) std::fprintf(stdout, "\n");
    res.seconds = timer.seconds();
    return res;
}

// Image formation: pixel loop over tiles on std::thread workers with
// deterministic per-pixel random streams.
#pragma once

#include <string>

#include "../core/image.h"
#include "../core/log.h"
#include "../scene/scene.h"

struct RenderOptions {
    int threads = 0;     // 0 = hardware concurrency
    uint64_t seed = 0;
    std::string outDir;  // output directory
    std::string outStem; // output file stem (without extension)
    bool writePPM = false;
    bool quiet = false;
    bool costMap = false;  // also record per-pixel intersection cost (see RenderResult::cost)
};

struct RenderResult {
    Image hdr;
    // With RenderOptions::costMap: per pixel, averaged over its camera rays, the ray-box tests (r),
    // ray-primitive tests (g) and rays traced (b) for everything that camera ray caused.
    Image cost;
    RayStats stats;
    double seconds = 0;
};

RenderResult renderImage(const Scene& scene, const RenderOptions& opt);

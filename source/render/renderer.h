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
};

struct RenderResult {
    Image hdr;
    RayStats stats;
    double seconds = 0;
};

RenderResult renderImage(const Scene& scene, const RenderOptions& opt);

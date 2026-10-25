#include "sampler.h"

#include <utility>

#include "../core/sampling.h"

std::string SamplerSettings::describe() const {
    if (type == "stratified")
        return "stratified " + std::to_string(xSamples) + "x" + std::to_string(ySamples) +
               (jitter ? " (jittered)" : " (regular grid, cell centres)");
    if (type == "halton")
        return "halton, " + std::to_string(pixelSamples) + " spp" +
               (randomize ? " (Cranley-Patterson rotation per pixel)" : " (no randomization)");
    return "independent, " + std::to_string(pixelSamples) + " spp" +
           (pixelSamples == 1 ? " (pixel centre)" : " (uniform random)");
}

void PixelSampler::startPixel(RNG& rng) {
    if (s_.type == "stratified") {
        // Pair film and lens strata through a random permutation, so that the two
        // stratified 2-D patterns are not correlated (pbrt shuffles each dimension).
        int n = spp();
        lensPerm_.resize(n);
        for (int i = 0; i < n; ++i) lensPerm_[i] = i;
        if (s_.jitter)
            for (int i = n - 1; i > 0; --i) std::swap(lensPerm_[i], lensPerm_[rng.nextU32() % (uint32_t)(i + 1)]);
    } else if (s_.type == "halton" && s_.randomize) {
        for (double& v : shift_) v = rng.uniform();
    }
}

void PixelSampler::get(int i, RNG& rng, Vec2* film, Vec2* lens) {
    if (s_.type == "stratified") {
        int xs = s_.xSamples, ys = s_.ySamples;
        auto cell = [&](int k) {
            double jx = s_.jitter ? rng.uniform() : 0.5;
            double jy = s_.jitter ? rng.uniform() : 0.5;
            return Vec2((k % xs + jx) / xs, (k / xs + jy) / ys);
        };
        *film = cell(i);
        *lens = cell(lensPerm_[i]);
    } else if (s_.type == "halton") {
        *film = Vec2(cpRotate(radicalInverse(2, (uint64_t)i), shift_[0]), cpRotate(radicalInverse(3, (uint64_t)i), shift_[1]));
        *lens = Vec2(cpRotate(radicalInverse(5, (uint64_t)i), shift_[2]), cpRotate(radicalInverse(7, (uint64_t)i), shift_[3]));
    } else {
        // Same order of random numbers as the Module 1 renderer (identical images).
        *film = spp() == 1 ? Vec2(0.5, 0.5) : rng.uniform2();
        *lens = rng.uniform2();
    }
}

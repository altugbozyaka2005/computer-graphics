// Pixel samplers (pbrt-v4 Chapter 8): where inside the pixel, and where on the lens,
// each camera ray of a pixel goes. Every sample has the same weight, so the pixel value
// is the plain average of its samples (supersampling with a box filter).
//
//  independent : uniform random positions; 1 sample per pixel = the pixel centre (classic ray casting)
//  stratified  : an xsamples x ysamples grid of cells; one sample per cell, at the cell centre
//                ("bool jitter" false: regular-grid supersampling) or at a random point in it
//                (jitter true, the default: jittered supersampling)
//  halton      : the first N points of the 2-D Halton sequence (bases 2,3 on the film, 5,7 on
//                the lens), toroidally shifted per pixel unless "randomization" is "none"
//
// The sampler only places camera rays. All other random decisions (light samples, indirect
// directions) come from the pixel's random stream (see the "lightsampling" integrator option).
#pragma once

#include <string>
#include <vector>

#include "../core/math.h"
#include "../core/rng.h"

struct SamplerSettings {
    std::string type = "independent";  // independent | stratified | halton
    int pixelSamples = 16;             // independent / halton
    int xSamples = 4, ySamples = 4;    // stratified
    bool jitter = true;                // stratified
    bool randomize = true;             // halton: per-pixel Cranley-Patterson rotation
    int seed = 0;
    int samplesPerPixel() const { return type == "stratified" ? xSamples * ySamples : pixelSamples; }
    std::string describe() const;
};

// One per render thread (it keeps per-pixel scratch state).
class PixelSampler {
public:
    explicit PixelSampler(const SamplerSettings& s) : s_(s) {}
    int spp() const { return s_.samplesPerPixel(); }
    // Draws the per-pixel randomisation (lens strata permutation, Halton shift). Call once per pixel.
    void startPixel(RNG& rng);
    // Sample i of the current pixel: film offset inside the pixel in [0,1)^2 and lens sample in [0,1)^2.
    void get(int i, RNG& rng, Vec2* film, Vec2* lens);

private:
    SamplerSettings s_;
    std::vector<int> lensPerm_;  // stratified: lens stratum used by each film stratum
    double shift_[4] = {0, 0, 0, 0};
};

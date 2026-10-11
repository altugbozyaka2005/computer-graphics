// Sampling routines (pbrt-v4 Sections 2.4, A.5).
#pragma once

#include "math.h"

// Shirley-Chiu concentric square-to-disk mapping (area preserving, low distortion).
inline Vec2 sampleUniformDiskConcentric(Vec2 u) {
    double ox = 2 * u.x - 1, oy = 2 * u.y - 1;
    if (ox == 0 && oy == 0) return {0, 0};
    double r, theta;
    if (std::fabs(ox) > std::fabs(oy)) {
        r = ox;
        theta = (Pi / 4) * (oy / ox);
    } else {
        r = oy;
        theta = (Pi / 2) - (Pi / 4) * (ox / oy);
    }
    return {r * std::cos(theta), r * std::sin(theta)};
}

// Directions in a local frame where +z is the surface normal.
inline Vec3 sampleUniformHemisphere(Vec2 u) {
    double z = u.x;
    double r = safeSqrt(1 - z * z);
    double phi = 2 * Pi * u.y;
    return {r * std::cos(phi), r * std::sin(phi), z};
}
inline double uniformHemispherePdf() { return Inv2Pi; }

inline Vec3 sampleUniformSphere(Vec2 u) {
    double z = 1 - 2 * u.x;
    double r = safeSqrt(1 - z * z);
    double phi = 2 * Pi * u.y;
    return {r * std::cos(phi), r * std::sin(phi), z};
}

// Low-distortion uniform triangle sampling (Heitz 2019; pbrt-v4 SampleUniformTriangle).
// Returns barycentrics (b0, b1); b2 = 1 - b0 - b1.
inline Vec2 sampleUniformTriangle(Vec2 u) {
    double b0, b1;
    if (u.x < u.y) {
        b0 = u.x / 2;
        b1 = u.y - b0;
    } else {
        b1 = u.y / 2;
        b0 = u.x - b1;
    }
    return {b0, b1};
}

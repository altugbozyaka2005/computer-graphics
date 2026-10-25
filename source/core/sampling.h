// Sampling routines (pbrt-v4 Sections 2.4, A.5, 8.6).
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

// Radical inverse (van der Corput) of a in the given base: the digits of a mirrored about
// the radix point. The Halton sequence uses one prime base per dimension (pbrt-v4 8.6.1).
inline double radicalInverse(int base, uint64_t a) {
    double invBase = 1.0 / base, invBaseN = 1;
    uint64_t rev = 0;
    while (a) {
        uint64_t next = a / base;
        uint64_t digit = a - next * base;
        rev = rev * base + digit;
        invBaseN *= invBase;
        a = next;
    }
    return std::min(rev * invBaseN, OneMinusEpsilon);
}

// Point i of the two-dimensional Halton sequence (bases 2 and 3).
inline Vec2 halton2D(uint64_t i) { return {radicalInverse(2, i), radicalInverse(3, i)}; }

// Cranley-Patterson rotation: a toroidal shift of a point set by a random offset. It makes
// a deterministic low-discrepancy set an unbiased estimator while keeping its structure.
inline double cpRotate(double v, double shift) {
    v += shift;
    return v >= 1 ? v - 1 : v;
}

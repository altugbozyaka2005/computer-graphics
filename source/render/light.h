// Light sources (pbrt-v4 Chapter 12): point, spot, distant, diffuse area lights
// and a constant "infinite" environment.
#pragma once

#include <string>
#include <vector>

#include "../core/math.h"
#include "../core/rng.h"
#include "../geometry/shape.h"

enum class DeltaLightType { Point, Spot, Distant };

struct DeltaLight {
    DeltaLightType type = DeltaLightType::Point;
    Color I;        // radiant intensity (point/spot) or radiance (distant)
    Vec3 pos;       // point / spot position
    Vec3 dir;       // spot: axis (unit); distant: unit direction TOWARDS the light
    double cosFalloffStart = 1, cosFalloffEnd = 1;  // spot cone (cosines)

    // Incident illumination at p: direction to light, distance (Infinity for
    // distant) and the incident radiance-like term (I/d^2 for point lights).
    void illuminate(const Vec3& p, Vec3* wi, double* dist, Color* Li) const;
};

// A diffuse emitter made of one or more shapes (one per Shape directive).
struct AreaLight {
    Color L;
    bool twoSided = false;
    int nSamples = -1;  // per-light override of "lightsamples"; 0 = never sampled with shadow rays
    std::vector<const Shape*> shapes;

    // Derived by finalize()
    std::vector<double> cdf;  // area CDF over shapes
    double totalArea = 0;
    bool sphere = false;  // single full sphere
    Vec3 repPoint, repNormal;  // representative point for the Whitted integrator

    void finalize();
    // Uniform-by-area sample of a point on the light; pdf (w.r.t. area) is 1 / totalArea.
    SurfaceSample sample(Vec2 u) const;
    // Emitted radiance leaving a point with surface normal n in direction w.
    Color Le(const Vec3& n, const Vec3& w) const { return (twoSided || dot(n, w) > 0) ? L : Color(0); }
};

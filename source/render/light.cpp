#include "light.h"

#include "../core/sampling.h"

static double smoothStep(double x, double a, double b) {
    if (a == b) return (x < a) ? 0 : 1;
    double t = clampd((x - a) / (b - a), 0, 1);
    return t * t * (3 - 2 * t);
}

void DeltaLight::illuminate(const Vec3& p, Vec3* wi, double* dist, Color* Li) const {
    if (type == DeltaLightType::Distant) {
        *wi = dir;
        *dist = Infinity;
        *Li = I;
        return;
    }
    Vec3 d = pos - p;
    double d2 = lengthSquared(d);
    *dist = std::sqrt(d2);
    *wi = d / *dist;
    Color li = I / d2;
    if (type == DeltaLightType::Spot) {
        // pbrt-v4 spotlight falloff: smoothstep between the outer and inner cone.
        double cosTheta = dot(-*wi, dir);
        li *= smoothStep(cosTheta, cosFalloffEnd, cosFalloffStart);
    }
    *Li = li;
}

void AreaLight::finalize() {
    cdf.clear();
    totalArea = 0;
    for (const Shape* s : shapes) {
        totalArea += s->area();
        cdf.push_back(totalArea);
    }
    for (auto& c : cdf) c /= totalArea;
    if (!cdf.empty()) cdf.back() = 1.0;
    sphere = shapes.size() == 1 && std::string(shapes[0]->typeName()) == "sphere";

    // Representative point for the WSRT (area-weighted centroid, average normal).
    repPoint = Vec3(0);
    Vec3 nSum(0);
    for (const Shape* s : shapes) {
        double w = s->area() / totalArea;
        repPoint += s->centroid() * w;
        nSum += s->sample(Vec2(0.5, 0.5)).n * s->area();
    }
    repNormal = length(nSum) > 0 ? normalize(nSum) : Vec3(0, 0, 1);
}

SurfaceSample AreaLight::sample(Vec2 u) const {
    // Pick a shape in proportion to its area, then a uniform point on it.
    size_t i = std::lower_bound(cdf.begin(), cdf.end(), u.x) - cdf.begin();
    if (i >= cdf.size()) i = cdf.size() - 1;
    double lo = i == 0 ? 0 : cdf[i - 1];
    double width = cdf[i] - lo;
    double ux = width > 0 ? clampd((u.x - lo) / width, 0, OneMinusEpsilon) : 0.5;
    return shapes[i]->sample(Vec2(ux, u.y));
}

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

    // An emissive rectangle is usually two triangles (trianglemesh or bilinearmesh). Detect a
    // parallelogram so that the structured sample patterns can map [0,1)^2 straight onto it.
    parallelogram = false;
    if (shapes.size() == 2 && std::string(shapes[0]->typeName()) == "triangle" &&
        std::string(shapes[1]->typeName()) == "triangle") {
        const Triangle* t0 = static_cast<const Triangle*>(shapes[0]);
        const Triangle* t1 = static_cast<const Triangle*>(shapes[1]);
        Vec3 v[6];
        t0->vertices(&v[0], &v[1], &v[2]);
        t1->vertices(&v[3], &v[4], &v[5]);
        double scaleLen = 0;
        for (auto& p : v) scaleLen = std::max(scaleLen, length(p - v[0]));
        double tol = 1e-9 * (1 + scaleLen);
        std::vector<Vec3> uniq;
        for (auto& p : v) {
            bool dup = false;
            for (auto& q : uniq) dup = dup || length(p - q) <= tol;
            if (!dup) uniq.push_back(p);
        }
        if (uniq.size() == 4) {
            // A corner a with neighbours b, c such that the fourth vertex d is b + c - a.
            for (int a = 0; a < 4 && !parallelogram; ++a)
                for (int b = 0; b < 4 && !parallelogram; ++b)
                    for (int c = b + 1; c < 4 && !parallelogram; ++c) {
                        if (a == b || a == c) continue;
                        int d = 6 - a - b - c;
                        if (length(uniq[b] + uniq[c] - uniq[a] - uniq[d]) <= tol) {
                            p0 = uniq[a];
                            e1 = uniq[b] - uniq[a];
                            e2 = uniq[c] - uniq[a];
                            parallelogram = length(cross(e1, e2)) > 0;
                        }
                    }
            // Both triangles must be coplanar halves with the same orientation.
            if (parallelogram) {
                paraNormal = t0->orientedNormal(1.0 / 3, 1.0 / 3);
                parallelogram = dot(paraNormal, t1->orientedNormal(1.0 / 3, 1.0 / 3)) > 1 - 1e-9 &&
                                std::fabs(dot(paraNormal, normalize(cross(e1, e2)))) > 1 - 1e-9 &&
                                std::fabs(length(cross(e1, e2)) - totalArea) <= 1e-9 * (1 + totalArea);
            }
        }
    }

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

bool parseLightSampling(const std::string& s, LightSampling* out) {
    if (s == "uniform" || s == "random" || s == "independent") *out = LightSampling::Uniform;
    else if (s == "grid" || s == "regular") *out = LightSampling::Grid;
    else if (s == "stratified" || s == "jittered") *out = LightSampling::Stratified;
    else if (s == "halton") *out = LightSampling::Halton;
    else return false;
    return true;
}

const char* lightSamplingName(LightSampling s) {
    switch (s) {
        case LightSampling::Uniform: return "uniform";
        case LightSampling::Grid: return "grid";
        case LightSampling::Stratified: return "stratified";
        case LightSampling::Halton: return "halton";
    }
    return "?";
}

int effectiveLightSamples(LightSampling s, int requested) {
    requested = std::max(1, requested);
    if (s == LightSampling::Grid || s == LightSampling::Stratified) {
        int n = std::max(1, (int)std::lround(std::sqrt((double)requested)));
        return n * n;
    }
    return requested;
}

LightSamplePattern::LightSamplePattern(LightSampling s, int count, bool randomizeHalton, RNG& rng)
    : s_(s), n_(std::max(1, (int)std::lround(std::sqrt((double)count)))) {
    if (s == LightSampling::Halton && randomizeHalton) {
        sx_ = rng.uniform();
        sy_ = rng.uniform();
    }
}

Vec2 LightSamplePattern::get(int i, RNG& rng) const {
    switch (s_) {
        case LightSampling::Uniform:
            return rng.uniform2();
        case LightSampling::Grid:
            return Vec2((i % n_ + 0.5) / n_, (i / n_ + 0.5) / n_);
        case LightSampling::Stratified: {
            double jx = rng.uniform(), jy = rng.uniform();
            return Vec2((i % n_ + jx) / n_, (i / n_ + jy) / n_);
        }
        case LightSampling::Halton: {
            Vec2 h = halton2D((uint64_t)i);
            return Vec2(cpRotate(h.x, sx_), cpRotate(h.y, sy_));
        }
    }
    return Vec2(0.5, 0.5);
}

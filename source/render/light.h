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
    int nSamples = -1;  // per-light override of "lightsamples"; 0 = visible-only (lights nothing)
    std::vector<const Shape*> shapes;

    // Derived by finalize()
    std::vector<double> cdf;  // area CDF over shapes
    double totalArea = 0;
    bool sphere = false;  // single full sphere
    // Two triangles forming a parallelogram (an emissive rectangle): p = p0 + u e1 + v e2.
    bool parallelogram = false;
    Vec3 p0, e1, e2, paraNormal;
    Vec3 repPoint, repNormal;  // representative point for the Whitted integrator

    void finalize();
    // Uniform-by-area sample of a point on the light; pdf (w.r.t. area) is 1 / totalArea.
    SurfaceSample sample(Vec2 u) const;
    // Also uniform by area, but mapping the unit square onto the light so that strata of
    // [0,1)^2 stay compact cells on the light (exact n x n cells on a rectangle). Used by the
    // structured sample patterns; uniform random sampling keeps sample() (Module 1 images).
    SurfaceSample sampleStratified(Vec2 u) const { return parallelogram ? SurfaceSample{p0 + e1 * u.x + e2 * u.y, paraNormal} : sample(u); }
    // Emitted radiance leaving a point with surface normal n in direction w.
    Color Le(const Vec3& n, const Vec3& w) const { return (twoSided || dot(n, w) > 0) ? L : Color(0); }
};

// Sample patterns for the shadow rays towards an area light (Module 2 sampler comparison).
// Each shading point draws its own set of N points in [0,1)^2:
//  uniform    : N independent uniform random points
//  grid       : the light divided into n x n cells (n = round(sqrt N)), one sample at the
//               centre of each cell; deterministic, the same points for every shading point
//  stratified : n x n cells with one random point per cell (jittered grid)
//  halton     : the first N points of the 2-D Halton sequence (bases 2, 3), toroidally shifted
//               by a random offset per shading point (Cranley-Patterson rotation), unless
//               "haltonrandomization" is "none"
enum class LightSampling { Uniform, Grid, Stratified, Halton };
bool parseLightSampling(const std::string& s, LightSampling* out);
const char* lightSamplingName(LightSampling s);
// Number of points actually used for a requested count (grid/stratified round to n*n).
int effectiveLightSamples(LightSampling s, int requested);

// Generates the points of one shading point's pattern on demand (no allocation).
class LightSamplePattern {
public:
    // count must already be effective (see effectiveLightSamples).
    LightSamplePattern(LightSampling s, int count, bool randomizeHalton, RNG& rng);
    Vec2 get(int i, RNG& rng) const;
    bool structured() const { return s_ != LightSampling::Uniform; }

private:
    LightSampling s_;
    int n_;  // grid side
    double sx_ = 0, sy_ = 0;
};

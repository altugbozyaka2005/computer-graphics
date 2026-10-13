// Rays, bounding boxes and geometric primitives (pbrt-v4 Chapter 6 conventions).
#pragma once

#include <memory>
#include <vector>

#include "../core/math.h"
#include "../core/transform.h"
#include "../render/texture.h"

struct Ray {
    Vec3 o, d;
    Ray() {}
    Ray(const Vec3& o_, const Vec3& d_) : o(o_), d(d_) {}
    Vec3 at(double t) const { return o + d * t; }
};

// Smallest parametric distance accepted as a hit. Self-intersection is mainly
// avoided by offsetting ray origins (see offsetRayOrigin) so this can be tiny.
constexpr double kRayTMin = 1e-9;

struct AABB {
    Vec3 lo{Infinity, Infinity, Infinity}, hi{-Infinity, -Infinity, -Infinity};
    void expand(const Vec3& p) { lo = vmin(lo, p); hi = vmax(hi, p); }
    void expand(const AABB& b) { lo = vmin(lo, b.lo); hi = vmax(hi, b.hi); }
    Vec3 centroid() const { return (lo + hi) * 0.5; }
    Vec3 diagonal() const { return hi - lo; }
    bool empty() const { return lo.x > hi.x || lo.y > hi.y || lo.z > hi.z; }
    double surfaceArea() const {
        if (empty()) return 0;
        Vec3 d = diagonal();
        return 2 * (d.x * d.y + d.x * d.z + d.y * d.z);
    }
    int maxExtent() const {
        Vec3 d = diagonal();
        if (d.x > d.y && d.x > d.z) return 0;
        return d.y > d.z ? 1 : 2;
    }
    // Offset of p inside the box: 0 at lo, 1 at hi.
    Vec3 offset(const Vec3& p) const {
        Vec3 o = p - lo;
        if (hi.x > lo.x) o.x /= hi.x - lo.x;
        if (hi.y > lo.y) o.y /= hi.y - lo.y;
        if (hi.z > lo.z) o.z /= hi.z - lo.z;
        return o;
    }
};

class Shape;
struct AreaLight;

struct Hit {
    double t = Infinity;
    Vec3 p;
    Vec3 ng;  // geometric normal, oriented as the surface (outward / winding / ReverseOrientation)
    Vec3 ns;  // shading normal (interpolated vertex normals), same hemisphere as ng
    Vec2 uv;
    const Shape* shape = nullptr;
};

// Sample on a shape's surface for area-light sampling.
struct SurfaceSample {
    Vec3 p, n;
};

class Shape {
public:
    virtual ~Shape() {}
    virtual bool intersect(const Ray& r, double tMax, Hit* hit) const = 0;
    virtual bool intersectP(const Ray& r, double tMax) const = 0;
    virtual AABB bounds() const = 0;
    virtual bool bounded() const { return true; }
    virtual double area() const = 0;
    // Uniform-by-area sample from u in [0,1)^2.
    virtual SurfaceSample sample(Vec2 u) const = 0;
    virtual Vec3 centroid() const { return bounds().centroid(); }
    virtual const char* typeName() const = 0;

    int materialId = 0;
    const AreaLight* areaLight = nullptr;
    // Optional alpha (cut-out) mask, pbrt "alpha" parameter: where alpha < 0.5 the
    // surface does not exist, for camera and shadow rays alike.
    TexturePtr alpha;

    bool alphaCut(const Hit& h) const { return alpha && alpha->eval(h.uv).average() < 0.5; }
    // Closest hit / any hit honouring the alpha mask. Only the nearest hit of a
    // shape is tested against the mask (exact for triangles, the usual masked shape).
    bool intersectA(const Ray& r, double tMax, Hit* hit) const {
        if (!alpha) return intersect(r, tMax, hit);
        Hit tmp;
        if (!intersect(r, tMax, &tmp) || alphaCut(tmp)) return false;
        *hit = tmp;
        return true;
    }
    bool intersectPA(const Ray& r, double tMax) const {
        if (!alpha) return intersectP(r, tMax);
        Hit tmp;
        return intersect(r, tMax, &tmp) && !alphaCut(tmp);
    }
};

class Sphere : public Shape {
public:
    Sphere(const Transform& objToWorld, bool reverseOrientation, double radius, double zMin, double zMax,
           double phiMaxDeg);
    bool intersect(const Ray& r, double tMax, Hit* hit) const override;
    bool intersectP(const Ray& r, double tMax) const override;
    AABB bounds() const override;
    double area() const override { return worldArea_; }
    SurfaceSample sample(Vec2 u) const override;
    Vec3 centroid() const override { return objToWorld_.point(Vec3(0, 0, 0)); }
    const char* typeName() const override { return "sphere"; }
    bool isFullSphere() const { return full_; }
    double worldRadius() const { return worldRadius_; }

private:
    bool basicIntersect(const Ray& r, double tMax, double* tHit, Vec3* pObj, double* phiOut) const;
    Transform objToWorld_, worldToObj_;
    bool reverse_;
    double radius_, zMin_, zMax_, thetaZMin_, thetaZMax_, phiMax_;
    double worldArea_, worldRadius_;
    bool full_;
};

class Disk : public Shape {
public:
    Disk(const Transform& objToWorld, bool reverseOrientation, double height, double radius, double innerRadius,
         double phiMaxDeg);
    bool intersect(const Ray& r, double tMax, Hit* hit) const override;
    bool intersectP(const Ray& r, double tMax) const override;
    AABB bounds() const override;
    double area() const override { return worldArea_; }
    SurfaceSample sample(Vec2 u) const override;
    Vec3 centroid() const override { return objToWorld_.point(Vec3(0, 0, height_)); }
    const char* typeName() const override { return "disk"; }

private:
    bool basicIntersect(const Ray& r, double tMax, double* tHit, Vec3* pObj, double* phiOut) const;
    Transform objToWorld_, worldToObj_;
    bool reverse_;
    double height_, radius_, innerRadius_, phiMax_;
    double worldArea_;
};

// World-space triangle mesh shared by its triangles.
struct TriangleMesh {
    std::vector<Vec3> p, n;
    std::vector<Vec2> uv;
    std::vector<int> indices;
    bool flipNormals = false;  // ReverseOrientation XOR transform swaps handedness
};

class Triangle : public Shape {
public:
    Triangle(std::shared_ptr<const TriangleMesh> mesh, int triIndex) : mesh_(std::move(mesh)), tri_(triIndex) {}
    bool intersect(const Ray& r, double tMax, Hit* hit) const override;
    bool intersectP(const Ray& r, double tMax) const override;
    AABB bounds() const override;
    double area() const override;
    SurfaceSample sample(Vec2 u) const override;
    Vec3 centroid() const override;
    const char* typeName() const override { return "triangle"; }
    void vertices(Vec3* a, Vec3* b, Vec3* c) const;
    // Geometric normal at barycentrics (b1, b2), applying pbrt's orientation rules.
    Vec3 orientedNormal(double b1, double b2) const;

private:
    bool mt(const Ray& r, double tMax, double* t, double* b1, double* b2) const;
    std::shared_ptr<const TriangleMesh> mesh_;
    int tri_;
};

// Infinite plane (renderer extension; pbrt has no infinite plane). Unbounded:
// kept in a separate list and tested against every ray.
class Plane : public Shape {
public:
    Plane(const Vec3& point, const Vec3& normal, bool reverseOrientation);
    bool intersect(const Ray& r, double tMax, Hit* hit) const override;
    bool intersectP(const Ray& r, double tMax) const override;
    AABB bounds() const override { return AABB(); }
    bool bounded() const override { return false; }
    double area() const override { return Infinity; }
    SurfaceSample sample(Vec2) const override { return {p0_, n_}; }
    Vec3 centroid() const override { return p0_; }
    const char* typeName() const override { return "plane"; }

private:
    Vec3 p0_, n_, s_, t_;
};

// Ray origin pushed off the surface along the geometric normal, on the side of
// the outgoing direction, to avoid self-intersection ("shadow acne").
inline Vec3 offsetRayOrigin(const Vec3& p, const Vec3& ng, const Vec3& dir) {
    double mag = std::max(std::fabs(p.x), std::max(std::fabs(p.y), std::fabs(p.z)));
    double eps = 1e-7 * (1.0 + mag);
    return dot(ng, dir) > 0 ? p + ng * eps : p - ng * eps;
}

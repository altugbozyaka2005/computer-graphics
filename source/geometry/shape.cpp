#include "shape.h"

#include "../core/log.h"
#include "../core/sampling.h"

// ============================================================ Sphere
Sphere::Sphere(const Transform& objToWorld, bool reverseOrientation, double radius, double zMin, double zMax,
               double phiMaxDeg)
    : objToWorld_(objToWorld), worldToObj_(objToWorld.inverse()), reverse_(reverseOrientation), radius_(radius) {
    zMin_ = clampd(std::min(zMin, zMax), -radius, radius);
    zMax_ = clampd(std::max(zMin, zMax), -radius, radius);
    thetaZMin_ = std::acos(clampd(zMin_ / radius, -1, 1));
    thetaZMax_ = std::acos(clampd(zMax_ / radius, -1, 1));
    phiMax_ = radians(clampd(phiMaxDeg, 0, 360));
    full_ = zMin_ <= -radius && zMax_ >= radius && phiMaxDeg >= 360;
    // World-space radius/area assume a similarity transform (uniform scale); the
    // parser warns when that is not the case.
    double sx = length(objToWorld.vector(Vec3(1, 0, 0)));
    double sy = length(objToWorld.vector(Vec3(0, 1, 0)));
    double sz = length(objToWorld.vector(Vec3(0, 0, 1)));
    double s = (sx + sy + sz) / 3.0;
    worldRadius_ = radius * s;
    worldArea_ = phiMax_ * radius * (zMax_ - zMin_) * s * s;
}

bool Sphere::basicIntersect(const Ray& r, double tMax, double* tHit, Vec3* pObj, double* phiOut) const {
    Vec3 o = worldToObj_.point(r.o), d = worldToObj_.vector(r.d);
    double a = dot(d, d);
    double h = dot(o, d);  // b = 2h ("half-b" form)
    // Numerically robust discriminant (pbrt-v4 6.8.5): b^2 - 4ac = 4a (r - |f|)(r + |f|)
    // with f = o - (b / 2a) d, the closest point on the ray to the centre.
    Vec3 f = o - d * (h / a);
    double lf = length(f);
    double disc = a * (radius_ - lf) * (radius_ + lf);
    if (disc < 0) return false;
    double sq = std::sqrt(disc);
    double q = (h >= 0) ? -(h + sq) : -(h - sq);
    double c = dot(o, o) - radius_ * radius_;
    double t0, t1;
    if (q == 0) {
        t0 = t1 = -h / a;
    } else {
        t0 = q / a;
        t1 = c / q;
    }
    if (t0 > t1) std::swap(t0, t1);
    if (t0 > tMax || t1 <= kRayTMin) return false;
    double t = t0;
    if (t <= kRayTMin) {
        t = t1;
        if (t > tMax) return false;
    }
    auto computeHit = [&](double tt, Vec3* p, double* phi) {
        Vec3 ph = o + d * tt;
        ph *= radius_ / length(ph);  // re-project onto the surface
        if (ph.x == 0 && ph.y == 0) ph.x = 1e-5 * radius_;
        double ang = std::atan2(ph.y, ph.x);
        if (ang < 0) ang += 2 * Pi;
        *p = ph;
        *phi = ang;
    };
    auto clipped = [&](const Vec3& p, double phi) {
        return (zMin_ > -radius_ && p.z < zMin_) || (zMax_ < radius_ && p.z > zMax_) || phi > phiMax_;
    };
    Vec3 p;
    double phi;
    computeHit(t, &p, &phi);
    if (clipped(p, phi)) {
        if (t == t1) return false;
        if (t1 > tMax) return false;
        t = t1;
        computeHit(t, &p, &phi);
        if (clipped(p, phi)) return false;
    }
    *tHit = t;
    *pObj = p;
    *phiOut = phi;
    return true;
}

bool Sphere::intersect(const Ray& r, double tMax, Hit* hit) const {
    double t, phi;
    Vec3 p;
    if (!basicIntersect(r, tMax, &t, &p, &phi)) return false;
    hit->t = t;
    hit->p = objToWorld_.point(p);
    Vec3 n = normalize(objToWorld_.normal(p));
    if (reverse_) n = -n;
    hit->ng = hit->ns = n;
    double theta = safeAcos(p.z / radius_);
    double denom = thetaZMax_ - thetaZMin_;
    hit->uv = Vec2(phi / phiMax_, denom != 0 ? (theta - thetaZMin_) / denom : 0);
    hit->shape = this;
    return true;
}

bool Sphere::intersectP(const Ray& r, double tMax) const {
    double t, phi;
    Vec3 p;
    return basicIntersect(r, tMax, &t, &p, &phi);
}

AABB Sphere::bounds() const {
    AABB b;
    for (int i = 0; i < 8; ++i) {
        Vec3 c((i & 1) ? radius_ : -radius_, (i & 2) ? radius_ : -radius_, (i & 4) ? zMax_ : zMin_);
        b.expand(objToWorld_.point(c));
    }
    return b;
}

SurfaceSample Sphere::sample(Vec2 u) const {
    // Uniform over the full sphere (partial spheres are approximated; the parser warns).
    Vec3 pObj = sampleUniformSphere(u) * radius_;
    SurfaceSample s;
    s.p = objToWorld_.point(pObj);
    s.n = normalize(objToWorld_.normal(pObj));
    if (reverse_) s.n = -s.n;
    return s;
}

// ============================================================ Disk
Disk::Disk(const Transform& objToWorld, bool reverseOrientation, double height, double radius, double innerRadius,
           double phiMaxDeg)
    : objToWorld_(objToWorld), worldToObj_(objToWorld.inverse()), reverse_(reverseOrientation), height_(height),
      radius_(radius), innerRadius_(innerRadius) {
    phiMax_ = radians(clampd(phiMaxDeg, 0, 360));
    // Affine maps scale planar areas by a constant factor.
    double areaScale = length(cross(objToWorld.vector(Vec3(1, 0, 0)), objToWorld.vector(Vec3(0, 1, 0))));
    worldArea_ = phiMax_ * 0.5 * (radius_ * radius_ - innerRadius_ * innerRadius_) * areaScale;
}

bool Disk::basicIntersect(const Ray& r, double tMax, double* tHit, Vec3* pObj, double* phiOut) const {
    Vec3 o = worldToObj_.point(r.o), d = worldToObj_.vector(r.d);
    if (d.z == 0) return false;
    double t = (height_ - o.z) / d.z;
    if (t <= kRayTMin || t >= tMax) return false;
    Vec3 p = o + d * t;
    double dist2 = p.x * p.x + p.y * p.y;
    if (dist2 > radius_ * radius_ || dist2 < innerRadius_ * innerRadius_) return false;
    double phi = std::atan2(p.y, p.x);
    if (phi < 0) phi += 2 * Pi;
    if (phi > phiMax_) return false;
    p.z = height_;
    *tHit = t;
    *pObj = p;
    *phiOut = phi;
    return true;
}

bool Disk::intersect(const Ray& r, double tMax, Hit* hit) const {
    double t, phi;
    Vec3 p;
    if (!basicIntersect(r, tMax, &t, &p, &phi)) return false;
    hit->t = t;
    hit->p = objToWorld_.point(p);
    Vec3 n = normalize(objToWorld_.normal(Vec3(0, 0, 1)));
    if (reverse_) n = -n;
    hit->ng = hit->ns = n;
    double rHit = std::sqrt(p.x * p.x + p.y * p.y);
    hit->uv = Vec2(phi / phiMax_, (radius_ - rHit) / (radius_ - innerRadius_));
    hit->shape = this;
    return true;
}

bool Disk::intersectP(const Ray& r, double tMax) const {
    double t, phi;
    Vec3 p;
    return basicIntersect(r, tMax, &t, &p, &phi);
}

AABB Disk::bounds() const {
    AABB b;
    for (int i = 0; i < 4; ++i)
        b.expand(objToWorld_.point(Vec3((i & 1) ? radius_ : -radius_, (i & 2) ? radius_ : -radius_, height_)));
    return b;
}

SurfaceSample Disk::sample(Vec2 u) const {
    // Concentric mapping: uniform by area on the disk.
    Vec2 pd = sampleUniformDiskConcentric(u);
    Vec3 pObj(pd.x * radius_, pd.y * radius_, height_);
    SurfaceSample s;
    s.p = objToWorld_.point(pObj);
    s.n = normalize(objToWorld_.normal(Vec3(0, 0, 1)));
    if (reverse_) s.n = -s.n;
    return s;
}

// ============================================================ Triangle
void Triangle::vertices(Vec3* a, Vec3* b, Vec3* c) const {
    const int* v = &mesh_->indices[3 * tri_];
    *a = mesh_->p[v[0]];
    *b = mesh_->p[v[1]];
    *c = mesh_->p[v[2]];
}

// Moller-Trumbore ray/triangle test in double precision.
bool Triangle::mt(const Ray& r, double tMax, double* tOut, double* b1Out, double* b2Out) const {
    Vec3 p0, p1, p2;
    vertices(&p0, &p1, &p2);
    Vec3 e1 = p1 - p0, e2 = p2 - p0;
    Vec3 pvec = cross(r.d, e2);
    double det = dot(e1, pvec);
    if (det == 0) return false;
    double inv = 1.0 / det;
    Vec3 tvec = r.o - p0;
    double u = dot(tvec, pvec) * inv;
    if (u < 0 || u > 1) return false;
    Vec3 qvec = cross(tvec, e1);
    double v = dot(r.d, qvec) * inv;
    if (v < 0 || u + v > 1) return false;
    double t = dot(e2, qvec) * inv;
    if (t <= kRayTMin || t >= tMax) return false;
    *tOut = t;
    *b1Out = u;
    *b2Out = v;
    return true;
}

Vec3 Triangle::orientedNormal(double b1, double b2) const {
    Vec3 p0, p1, p2;
    vertices(&p0, &p1, &p2);
    // Same orientation as pbrt's Cross(p0 - p2, p1 - p2).
    Vec3 n = normalize(cross(p1 - p0, p2 - p0));
    if (mesh_->flipNormals) n = -n;
    if (!mesh_->n.empty()) {
        const int* v = &mesh_->indices[3 * tri_];
        Vec3 ns = mesh_->n[v[0]] * (1 - b1 - b2) + mesh_->n[v[1]] * b1 + mesh_->n[v[2]] * b2;
        if (lengthSquared(ns) > 0) n = faceForward(n, ns);  // vertex normals are authoritative
    }
    return n;
}

bool Triangle::intersect(const Ray& r, double tMax, Hit* hit) const {
    double t, b1, b2;
    if (!mt(r, tMax, &t, &b1, &b2)) return false;
    double b0 = 1 - b1 - b2;
    const int* v = &mesh_->indices[3 * tri_];
    hit->t = t;
    hit->p = mesh_->p[v[0]] * b0 + mesh_->p[v[1]] * b1 + mesh_->p[v[2]] * b2;
    hit->ng = orientedNormal(b1, b2);
    hit->ns = hit->ng;
    if (!mesh_->n.empty()) {
        Vec3 ns = mesh_->n[v[0]] * b0 + mesh_->n[v[1]] * b1 + mesh_->n[v[2]] * b2;
        if (lengthSquared(ns) > 0) hit->ns = normalize(ns);
    }
    if (!mesh_->uv.empty()) {
        hit->uv = mesh_->uv[v[0]] * b0 + mesh_->uv[v[1]] * b1 + mesh_->uv[v[2]] * b2;
    } else {
        // pbrt default parameterisation: (0,0), (1,0), (1,1)
        hit->uv = Vec2(0, 0) * b0 + Vec2(1, 0) * b1 + Vec2(1, 1) * b2;
    }
    hit->shape = this;
    return true;
}

bool Triangle::intersectP(const Ray& r, double tMax) const {
    double t, b1, b2;
    return mt(r, tMax, &t, &b1, &b2);
}

AABB Triangle::bounds() const {
    Vec3 a, b, c;
    vertices(&a, &b, &c);
    AABB box;
    box.expand(a);
    box.expand(b);
    box.expand(c);
    return box;
}

double Triangle::area() const {
    Vec3 a, b, c;
    vertices(&a, &b, &c);
    return 0.5 * length(cross(b - a, c - a));
}

Vec3 Triangle::centroid() const {
    Vec3 a, b, c;
    vertices(&a, &b, &c);
    return (a + b + c) / 3.0;
}

SurfaceSample Triangle::sample(Vec2 u) const {
    Vec2 b = sampleUniformTriangle(u);
    Vec3 p0, p1, p2;
    vertices(&p0, &p1, &p2);
    double b0 = b.x, b1 = b.y, b2 = 1 - b.x - b.y;
    SurfaceSample s;
    s.p = p0 * b0 + p1 * b1 + p2 * b2;
    s.n = orientedNormal(b1, b2);
    return s;
}

// ============================================================ Plane
Plane::Plane(const Vec3& point, const Vec3& normal, bool reverseOrientation) : p0_(point) {
    n_ = normalize(normal);
    if (reverseOrientation) n_ = -n_;
    coordinateSystem(normalize(normal), &s_, &t_);
}

bool Plane::intersect(const Ray& r, double tMax, Hit* hit) const {
    double denom = dot(r.d, n_);
    if (denom == 0) return false;
    double t = dot(p0_ - r.o, n_) / denom;
    if (t <= kRayTMin || t >= tMax) return false;
    hit->t = t;
    Vec3 p = r.at(t);
    p -= n_ * dot(p - p0_, n_);  // snap onto the plane
    hit->p = p;
    hit->ng = hit->ns = n_;
    Vec3 d = p - p0_;
    hit->uv = Vec2(dot(d, s_), dot(d, t_));
    hit->shape = this;
    return true;
}

bool Plane::intersectP(const Ray& r, double tMax) const {
    double denom = dot(r.d, n_);
    if (denom == 0) return false;
    double t = dot(p0_ - r.o, n_) / denom;
    return t > kRayTMin && t < tMax;
}

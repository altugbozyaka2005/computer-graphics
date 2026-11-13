#include "scene.h"

#include "../core/log.h"

namespace {
// Ray / axis-aligned box slab test: true if the ray overlaps the box within (0, tMax).
bool hitBox(const AABB& b, const Ray& r, double tMax) {
    double t0 = 0, t1 = tMax;
    for (int a = 0; a < 3; ++a) {
        double inv = r.d[a] == 0 ? std::copysign(1e300, r.d[a]) : 1.0 / r.d[a];
        double tNear = (b.lo[a] - r.o[a]) * inv, tFar = (b.hi[a] - r.o[a]) * inv;
        if (tNear > tFar) std::swap(tNear, tFar);
        tFar *= 1 + 1e-12;  // conservative for round-off
        t0 = tNear > t0 ? tNear : t0;
        t1 = tFar < t1 ? tFar : t1;
        if (t0 > t1) return false;
    }
    return true;
}
}  // namespace

const char* accelName(AccelType t) {
    switch (t) {
        case AccelType::BVH: return "bvh";
        case AccelType::Objects: return "objects";
        case AccelType::None: return "none";
    }
    return "?";
}

void Scene::prepare() {
    for (auto& o : objects) {
        o.box = AABB();
        for (size_t i = o.first; i < o.last; ++i) o.box.expand(shapes[i]->bounds());
    }
    if (accel.type == AccelType::BVH) bvh.build(shapes, accel.split, accel.maxNodePrims);
}

bool Scene::intersect(const Ray& r, Hit* hit) const {
    double tMax = Infinity;
    bool found = false;
    RayStats& st = tlsStats;
    if (accel.type == AccelType::BVH) {
        if (bvh.intersect(r, tMax, hit)) {
            found = true;
            tMax = hit->t;
        }
    } else if (accel.type == AccelType::None) {
        for (const auto& s : shapes) {
            ++st.primTests;
            if (s->intersectA(r, tMax, hit)) {
                found = true;
                tMax = hit->t;
            }
        }
    } else for (const auto& o : objects) {
        ++st.boxTests;
        if (!hitBox(o.box, r, tMax)) continue;
        for (size_t i = o.first; i < o.last; ++i) {
            ++st.primTests;
            if (shapes[i]->intersectA(r, tMax, hit)) {
                found = true;
                tMax = hit->t;
            }
        }
    }
    for (const auto& s : unbounded) {
        ++st.primTests;
        if (s->intersectA(r, tMax, hit)) {
            found = true;
            tMax = hit->t;
        }
    }
    return found;
}

bool Scene::occluded(const Ray& r, double tMax) const {
    RayStats& st = tlsStats;
    ++st.shadowRays;
    for (const auto& s : unbounded) {
        ++st.primTests;
        if (s->intersectPA(r, tMax)) return true;
    }
    if (accel.type == AccelType::BVH) return bvh.occluded(r, tMax);
    if (accel.type == AccelType::None) {
        for (const auto& s : shapes) {
            ++st.primTests;
            if (s->intersectPA(r, tMax)) return true;
        }
        return false;
    }
    for (const auto& o : objects) {
        ++st.boxTests;
        if (!hitBox(o.box, r, tMax)) continue;
        for (size_t i = o.first; i < o.last; ++i) {
            ++st.primTests;
            if (shapes[i]->intersectPA(r, tMax)) return true;
        }
    }
    return false;
}

#include "bvh.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "../core/log.h"

namespace {

constexpr int kBuckets = 12;     // SAH buckets along the split axis (pbrt-v4 uses 12)
constexpr int kMaxDepth = 100;   // recursion guard; a deeper node becomes a leaf
constexpr int kStackSize = 128;  // > kMaxDepth: the traversal stack can never overflow
// SAH costs relative to one ray-primitive test (pbrt-v4: traversal 1/2, intersection 1).
constexpr double kTraversalCost = 0.5;

// Slab test against (0, tMax) with a precomputed reciprocal direction. Division by a zero
// component gives a huge reciprocal of the right sign, as in Scene's per-object test.
inline bool hitBox(const AABB& b, const Vec3& o, const Vec3& inv, double tMax) {
    // tMax is padded too: a box whose entry distance rounds to just above the current
    // closest hit may still hold a primitive at exactly that distance (see intersect).
    double t0 = 0, t1 = tMax * (1 + 1e-12);
    for (int a = 0; a < 3; ++a) {
        double tNear = (b.lo[a] - o[a]) * inv[a], tFar = (b.hi[a] - o[a]) * inv[a];
        if (tNear > tFar) std::swap(tNear, tFar);
        tFar *= 1 + 1e-12;  // conservative for round-off
        t0 = tNear > t0 ? tNear : t0;
        t1 = tFar < t1 ? tFar : t1;
        if (t0 > t1) return false;
    }
    return true;
}

inline Vec3 reciprocal(const Vec3& d) {
    Vec3 inv;
    for (int a = 0; a < 3; ++a) inv[a] = d[a] == 0 ? std::copysign(1e300, d[a]) : 1.0 / d[a];
    return inv;
}

}  // namespace

bool parseSplitMethod(const std::string& s, SplitMethod* m) {
    if (s == "sah") *m = SplitMethod::SAH;
    else if (s == "middle") *m = SplitMethod::Middle;
    else if (s == "equal") *m = SplitMethod::EqualCounts;
    else return false;
    return true;
}

const char* splitMethodName(SplitMethod m) {
    switch (m) {
        case SplitMethod::SAH: return "sah";
        case SplitMethod::Middle: return "middle";
        case SplitMethod::EqualCounts: return "equal";
    }
    return "?";
}

struct BVH::BuildNode {
    AABB box;
    const BuildNode* child[2] = {nullptr, nullptr};
    int axis = 0, firstPrim = 0, nPrims = 0;
};

void BVH::build(const std::vector<std::unique_ptr<Shape>>& prims, SplitMethod method, int maxPrimsInNode) {
    Timer t;
    method_ = method;
    maxPrims_ = std::max(1, std::min(maxPrimsInNode, 255));
    nodes_.clear();
    prims_.clear();
    primIndex_.clear();
    stats_ = BVHBuildStats();
    if (prims.empty()) return;

    std::vector<BuildPrim> bp(prims.size());
    for (size_t i = 0; i < prims.size(); ++i) {
        bp[i].box = prims[i]->bounds();
        bp[i].c = bp[i].box.centroid();
        bp[i].index = (int)i;
    }
    std::vector<const Shape*> ordered;
    ordered.reserve(prims.size());
    std::vector<std::unique_ptr<BuildNode>> pool;
    // Build nodes refer to bp by index; the leaves copy their shape pointers into `ordered`.
    std::vector<const Shape*> all(prims.size());
    for (size_t i = 0; i < prims.size(); ++i) all[i] = prims[i].get();
    allPrims_ = &all;
    const BuildNode* root = buildRec(bp, 0, (int)bp.size(), 0, ordered, pool);
    allPrims_ = nullptr;
    prims_ = std::move(ordered);

    nodes_.resize(stats_.nodes);
    int offset = 0;
    flatten(root, &offset);

    // Expected SAH cost of the finished tree, relative to the root's surface area.
    double rootArea = nodes_[0].box.surfaceArea();
    if (rootArea > 0) {
        for (const Node& n : nodes_) {
            double p = n.box.surfaceArea() / rootArea;
            stats_.sahCost += n.nPrims ? p * n.nPrims : p * kTraversalCost;
        }
    }
    stats_.buildSeconds = t.seconds();
}

BVH::BuildNode* BVH::buildRec(std::vector<BuildPrim>& bp, int start, int end, int depth,
                              std::vector<const Shape*>& ordered, std::vector<std::unique_ptr<BuildNode>>& pool) {
    pool.push_back(std::make_unique<BuildNode>());
    BuildNode* node = pool.back().get();
    ++stats_.nodes;
    stats_.maxDepth = std::max(stats_.maxDepth, depth);
    for (int i = start; i < end; ++i) node->box.expand(bp[i].box);
    const int n = end - start;

    auto makeLeaf = [&]() {
        node->firstPrim = (int)ordered.size();
        node->nPrims = n;
        for (int i = start; i < end; ++i) {
            ordered.push_back((*allPrims_)[bp[i].index]);
            primIndex_.push_back(bp[i].index);
        }
        ++stats_.leaves;
        stats_.maxLeafPrims = std::max(stats_.maxLeafPrims, n);
        return node;
    };
    if (n == 1 || depth >= kMaxDepth) return makeLeaf();

    AABB cb;
    for (int i = start; i < end; ++i) cb.expand(bp[i].c);
    const int dim = cb.maxExtent();
    // All centroids coincide: no split can separate the primitives (pbrt-v4 makes a leaf too).
    if (cb.hi[dim] == cb.lo[dim]) return makeLeaf();

    int mid = (start + end) / 2;
    auto equalCounts = [&]() {
        mid = (start + end) / 2;
        std::nth_element(bp.begin() + start, bp.begin() + mid, bp.begin() + end,
                         [dim](const BuildPrim& a, const BuildPrim& b) { return a.c[dim] < b.c[dim]; });
    };
    if (method_ == SplitMethod::Middle) {
        // Split the centroid bounds in half along the longest axis.
        double pmid = 0.5 * (cb.lo[dim] + cb.hi[dim]);
        BuildPrim* m = std::partition(bp.data() + start, bp.data() + end,
                                      [dim, pmid](const BuildPrim& p) { return p.c[dim] < pmid; });
        mid = (int)(m - bp.data());
        if (mid == start || mid == end) equalCounts();
    } else if (method_ == SplitMethod::EqualCounts || n <= 2) {
        equalCounts();
    } else {
        // Surface area heuristic over kBuckets equal-width buckets of the centroid range:
        // cost(split) = C_trav + (A_below N_below + A_above N_above) / A_node.
        struct Bucket {
            int count = 0;
            AABB box;
        } buckets[kBuckets];
        auto bucketOf = [&](const BuildPrim& p) {
            int b = (int)(kBuckets * cb.offset(p.c)[dim]);
            return std::min(std::max(b, 0), kBuckets - 1);
        };
        for (int i = start; i < end; ++i) {
            Bucket& b = buckets[bucketOf(bp[i])];
            ++b.count;
            b.box.expand(bp[i].box);
        }
        // Sweep from both ends to get the cost of splitting after each bucket in O(kBuckets).
        double cost[kBuckets - 1] = {};
        int countBelow = 0;
        AABB boxBelow;
        for (int i = 0; i < kBuckets - 1; ++i) {
            boxBelow.expand(buckets[i].box);
            countBelow += buckets[i].count;
            cost[i] += countBelow * boxBelow.surfaceArea();
        }
        int countAbove = 0;
        AABB boxAbove;
        for (int i = kBuckets - 1; i >= 1; --i) {
            boxAbove.expand(buckets[i].box);
            countAbove += buckets[i].count;
            cost[i - 1] += countAbove * boxAbove.surfaceArea();
        }
        int best = 0;
        for (int i = 1; i < kBuckets - 1; ++i)
            if (cost[i] < cost[best]) best = i;
        double area = node->box.surfaceArea();
        double splitCost = kTraversalCost + (area > 0 ? cost[best] / area : 0);
        double leafCost = n;
        if (n <= maxPrims_ && leafCost <= splitCost) return makeLeaf();
        BuildPrim* m = std::partition(bp.data() + start, bp.data() + end,
                                      [&](const BuildPrim& p) { return bucketOf(p) <= best; });
        mid = (int)(m - bp.data());
        if (mid == start || mid == end) equalCounts();
    }

    node->axis = dim;
    node->child[0] = buildRec(bp, start, mid, depth + 1, ordered, pool);
    node->child[1] = buildRec(bp, mid, end, depth + 1, ordered, pool);
    return node;
}

int BVH::flatten(const BuildNode* n, int* offset) {
    int idx = (*offset)++;
    Node& ln = nodes_[idx];
    ln.box = n->box;
    if (n->nPrims > 0) {
        ln.offset = n->firstPrim;
        ln.nPrims = n->nPrims;
    } else {
        ln.axis = n->axis;
        flatten(n->child[0], offset);  // first child directly follows its parent
        nodes_[idx].offset = flatten(n->child[1], offset);
    }
    return idx;
}

bool BVH::intersect(const Ray& r, double tMax, Hit* hit) const {
    if (nodes_.empty()) return false;
    RayStats& st = tlsStats;
    const Vec3 inv = reciprocal(r.d);
    const bool dirIsNeg[3] = {inv.x < 0, inv.y < 0, inv.z < 0};
    int stack[kStackSize];
    int sp = 0, cur = 0;
    bool found = false;
    int bestIndex = INT32_MAX;
    while (true) {
        const Node& n = nodes_[cur];
        ++st.boxTests;
        if (hitBox(n.box, r.o, inv, tMax)) {
            if (n.nPrims > 0) {
                for (int i = 0; i < n.nPrims; ++i) {
                    ++st.primTests;
                    // Closest hit; an exact tie goes to the primitive declared first, as in a
                    // linear scan, so the result does not depend on the traversal order.
                    Hit h;
                    if (prims_[n.offset + i]->intersectA(r, std::nextafter(tMax, Infinity), &h) &&
                        (h.t < tMax || primIndex_[n.offset + i] < bestIndex)) {
                        *hit = h;
                        tMax = h.t;
                        bestIndex = primIndex_[n.offset + i];
                        found = true;
                    }
                }
                if (sp == 0) break;
                cur = stack[--sp];
            } else if (dirIsNeg[n.axis]) {
                // Visit the child nearer to the ray origin first so tMax shrinks early.
                stack[sp++] = cur + 1;
                cur = n.offset;
            } else {
                stack[sp++] = n.offset;
                cur = cur + 1;
            }
        } else {
            if (sp == 0) break;
            cur = stack[--sp];
        }
    }
    return found;
}

bool BVH::occluded(const Ray& r, double tMax) const {
    if (nodes_.empty()) return false;
    RayStats& st = tlsStats;
    const Vec3 inv = reciprocal(r.d);
    const bool dirIsNeg[3] = {inv.x < 0, inv.y < 0, inv.z < 0};
    int stack[kStackSize];
    int sp = 0, cur = 0;
    while (true) {
        const Node& n = nodes_[cur];
        ++st.boxTests;
        if (hitBox(n.box, r.o, inv, tMax)) {
            if (n.nPrims > 0) {
                for (int i = 0; i < n.nPrims; ++i) {
                    ++st.primTests;
                    if (prims_[n.offset + i]->intersectPA(r, tMax)) return true;  // any hit ends the search
                }
                if (sp == 0) break;
                cur = stack[--sp];
            } else if (dirIsNeg[n.axis]) {
                stack[sp++] = cur + 1;
                cur = n.offset;
            } else {
                stack[sp++] = n.offset;
                cur = cur + 1;
            }
        } else {
            if (sp == 0) break;
            cur = stack[--sp];
        }
    }
    return false;
}

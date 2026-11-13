// Bounding volume hierarchy over the scene's bounded primitives (pbrt-v4 Section 7.3).
// Built top-down with the surface area heuristic (or middle / equal-counts splits), then
// flattened into an array of nodes in depth-first order for a compact, stack-based traversal.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "shape.h"

enum class SplitMethod { SAH, Middle, EqualCounts };
bool parseSplitMethod(const std::string& s, SplitMethod* m);
const char* splitMethodName(SplitMethod m);

struct BVHBuildStats {
    int nodes = 0, leaves = 0, maxDepth = 0, maxLeafPrims = 0;
    double buildSeconds = 0;
    double sahCost = 0;  // expected cost of the tree (traversal 1/8, intersection 1, pbrt-v4 weights)
};

class BVH {
public:
    // Builds over prims (which must outlive the BVH). maxPrimsInNode is pbrt's "maxnodeprims".
    void build(const std::vector<std::unique_ptr<Shape>>& prims, SplitMethod method, int maxPrimsInNode);
    bool empty() const { return nodes_.empty(); }
    // Closest hit (t < tMax) / any hit; ray-box and ray-primitive tests are counted in tlsStats.
    bool intersect(const Ray& r, double tMax, Hit* hit) const;
    bool occluded(const Ray& r, double tMax) const;
    const BVHBuildStats& stats() const { return stats_; }
    AABB bounds() const { return nodes_.empty() ? AABB() : nodes_[0].box; }

private:
    struct Node {
        AABB box;
        int offset = 0;     // leaf: first index into prims_; interior: index of the second child
        int nPrims = 0;    // 0 for interior nodes
        int axis = 0;      // interior: split axis (decides the traversal order)
    };
    struct BuildPrim {
        AABB box;
        Vec3 c;
        int index;
    };
    struct BuildNode;
    BuildNode* buildRec(std::vector<BuildPrim>& bp, int start, int end, int depth, std::vector<const Shape*>& ordered,
                        std::vector<std::unique_ptr<BuildNode>>& pool);
    int flatten(const BuildNode* n, int* offset);

    std::vector<Node> nodes_;
    std::vector<const Shape*> prims_;  // in leaf order
    std::vector<int> primIndex_;       // input index of each prims_ entry (tie-breaking)
    const std::vector<const Shape*>* allPrims_ = nullptr;  // input order, during build only
    SplitMethod method_ = SplitMethod::SAH;
    int maxPrims_ = 4;
    BVHBuildStats stats_;
};

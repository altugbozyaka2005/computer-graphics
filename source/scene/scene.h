// The fully built scene: geometry, materials, lights, and the render settings
// collected from the scene file.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "../core/image.h"
#include "../geometry/shape.h"
#include "../render/camera.h"
#include "../render/light.h"
#include "../render/material.h"
#include "../render/sampler.h"

struct FilmSettings {
    int xRes = 1280, yRes = 720;
    double crop[4] = {0, 1, 0, 1};  // xmin xmax ymin ymax (normalised)
    std::string filename = "pbrt.exr";
    bool filenameSpecified = false;
    ToneMapSettings tonemap;
    bool tonemapSpecified = false;
};

struct IntegratorSettings {
    std::string type = "distributed";  // "whitted" | "distributed"
    int maxDepth = 5;
    // Whitted
    Color ambient{1, 1, 1};  // ambient light intensity I_a (multiplied by material Ka * Kd)
    bool transparentShadows = false;  // filtered shadow rays through dielectrics
    double minWeight = 0;             // DRT: adaptive path termination threshold (0 = off)
    bool caustics = true;             // DRT: count lights reached via mirror/glass after a diffuse bounce
    // Distributed
    int lightSamples = 16;  // shadow rays per area light (sampling density)
};

class Scene {
public:
    // Settings
    CameraSettings camera;
    FilmSettings film;
    SamplerSettings sampler;
    bool samplerSpecified = false;
    IntegratorSettings integrator;

    // Content
    std::vector<std::unique_ptr<Shape>> shapes;     // bounded shapes
    std::vector<std::unique_ptr<Shape>> unbounded;  // infinite planes
    std::vector<std::shared_ptr<TriangleMesh>> meshes;
    std::vector<Material> materials;  // index 0 = default material
    std::vector<DeltaLight> deltaLights;
    std::vector<std::unique_ptr<AreaLight>> areaLights;
    Color envL{0, 0, 0};
    bool hasEnv = false;

    // One entry per Shape directive: a range [first, last) of `shapes`.
    struct Object {
        size_t first = 0, last = 0;
        AABB box;
    };
    std::vector<Object> objects;
    void addObject(size_t first, size_t last) { objects.push_back({first, last, AABB()}); }
    // Computes each object's bounding box (call once after parsing).
    void prepare();

    // Closest hit / any hit. Each object's primitives are only tested when the
    // ray hits the object's bounding box (simple per-object bounding volumes).
    bool intersect(const Ray& r, Hit* hit) const;
    bool occluded(const Ray& r, double tMax) const;
    size_t primitiveCount() const { return shapes.size() + unbounded.size(); }
};

// Creation of scene objects (shapes, materials, textures, lights, render
// settings) from parsed pbrt directives. Internal to the parser.
#pragma once

#include <map>
#include <memory>
#include <string>
#include <vector>

#include "../core/transform.h"
#include "params.h"
#include "scene.h"

struct AreaLightState {
    bool active = false;
    std::string type;
    ParamSet params;
    FileLoc loc;
};

class SceneBuilder {
public:
    explicit SceneBuilder(Scene* scene, std::string baseDir) : scene_(scene), baseDir_(std::move(baseDir)) {}

    // Render options (before WorldBegin)
    void camera(const std::string& type, const ParamSet& ps, const Transform& ctm, const FileLoc& loc);
    void film(const std::string& type, const ParamSet& ps, const FileLoc& loc);
    void sampler(const std::string& type, const ParamSet& ps, const FileLoc& loc);
    void pixelFilter(const std::string& type, const ParamSet& ps, const FileLoc& loc);
    void integrator(const std::string& type, const ParamSet& ps, const FileLoc& loc);
    void accelerator(const std::string& type, const ParamSet& ps, const FileLoc& loc);

    // World
    // Returns the index of the new material in scene->materials.
    int material(const std::string& type, const ParamSet& ps, const std::string& name, const FileLoc& loc);
    void texture(const std::string& name, const std::string& valueType, const std::string& cls, const ParamSet& ps,
                 const FileLoc& loc);
    void light(const std::string& type, const ParamSet& ps, const Transform& ctm, const FileLoc& loc);
    void shape(const std::string& type, const ParamSet& ps, const Transform& ctm, bool reverseOrientation,
               int materialId, const AreaLightState& area, const FileLoc& loc);

    bool hasCamera() const { return cameraSet_; }

private:
    TexturePtr spectrumTexture(const ParamSet& ps, const std::string& name, const Color& def, SpectrumKind kind,
                               bool* specified = nullptr);
    std::shared_ptr<const Image> loadImage(const std::string& filename, const std::string& encoding,
                                           const FileLoc& loc);
    std::vector<Shape*> addMesh(const struct MeshData& md, const Transform& ctm, bool ro, int materialId,
                                const FileLoc& loc, const std::string& label);
    std::string resolvePath(const std::string& p) const;

    Scene* scene_;
    std::string baseDir_;
    bool cameraSet_ = false;
    std::map<std::string, TexturePtr> spectrumTextures_, floatTextures_;
    std::map<std::string, std::shared_ptr<const Image>> imageCache_;
};

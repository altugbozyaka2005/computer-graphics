// pbrt parameter lists: "type name" [ values ].
#pragma once

#include <string>
#include <vector>

#include "../core/log.h"
#include "../core/math.h"

struct Param {
    std::string type, name;
    FileLoc loc;
    std::vector<double> nums;
    std::vector<std::string> strs;
    std::vector<bool> bools;
    mutable bool used = false;
};

enum class SpectrumKind { Reflectance, Illuminant, Unbounded };

class ParamSet {
public:
    std::vector<Param> params;
    std::string baseDir;  // directory of the scene file, for relative paths

    const Param* find(const std::string& name) const;
    bool has(const std::string& name) const { return find(name) != nullptr; }

    double getFloat(const std::string& name, double def) const;
    int getInt(const std::string& name, int def) const;
    bool getBool(const std::string& name, bool def) const;
    std::string getString(const std::string& name, const std::string& def) const;
    Vec3 getPoint3(const std::string& name, const Vec3& def) const;
    // rgb / spectrum / blackbody -> linear RGB. Returns false if absent or invalid.
    bool getRGB(const std::string& name, SpectrumKind kind, Color* out) const;
    // Name of a texture if the parameter is of type "texture", else "".
    std::string getTexture(const std::string& name) const;

    std::vector<double> getFloats(const std::string& name) const;
    std::vector<int> getInts(const std::string& name) const;
    std::vector<Vec3> getPoint3s(const std::string& name) const;  // point3/vector3/normal3
    std::vector<Vec2> getPoint2s(const std::string& name) const;  // point2 / float pairs

    // Warn about parameters that were never looked up (typos, unsupported options).
    void reportUnused(const std::string& context) const;

private:
    const Param* lookup(const std::string& name, std::initializer_list<const char*> types,
                        const char* expected) const;
};

// Canonical pbrt type name (accepts pbrt-v3 aliases such as "point", "color").
std::string canonicalParamType(const std::string& t);

// Spectral helpers (CIE 1931 analytic fit, Wyman et al. 2013).
Color blackbodyRGB(double kelvin);  // normalised to luminance 1
Color spectrumSamplesToRGB(const std::vector<double>& lambdaValuePairs, SpectrumKind kind);
bool namedSpectrumRGB(const std::string& name, SpectrumKind kind, Color* out);
// Approximate normal-incidence reflectance of pbrt's named metals ("metal-Cu-eta" etc).
bool namedMetalReflectance(const std::string& name, Color* out);
// IOR for pbrt's named glasses ("glass-BK7"...). Returns false if unknown.
bool namedGlassIOR(const std::string& name, double* eta);

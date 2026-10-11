#include "params.h"

#include <fstream>
#include <sstream>

std::string canonicalParamType(const std::string& t) {
    if (t == "point") return "point3";
    if (t == "normal") return "normal3";
    if (t == "vector") return "vector3";
    if (t == "color") return "rgb";
    return t;
}

const Param* ParamSet::find(const std::string& name) const {
    for (auto it = params.rbegin(); it != params.rend(); ++it)
        if (it->name == name) return &*it;
    return nullptr;
}

const Param* ParamSet::lookup(const std::string& name, std::initializer_list<const char*> types,
                              const char* expected) const {
    const Param* p = find(name);
    if (!p) return nullptr;
    p->used = true;
    for (const char* t : types)
        if (p->type == t) return p;
    LOG().error("parameter '" + name + "' has type '" + p->type + "' but '" + expected +
                    "' was expected; using the default value",
                p->loc);
    return nullptr;
}

double ParamSet::getFloat(const std::string& name, double def) const {
    const Param* p = lookup(name, {"float"}, "float");
    if (!p || p->nums.empty()) return def;
    if (p->nums.size() > 1) LOG().warning("parameter 'float " + name + "' has more than one value; using the first", p->loc);
    return p->nums[0];
}

int ParamSet::getInt(const std::string& name, int def) const {
    const Param* p = lookup(name, {"integer"}, "integer");
    if (!p || p->nums.empty()) return def;
    return (int)p->nums[0];
}

bool ParamSet::getBool(const std::string& name, bool def) const {
    const Param* p = lookup(name, {"bool"}, "bool");
    if (!p || p->bools.empty()) return def;
    return p->bools[0];
}

std::string ParamSet::getString(const std::string& name, const std::string& def) const {
    const Param* p = lookup(name, {"string"}, "string");
    if (!p || p->strs.empty()) return def;
    return p->strs[0];
}

Vec3 ParamSet::getPoint3(const std::string& name, const Vec3& def) const {
    const Param* p = lookup(name, {"point3", "vector3", "normal3"}, "point3");
    if (!p || p->nums.size() < 3) return def;
    return Vec3(p->nums[0], p->nums[1], p->nums[2]);
}

std::string ParamSet::getTexture(const std::string& name) const {
    const Param* p = find(name);
    if (!p || p->type != "texture" || p->strs.empty()) return "";
    p->used = true;
    return p->strs[0];
}

std::vector<double> ParamSet::getFloats(const std::string& name) const {
    const Param* p = lookup(name, {"float"}, "float");
    return p ? p->nums : std::vector<double>();
}

std::vector<int> ParamSet::getInts(const std::string& name) const {
    const Param* p = lookup(name, {"integer"}, "integer");
    std::vector<int> r;
    if (p)
        for (double v : p->nums) r.push_back((int)v);
    return r;
}

std::vector<Vec3> ParamSet::getPoint3s(const std::string& name) const {
    const Param* p = lookup(name, {"point3", "vector3", "normal3"}, "point3");
    std::vector<Vec3> r;
    if (p)
        for (size_t i = 0; i + 2 < p->nums.size(); i += 3) r.push_back(Vec3(p->nums[i], p->nums[i + 1], p->nums[i + 2]));
    return r;
}

std::vector<Vec2> ParamSet::getPoint2s(const std::string& name) const {
    const Param* p = lookup(name, {"point2", "vector2", "float"}, "point2");
    std::vector<Vec2> r;
    if (p) {
        if (p->nums.size() % 2 != 0)
            LOG().error("parameter '" + name + "' needs an even number of values", p->loc);
        for (size_t i = 0; i + 1 < p->nums.size(); i += 2) r.push_back(Vec2(p->nums[i], p->nums[i + 1]));
    }
    return r;
}

void ParamSet::reportUnused(const std::string& context) const {
    for (const auto& p : params)
        if (!p.used)
            LOG().warning("unused or unsupported parameter \"" + p.type + " " + p.name + "\" in " + context, p.loc);
}

// ------------------------------------------------------------- spectra
namespace {
double g(double x, double mu, double s1, double s2) {
    double t = (x - mu) / (x < mu ? s1 : s2);
    return std::exp(-0.5 * t * t);
}
Vec3 cieXYZ(double l) {  // Wyman, Sloan, Shirley 2013 multi-lobe fit
    double x = 1.056 * g(l, 599.8, 37.9, 31.0) + 0.362 * g(l, 442.0, 16.0, 26.7) - 0.065 * g(l, 501.1, 20.4, 26.2);
    double y = 0.821 * g(l, 568.8, 46.9, 40.5) + 0.286 * g(l, 530.9, 16.3, 31.1);
    double z = 1.217 * g(l, 437.0, 11.8, 36.0) + 0.681 * g(l, 459.0, 26.0, 13.8);
    return {x, y, z};
}
Color xyzToLinearSRGB(const Vec3& c) {
    return {3.2404542 * c.x - 1.5371385 * c.y - 0.4985314 * c.z,
            -0.9692660 * c.x + 1.8760108 * c.y + 0.0415560 * c.z,
            0.0556434 * c.x - 0.2040259 * c.y + 1.0572252 * c.z};
}
double planck(double lambdaNm, double T) {
    const double c = 299792458.0, h = 6.62606957e-34, kb = 1.3806488e-23;
    double l = lambdaNm * 1e-9;
    return (2 * h * c * c) / (std::pow(l, 5) * (std::exp((h * c) / (l * kb * T)) - 1));
}
template <typename F>
Color integrateToRGB(F spectrum, SpectrumKind kind) {
    Vec3 xyz(0);
    double norm = 0;
    for (int l = 360; l <= 830; ++l) {
        double s = spectrum((double)l);
        Vec3 cmf = cieXYZ(l);
        if (kind == SpectrumKind::Illuminant) {
            xyz += cmf * s;
        } else {
            // Reflectances are viewed under an (approximately) D65 illuminant.
            double e = planck(l, 6504.0);
            xyz += cmf * (s * e);
            norm += cmf.y * e;
        }
    }
    if (kind == SpectrumKind::Illuminant) {
        // pbrt-v4 normalises light spectra photometrically; keep luminance 1.
        if (xyz.y > 0) xyz /= xyz.y;
    } else if (norm > 0) {
        xyz /= norm;
    }
    return vmax(xyzToLinearSRGB(xyz), Color(0));
}
}  // namespace

Color blackbodyRGB(double T) {
    Color c = integrateToRGB([T](double l) { return planck(l, T); }, SpectrumKind::Illuminant);
    double lum = luminance(c);
    return lum > 0 ? c / lum : Color(1);
}

Color spectrumSamplesToRGB(const std::vector<double>& pv, SpectrumKind kind) {
    std::vector<std::pair<double, double>> s;
    for (size_t i = 0; i + 1 < pv.size(); i += 2) s.push_back({pv[i], pv[i + 1]});
    std::sort(s.begin(), s.end());
    auto eval = [&](double l) {
        if (s.empty()) return 0.0;
        if (l <= s.front().first) return s.front().second;
        if (l >= s.back().first) return s.back().second;
        for (size_t i = 1; i < s.size(); ++i)
            if (l <= s[i].first) {
                double t = (l - s[i - 1].first) / (s[i].first - s[i - 1].first);
                return lerp(t, s[i - 1].second, s[i].second);
            }
        return s.back().second;
    };
    Color c = integrateToRGB(eval, kind);
    if (kind == SpectrumKind::Illuminant) {
        double lum = luminance(c);
        if (lum > 0) c /= lum;
    }
    return c;
}

bool namedSpectrumRGB(const std::string& name, SpectrumKind kind, Color* out) {
    (void)kind;
    if (name == "stdillum-D65") { *out = Color(1); return true; }
    if (name == "stdillum-D50") { *out = blackbodyRGB(5003); return true; }
    if (name == "stdillum-A") { *out = blackbodyRGB(2856); return true; }
    if (name == "illum-acesD60") { *out = blackbodyRGB(6000); return true; }
    if (name.rfind("stdillum-F", 0) == 0) { *out = Color(1); return true; }
    return false;
}

bool namedMetalReflectance(const std::string& name, Color* out) {
    // Normal-incidence reflectance (linear sRGB), commonly tabulated values.
    struct M { const char* key; Color c; };
    static const M metals[] = {{"metal-Cu", {0.955, 0.638, 0.538}}, {"metal-Au", {1.000, 0.766, 0.336}},
                               {"metal-Ag", {0.972, 0.960, 0.915}}, {"metal-Al", {0.913, 0.922, 0.924}},
                               {"metal-CuZn", {0.887, 0.789, 0.434}}, {"metal-MgO", {0.95, 0.95, 0.95}},
                               {"metal-TiO2", {0.95, 0.95, 0.95}}};
    // Longest prefix first so that "metal-CuZn" is not matched as "metal-Cu".
    const M* best = nullptr;
    size_t bestLen = 0;
    for (const auto& m : metals) {
        size_t len = std::string(m.key).size();
        if (name.compare(0, len, m.key) == 0 && (name.size() == len || name[len] == '-') && len > bestLen) {
            best = &m;
            bestLen = len;
        }
    }
    if (!best) return false;
    *out = best->c;
    return true;
}

bool namedGlassIOR(const std::string& name, double* eta) {
    struct G { const char* key; double eta; };
    static const G glasses[] = {{"glass-BK7", 1.5168}, {"glass-BAF10", 1.6700}, {"glass-FK51A", 1.4866},
                                {"glass-LASF9", 1.8503}, {"glass-F5", 1.6034}, {"glass-F10", 1.6200},
                                {"glass-F11", 1.6200}, {"fused-silica", 1.4585}};
    for (const auto& gl : glasses)
        if (name == gl.key) { *eta = gl.eta; return true; }
    return false;
}

bool ParamSet::getRGB(const std::string& name, SpectrumKind kind, Color* out) const {
    const Param* p = find(name);
    if (!p) return false;
    p->used = true;
    if (p->type == "rgb") {
        if (p->nums.size() != 3) return false;
        Color c(p->nums[0], p->nums[1], p->nums[2]);
        if (c.minComponent() < 0) {
            LOG().error("rgb parameter '" + name + "' has negative components; clamped to 0", p->loc);
            c = vmax(c, Color(0));
        }
        if (kind == SpectrumKind::Reflectance && c.maxComponent() > 1)
            LOG().warning("reflectance '" + name + "' exceeds 1 (not energy conserving)", p->loc);
        *out = c;
        return true;
    }
    if (p->type == "blackbody") {
        if (p->nums.empty() || p->nums[0] <= 0) {
            LOG().error("blackbody temperature for '" + name + "' must be positive", p->loc);
            return false;
        }
        *out = blackbodyRGB(p->nums[0]);
        return true;
    }
    if (p->type == "spectrum") {
        if (!p->strs.empty()) {
            const std::string& s = p->strs[0];
            if (namedSpectrumRGB(s, kind, out)) return true;
            // Otherwise a file of (lambda, value) pairs.
            std::string path = (!s.empty() && s[0] == '/') ? s : baseDir + s;
            std::ifstream f(path);
            if (!f) {
                LOG().error("unknown named spectrum or missing spectrum file '" + s + "' for '" + name + "'", p->loc);
                return false;
            }
            std::vector<double> vals;
            std::string line;
            while (std::getline(f, line)) {
                size_t hash = line.find('#');
                if (hash != std::string::npos) line = line.substr(0, hash);
                std::istringstream ls(line);
                double v;
                while (ls >> v) vals.push_back(v);
            }
            if (vals.size() < 2 || vals.size() % 2) {
                LOG().error("spectrum file '" + s + "' must contain (lambda, value) pairs", p->loc);
                return false;
            }
            *out = spectrumSamplesToRGB(vals, kind);
            LOG().warning("spectral data for '" + name + "' approximated as RGB " + std::to_string(out->x) + " " +
                              std::to_string(out->y) + " " + std::to_string(out->z),
                          p->loc);
            return true;
        }
        if (p->nums.size() >= 2 && p->nums.size() % 2 == 0) {
            *out = spectrumSamplesToRGB(p->nums, kind);
            LOG().warning("spectral samples for '" + name + "' approximated as RGB", p->loc);
            return true;
        }
        LOG().error("malformed spectrum value for '" + name + "'", p->loc);
        return false;
    }
    if (p->type == "float" && p->nums.size() == 1) {
        *out = Color(p->nums[0]);
        return true;
    }
    LOG().error("parameter '" + name + "' has type '" + p->type + "' but a colour (rgb/spectrum/blackbody) was expected",
                p->loc);
    return false;
}

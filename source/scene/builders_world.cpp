// World directives: Material, Texture, LightSource, Shape (+ AreaLightSource).
#include <sstream>

#include "builders.h"
#include "meshio.h"

// Material parameters pbrt accepts that this renderer deliberately ignores.
static void ignoreParamsUsed(const ParamSet& ps) {
    for (const char* n : {"displacement", "normalmap"})
        if (const Param* p = ps.find(n)) {
            p->used = true;
            LOG().warning(std::string("material parameter '") + n + "' is not supported and was ignored", p->loc);
        }
}

std::string SceneBuilder::resolvePath(const std::string& p) const {
    if (p.empty() || p[0] == '/') return p;
    return baseDir_ + p;
}

TexturePtr SceneBuilder::spectrumTexture(const ParamSet& ps, const std::string& name, const Color& def,
                                         SpectrumKind kind, bool* specified) {
    if (specified) *specified = ps.has(name);
    std::string tex = ps.getTexture(name);
    if (!tex.empty()) {
        auto it = spectrumTextures_.find(tex);
        if (it != spectrumTextures_.end()) return it->second;
        auto jt = floatTextures_.find(tex);
        if (jt != floatTextures_.end()) return jt->second;
        LOG().error("undefined texture '" + tex + "' referenced by '" + name + "'; using default",
                    ps.find(name)->loc);
        return std::make_shared<ConstantTexture>(def);
    }
    Color c;
    if (ps.has(name) && ps.getRGB(name, kind, &c)) return std::make_shared<ConstantTexture>(c);
    return std::make_shared<ConstantTexture>(def);
}

// ================================================================ materials
int SceneBuilder::material(const std::string& type, const ParamSet& ps, const std::string& name, const FileLoc& loc) {
    Material m;
    m.name = name.empty() ? type : name;
    auto getColor = [&](const char* key, const Color& def, SpectrumKind kind = SpectrumKind::Reflectance) {
        Color c;
        return (ps.has(key) && ps.getRGB(key, kind, &c)) ? c : def;
    };
    auto checkRough = [&]() {
        double r = std::max(ps.getFloat("roughness", 0),
                            std::max(ps.getFloat("uroughness", 0), ps.getFloat("vroughness", 0)));
        ps.getBool("remaproughness", true);
        return r;
    };

    if (type == "diffuse") {
        m.type = MaterialType::Phong;
        m.Kd = spectrumTexture(ps, "reflectance", Color(0.5), SpectrumKind::Reflectance);
        m.physicalDiffuse = true;
    } else if (type == "phong" || type == "blinnphong") {
        m.type = MaterialType::Phong;
        m.Kd = spectrumTexture(ps, ps.has("reflectance") ? "reflectance" : "Kd", Color(0.5), SpectrumKind::Reflectance);
        m.Ks = getColor("Ks", Color(0));
        m.Ka = getColor("Ka", Color(0));
        m.Kr = getColor("Kr", Color(0));
        m.exponent = ps.has("exponent") ? ps.getFloat("exponent", 32) : ps.getFloat("shininess", 32);
        if (m.exponent < 0 || m.exponent > 1e5) {
            LOG().error("phong exponent/shininess must be in [0,1e5]; using 32", loc);
            m.exponent = 32;
        }
        m.physicalDiffuse = ps.getBool("normalized", false);
    } else if (type == "mirror") {
        m.type = MaterialType::Mirror;
        m.Kr = getColor("Kr", Color(0.9));
    } else if (type == "conductor" || type == "coatedconductor") {
        m.type = MaterialType::Mirror;
        if (checkRough() > 0)
            LOG().warning("rough conductor approximated by an ideal mirror (roughness ignored)", loc);
        Color refl;
        if (ps.has("reflectance") && ps.getRGB("reflectance", SpectrumKind::Reflectance, &refl)) {
            m.Kr = refl;
        } else {
            // Normal-incidence reflectance F0 = ((eta-1)^2 + k^2) / ((eta+1)^2 + k^2).
            Color eta(0.2), k(3.9);
            bool named = false;
            const char* etaKey = type == "coatedconductor" ? "conductor.eta" : "eta";
            const char* kKey = type == "coatedconductor" ? "conductor.k" : "k";
            if (const Param* p = ps.find(etaKey)) {
                if (p->type == "spectrum" && !p->strs.empty()) {
                    p->used = true;
                    Color f0;
                    if (namedMetalReflectance(p->strs[0], &f0)) {
                        m.Kr = f0;
                        named = true;
                    } else {
                        LOG().error("unknown named conductor spectrum '" + p->strs[0] + "'; using copper", p->loc);
                    }
                } else {
                    ps.getRGB(etaKey, SpectrumKind::Unbounded, &eta);
                }
            }
            if (const Param* p = ps.find(kKey)) {
                if (p->type == "spectrum" && !p->strs.empty()) p->used = true;
                else if (!named) ps.getRGB(kKey, SpectrumKind::Unbounded, &k);
            }
            if (!named) {
                if (!ps.has(etaKey)) {
                    namedMetalReflectance("metal-Cu-eta", &m.Kr);  // pbrt default: copper
                } else {
                    for (int i = 0; i < 3; ++i)
                        m.Kr[i] = (sqr(eta[i] - 1) + sqr(k[i])) / (sqr(eta[i] + 1) + sqr(k[i]));
                }
            }
            LOG().info("conductor '" + m.name + "' approximated as mirror with reflectance " + std::to_string(m.Kr.x) +
                       " " + std::to_string(m.Kr.y) + " " + std::to_string(m.Kr.z));
        }
        if (type == "coatedconductor")
            LOG().warning("coatedconductor approximated by a mirror conductor", loc);
    } else if (type == "dielectric" || type == "thindielectric") {
        m.type = MaterialType::Dielectric;
        if (type == "thindielectric") LOG().warning("thindielectric approximated by a solid dielectric", loc);
        if (checkRough() > 0) LOG().warning("rough dielectric approximated as smooth (roughness ignored)", loc);
        m.eta = 1.5;
        if (const Param* p = ps.find("eta")) {
            p->used = true;
            if (p->type == "float" && !p->nums.empty()) {
                m.eta = p->nums[0];
            } else if (p->type == "spectrum" && !p->strs.empty()) {
                if (!namedGlassIOR(p->strs[0], &m.eta)) {
                    LOG().error("unknown named IOR spectrum '" + p->strs[0] + "'; using 1.5", p->loc);
                    m.eta = 1.5;
                }
            } else if (p->type == "spectrum" && p->nums.size() >= 2) {
                double sum = 0;
                for (size_t i = 1; i < p->nums.size(); i += 2) sum += p->nums[i];
                m.eta = sum / (p->nums.size() / 2);
                LOG().warning("spectrally varying eta averaged to " + std::to_string(m.eta) + " (no dispersion)", p->loc);
            } else {
                LOG().error("dielectric eta must be a float or spectrum; using 1.5", p->loc);
            }
        }
        if (!(m.eta > 0) || m.eta > 10) {
            LOG().error("dielectric eta " + std::to_string(m.eta) + " out of range (0,10]; using 1.5", loc);
            m.eta = 1.5;
        }
        m.Kt = getColor("Kt", Color(1));
        if (m.eta == 1) m.type = MaterialType::Interface;
    } else if (type == "coateddiffuse") {
        m.type = MaterialType::Phong;
        m.Kd = spectrumTexture(ps, "reflectance", Color(0.5), SpectrumKind::Reflectance);
        m.physicalDiffuse = true;
        double r = checkRough();
        ps.getFloat("thickness", 0.01);
        ps.getFloat("eta", 1.5);
        if (r > 0) {
            m.Ks = Color(0.04);
            m.exponent = std::max(1.0, 2.0 / (r * r) - 2.0);
        } else {
            m.Kr = Color(0.04);
        }
        LOG().warning("coateddiffuse approximated by Phong (diffuse + 4% specular coat)", loc);
    } else if (type == "interface" || type == "none" || type == "") {
        m.type = MaterialType::Interface;
    } else if (type == "mix" || type == "measured" || type == "hair" || type == "subsurface" ||
               type == "diffusetransmission") {
        LOG().warning("material '" + type + "' not supported; using diffuse 0.5", loc);
        m.type = MaterialType::Phong;
        m.Kd = std::make_shared<ConstantTexture>(Color(0.5));
        m.physicalDiffuse = true;
        for (const auto& p : ps.params) p.used = true;
    } else {
        LOG().error("unknown material type '" + type + "'; using diffuse 0.5", loc);
        m.type = MaterialType::Phong;
        m.Kd = std::make_shared<ConstantTexture>(Color(0.5));
        m.physicalDiffuse = true;
        for (const auto& p : ps.params) p.used = true;
    }

    if (m.type == MaterialType::Phong) {
        Color kd;
        Color budget = m.Ks + m.Kr;
        if (budget.maxComponent() > 1) {
            LOG().warning("material '" + m.name + "': Ks + Kr > 1; scaled down for energy conservation", loc);
            double s = 1.0 / budget.maxComponent();
            m.Ks *= s;
            m.Kr *= s;
        }
        if (m.Kd && m.Kd->constantValue(&kd) && (kd + m.Ks + m.Kr).maxComponent() > 1 + 1e-9)
            LOG().warning("material '" + m.name +
                              "': Kd + Ks + Kr > 1; the DRT clamps Kd to conserve energy (the WSRT uses it as given)",
                          loc);
    }
    ignoreParamsUsed(ps);
    ps.reportUnused("Material \"" + type + "\"");
    scene_->materials.push_back(m);
    return (int)scene_->materials.size() - 1;
}

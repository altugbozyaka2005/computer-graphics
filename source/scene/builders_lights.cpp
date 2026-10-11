// Texture and LightSource directives.
#include "builders.h"

std::shared_ptr<const Image> SceneBuilder::loadImage(const std::string& filename, const std::string& encoding,
                                                     const FileLoc& loc) {
    std::string path = resolvePath(filename);
    std::string key = path + "|" + encoding;
    auto it = imageCache_.find(key);
    if (it != imageCache_.end()) return it->second;
    auto img = std::make_shared<Image>();
    bool linear = false;
    std::string err;
    if (!readImage(path, img.get(), &linear, &err)) {
        LOG().error("cannot load texture image '" + filename + "': " + err, loc);
        return nullptr;
    }
    if (!linear) {
        double gamma = 0;
        bool srgb = false;
        if (encoding == "sRGB" || encoding == "srgb") {
            srgb = true;
        } else if (encoding.rfind("gamma ", 0) == 0) {
            try {
                gamma = std::stod(encoding.substr(6));
            } catch (...) {
                gamma = 0;
            }
            if (!(gamma > 0)) {
                LOG().error("bad gamma encoding '" + encoding + "'; assuming sRGB", loc);
                srgb = true;
            }
        } else if (encoding != "linear") {
            LOG().error("unknown image encoding '" + encoding + "' (sRGB|linear|gamma g); assuming sRGB", loc);
            srgb = true;
        }
        for (auto& c : img->pixels)
            for (int k = 0; k < 3; ++k)
                c[k] = srgb ? srgbDecode(c[k]) : (gamma > 0 ? std::pow(c[k], gamma) : c[k]);
    }
    LOG().info("loaded texture '" + filename + "' (" + std::to_string(img->width) + "x" +
               std::to_string(img->height) + ")");
    imageCache_[key] = img;
    return img;
}

void SceneBuilder::texture(const std::string& name, const std::string& valueType, const std::string& cls,
                           const ParamSet& ps, const FileLoc& loc) {
    if (valueType != "spectrum" && valueType != "float") {
        LOG().error("texture '" + name + "' has invalid type '" + valueType + "' (spectrum|float); ignored", loc);
        return;
    }
    UVMapping map;
    map.su = ps.getFloat("uscale", 1);
    map.sv = ps.getFloat("vscale", 1);
    map.du = ps.getFloat("udelta", 0);
    map.dv = ps.getFloat("vdelta", 0);
    std::string mapping = ps.getString("mapping", "uv");
    if (mapping != "uv")
        LOG().warning("texture mapping '" + mapping + "' not supported; using uv", loc);
    SpectrumKind kind = valueType == "spectrum" ? SpectrumKind::Reflectance : SpectrumKind::Unbounded;

    TexturePtr tex;
    if (cls == "imagemap") {
        std::string file = ps.getString("filename", "");
        std::string encoding = ps.getString("encoding", "sRGB");
        std::string wrapS = ps.getString("wrap", "repeat");
        std::string filter = ps.getString("filter", "bilinear");
        double sc = ps.getFloat("scale", 1);
        bool invert = ps.getBool("invert", false);
        ps.getFloat("maxanisotropy", 8);
        ImageTexture::Wrap wrap = ImageTexture::Wrap::Repeat;
        if (wrapS == "clamp") wrap = ImageTexture::Wrap::Clamp;
        else if (wrapS == "black") wrap = ImageTexture::Wrap::Black;
        else if (wrapS != "repeat") LOG().error("unknown wrap mode '" + wrapS + "'; using repeat", loc);
        bool nearest = filter == "point";
        if (filter != "point" && filter != "bilinear")
            LOG().info("texture filter '" + filter + "' approximated by bilinear");
        std::shared_ptr<const Image> img;
        if (file.empty()) LOG().error("imagemap texture '" + name + "' has no filename", loc);
        else img = loadImage(file, encoding, loc);
        if (img) tex = std::make_shared<ImageTexture>(img, map, wrap, nearest, sc, invert);
        else tex = std::make_shared<ConstantTexture>(Color(1, 0, 1));  // magenta marks the missing texture
    } else if (cls == "checkerboard") {
        int dim = ps.getInt("dimension", 2);
        if (dim != 2) LOG().error("only 2D checkerboard textures are supported; using 2D", loc);
        TexturePtr t1 = spectrumTexture(ps, "tex1", Color(1), kind);
        TexturePtr t2 = spectrumTexture(ps, "tex2", Color(0), kind);
        tex = std::make_shared<CheckerboardTexture>(t1, t2, map);
    } else if (cls == "constant") {
        tex = spectrumTexture(ps, "value", Color(1), kind);
    } else if (cls == "scale") {
        tex = std::make_shared<ScaleTexture>(spectrumTexture(ps, "tex", Color(1), kind),
                                             spectrumTexture(ps, "scale", Color(1), SpectrumKind::Unbounded));
    } else if (cls == "mix") {
        tex = std::make_shared<MixTexture>(spectrumTexture(ps, "tex1", Color(0), kind),
                                           spectrumTexture(ps, "tex2", Color(1), kind),
                                           spectrumTexture(ps, "amount", Color(0.5), SpectrumKind::Unbounded));
    } else {
        LOG().error("unsupported texture class '" + cls + "' for texture '" + name + "'; using constant 0.5", loc);
        tex = std::make_shared<ConstantTexture>(Color(0.5));
        for (const auto& p : ps.params) p.used = true;
    }
    ps.reportUnused("Texture \"" + name + "\"");
    auto& table = valueType == "spectrum" ? spectrumTextures_ : floatTextures_;
    if (table.count(name)) LOG().warning("texture '" + name + "' redefined", loc);
    table[name] = tex;
}

void SceneBuilder::light(const std::string& type, const ParamSet& ps, const Transform& ctm, const FileLoc& loc) {
    double sc = ps.getFloat("scale", 1);
    if (sc < 0) {
        LOG().error("light scale must be >= 0; using 1", loc);
        sc = 1;
    }
    auto power = [&]() {
        double p = ps.getFloat("power", -1);
        return p;
    };
    if (type == "point" || type == "spot") {
        DeltaLight l;
        l.type = type == "point" ? DeltaLightType::Point : DeltaLightType::Spot;
        Color I(1);
        if (ps.has("I")) ps.getRGB("I", SpectrumKind::Illuminant, &I);
        Vec3 from = ps.getPoint3("from", Vec3(0, 0, 0));
        l.pos = ctm.point(from);
        double k_e = 4 * Pi;
        if (l.type == DeltaLightType::Spot) {
            Vec3 to = ps.getPoint3("to", Vec3(0, 0, 1));
            double cone = ps.getFloat("coneangle", 30), delta = ps.getFloat("conedeltaangle", 5);
            if (cone <= 0 || cone > 180 || delta < 0) {
                LOG().error("spot coneangle must be in (0,180] and conedeltaangle >= 0; using 30/5", loc);
                cone = 30;
                delta = 5;
            }
            l.dir = normalize(ctm.vector(to - from));
            if (length(to - from) == 0) {
                LOG().error("spot light 'from' equals 'to'; pointing along +z", loc);
                l.dir = normalize(ctm.vector(Vec3(0, 0, 1)));
            }
            l.cosFalloffEnd = std::cos(radians(cone));
            l.cosFalloffStart = std::cos(radians(std::max(0.0, cone - delta)));
            k_e = 2 * Pi * (1 - 0.5 * (l.cosFalloffStart + l.cosFalloffEnd));
        }
        double p = power();
        if (p > 0) sc *= p / k_e;
        l.I = I * sc;
        scene_->deltaLights.push_back(l);
    } else if (type == "distant") {
        DeltaLight l;
        l.type = DeltaLightType::Distant;
        Color L(1);
        if (ps.has("L")) ps.getRGB("L", SpectrumKind::Illuminant, &L);
        Vec3 from = ps.getPoint3("from", Vec3(0, 0, 0)), to = ps.getPoint3("to", Vec3(0, 0, 1));
        if (length(from - to) == 0) {
            LOG().error("distant light 'from' equals 'to'; ignored", loc);
            return;
        }
        l.dir = normalize(ctm.vector(from - to));
        double E = ps.getFloat("illuminance", -1);
        if (E > 0) sc *= E;
        l.I = L * sc;
        scene_->deltaLights.push_back(l);
    } else if (type == "infinite") {
        Color L(1);
        if (ps.has("filename")) {
            LOG().error("environment map '" + ps.getString("filename", "") +
                            "' not supported (constant infinite lights only); using L",
                        loc);
        }
        if (ps.has("L")) ps.getRGB("L", SpectrumKind::Illuminant, &L);
        if (const Param* p = ps.find("portal")) p->used = true;
        double E = ps.getFloat("illuminance", -1);
        if (E > 0) sc *= E / Pi;  // irradiance of a uniform environment is pi * L
        scene_->envL += L * sc;
        scene_->hasEnv = true;
    } else if (type == "goniometric" || type == "projection") {
        LOG().warning("light type '" + type + "' not supported; ignored", loc);
        for (const auto& p : ps.params) p.used = true;
        return;
    } else {
        LOG().error("unknown light type '" + type + "'; ignored", loc);
        for (const auto& p : ps.params) p.used = true;
        return;
    }
    ps.reportUnused("LightSource \"" + type + "\"");
}

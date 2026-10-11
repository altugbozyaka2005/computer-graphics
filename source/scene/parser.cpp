#include "parser.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <sstream>

#include "builders.h"

namespace {

struct Token {
    std::string text;
    bool quoted = false;
    FileLoc loc;
};

struct ParseError {
    std::string msg;
    FileLoc loc;
};

const std::set<std::string>& directives() {
    static const std::set<std::string> d = {
        "Identity", "Translate", "Scale", "Rotate", "LookAt", "Transform", "ConcatTransform", "CoordinateSystem",
        "CoordSysTransform", "ReverseOrientation", "Camera", "Film", "Sampler", "PixelFilter", "Integrator",
        "Accelerator", "ColorSpace", "Option", "WorldBegin", "WorldEnd", "AttributeBegin", "AttributeEnd",
        "TransformBegin", "TransformEnd", "Attribute", "Shape", "Material", "MakeNamedMaterial", "NamedMaterial",
        "Texture", "LightSource", "AreaLightSource", "ObjectBegin", "ObjectEnd", "ObjectInstance", "Include",
        "Import", "MakeNamedMedium", "MediumInterface", "TransformTimes", "ActiveTransform"};
    return d;
}
bool isDirective(const Token& t) { return !t.quoted && directives().count(t.text) > 0; }

// Token text made safe for log messages: non-printable bytes escaped, long tokens truncated.
std::string printable(const std::string& s) {
    std::string r;
    for (unsigned char c : s) {
        if (r.size() >= 40) {
            r += "...";
            break;
        }
        if (c >= 32 && c < 127) {
            r += (char)c;
        } else {
            char buf[8];
            std::snprintf(buf, sizeof buf, "\\x%02X", c);
            r += buf;
        }
    }
    return r;
}

bool parseNumber(const std::string& s, double* v) {
    if (s.empty()) return false;
    char* end = nullptr;
    double d = std::strtod(s.c_str(), &end);
    if (end != s.c_str() + s.size()) return false;
    if (!std::isfinite(d)) return false;
    *v = d;
    return true;
}

class Tokenizer {
public:
    Tokenizer(std::string src, std::string file) : src_(std::move(src)), file_(std::move(file)) {}

    bool next(Token* t) {
        while (pos_ < src_.size()) {
            char c = src_[pos_];
            if (c == '#') {
                while (pos_ < src_.size() && src_[pos_] != '\n') advance();
            } else if (std::isspace((unsigned char)c)) {
                advance();
            } else {
                break;
            }
        }
        if (pos_ >= src_.size()) return false;
        t->loc = FileLoc{file_, line_, col_};
        t->quoted = false;
        char c = src_[pos_];
        if (c == '"') {
            advance();
            std::string s;
            while (true) {
                if (pos_ >= src_.size() || src_[pos_] == '\n')
                    throw ParseError{"unterminated string (missing closing '\"')", t->loc};
                char ch = src_[pos_];
                if (ch == '"') {
                    advance();
                    break;
                }
                if (ch == '\\') {
                    advance();
                    if (pos_ >= src_.size()) throw ParseError{"unterminated escape sequence in string", t->loc};
                    char e = src_[pos_];
                    s += e == 'n' ? '\n' : (e == 't' ? '\t' : e);
                    advance();
                    continue;
                }
                s += ch;
                advance();
            }
            t->text = s;
            t->quoted = true;
            return true;
        }
        if (c == '[' || c == ']') {
            t->text = std::string(1, c);
            advance();
            return true;
        }
        size_t start = pos_;
        while (pos_ < src_.size()) {
            char ch = src_[pos_];
            if (std::isspace((unsigned char)ch) || ch == '"' || ch == '[' || ch == ']' || ch == '#') break;
            advance();
        }
        t->text = src_.substr(start, pos_ - start);
        return true;
    }
    const std::string& file() const { return file_; }

private:
    void advance() {
        if (src_[pos_] == '\n') {
            ++line_;
            col_ = 1;
        } else {
            ++col_;
        }
        ++pos_;
    }
    std::string src_, file_;
    size_t pos_ = 0;
    int line_ = 1, col_ = 1;
};

bool readFile(const std::string& path, std::string* out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::ostringstream ss;
    ss << f.rdbuf();
    *out = ss.str();
    return true;
}

struct GraphicsState {
    Transform ctm;
    bool reverseOrientation = false;
    int material = 0;
    AreaLightState area;
};

struct ShapeRecord {
    std::string type;
    ParamSet params;
    Transform ctm;
    bool reverseOrientation;
    int material;
    FileLoc loc;
};

class Parser {
public:
    Parser(Scene* scene, std::string baseDir) : baseDir_(baseDir), builder_(scene, baseDir) {}

    bool run(const std::string& path);

private:
    bool nextToken(Token* t) {
        if (havePeek_) {
            *t = peek_;
            havePeek_ = false;
            return true;
        }
        while (!stack_.empty()) {
            if (stack_.back()->next(t)) return true;
            stack_.pop_back();
        }
        return false;
    }
    bool peekToken(Token** t) {
        if (!havePeek_) {
            if (!nextToken(&peek_)) return false;
            havePeek_ = true;
        }
        *t = &peek_;
        return true;
    }
    void skipToDirective() {
        Token* pk;
        while (peekToken(&pk) && !isDirective(*pk)) {
            Token t;
            nextToken(&t);
        }
    }
    bool readNumbers(const Token& dir, size_t n, std::vector<double>* out);
    bool readString(const Token& dir, std::string* out);
    ParamSet parseParams();
    void handle(const Token& t);
    void applyTransform(const Token& dir, const Transform& t, bool concat);

    std::string baseDir_;
    SceneBuilder builder_;
    std::vector<std::unique_ptr<Tokenizer>> stack_;
    bool havePeek_ = false;
    Token peek_;

    GraphicsState gs_;
    std::vector<GraphicsState> attrStack_;
    std::vector<Transform> xformStack_;
    std::map<std::string, int> namedMaterials_;
    std::map<std::string, Transform> coordSys_;
    std::map<std::string, std::vector<ShapeRecord>> objects_;
    std::string currentObject_;
    bool inWorld_ = false;
};

bool Parser::readNumbers(const Token& dir, size_t n, std::vector<double>* out) {
    out->clear();
    Token* pk;
    bool bracket = false;
    if (peekToken(&pk) && !pk->quoted && pk->text == "[") {
        Token t;
        nextToken(&t);
        bracket = true;
    }
    while (peekToken(&pk)) {
        if (bracket && !pk->quoted && pk->text == "]") {
            Token t;
            nextToken(&t);
            bracket = false;
            break;
        }
        double v;
        if (pk->quoted || !parseNumber(pk->text, &v)) break;
        Token t;
        nextToken(&t);
        out->push_back(v);
        if (!bracket && out->size() == n) break;
    }
    if (bracket) {
        LOG().error(dir.text + ": missing ']' or non-numeric value inside brackets; directive ignored", dir.loc);
        skipToDirective();
        return false;
    }
    if (out->size() != n) {
        std::string bad;
        if (peekToken(&pk) && !isDirective(*pk))
            bad = " (found " + (pk->quoted ? "\"" + printable(pk->text) + "\"" : "'" + printable(pk->text) + "'") + " where a number was expected)";
        LOG().error(dir.text + " expects " + std::to_string(n) + " numeric arguments but got " +
                        std::to_string(out->size()) + bad + "; directive ignored",
                    dir.loc);
        skipToDirective();
        return false;
    }
    return true;
}

bool Parser::readString(const Token& dir, std::string* out) {
    Token* pk;
    if (!peekToken(&pk) || !pk->quoted) {
        LOG().error(dir.text + " expects a quoted string argument; directive ignored", dir.loc);
        skipToDirective();
        return false;
    }
    Token t;
    nextToken(&t);
    *out = t.text;
    return true;
}

ParamSet Parser::parseParams() {
    ParamSet ps;
    ps.baseDir = baseDir_;
    static const std::set<std::string> numericTypes = {"integer", "float", "point2", "vector2", "point3",
                                                       "vector3", "normal3", "rgb", "blackbody"};
    static const std::set<std::string> knownTypes = {"integer", "float",   "point2", "vector2", "point3",
                                                     "vector3", "normal3", "rgb",    "blackbody", "bool",
                                                     "string",  "texture", "spectrum"};
    Token* pk;
    while (peekToken(&pk) && pk->quoted) {
        Token decl;
        nextToken(&decl);
        std::istringstream ss(decl.text);
        std::string type, name, extra;
        ss >> type >> name;
        bool declOk = !type.empty() && !name.empty() && !(ss >> extra);
        type = canonicalParamType(type);

        std::vector<Token> vals;
        Token* nx;
        if (!peekToken(&nx) || isDirective(*nx)) {
            LOG().error("parameter \"" + decl.text + "\" has no value", decl.loc);
            continue;
        }
        if (!nx->quoted && nx->text == "[") {
            Token t;
            nextToken(&t);
            while (true) {
                if (!nextToken(&t)) throw ParseError{"unterminated '[' in parameter \"" + decl.text + "\"", decl.loc};
                if (!t.quoted && t.text == "]") break;
                if (!t.quoted && t.text == "[") throw ParseError{"nested '[' in parameter \"" + decl.text + "\"", t.loc};
                if (isDirective(t))
                    throw ParseError{"missing ']' for parameter \"" + decl.text + "\" before directive '" + t.text + "'",
                                     t.loc};
                vals.push_back(t);
            }
        } else if (nx->quoted) {
            // A single quoted value is only valid for string-like types; otherwise it
            // is the next parameter declaration and this one has no value.
            std::istringstream ns(nx->text);
            std::string nt, nn, nextra;
            ns >> nt >> nn;
            bool looksLikeDecl = knownTypes.count(canonicalParamType(nt)) && !nn.empty() && !(ns >> nextra);
            if (type == "string" || type == "texture" || type == "spectrum" || type == "bool" || !looksLikeDecl) {
                Token t;
                nextToken(&t);
                vals.push_back(t);
            } else {
                LOG().error("parameter \"" + decl.text + "\" has no value", decl.loc);
                continue;
            }
        } else if (!nx->quoted && nx->text == "]") {
            Token t;
            nextToken(&t);
            LOG().error("unexpected ']' after parameter \"" + decl.text + "\"", t.loc);
            continue;
        } else {
            Token t;
            nextToken(&t);
            vals.push_back(t);
        }

        if (!declOk) {
            LOG().error("malformed parameter declaration \"" + printable(decl.text) + "\" (expected \"type name\"); ignored",
                        decl.loc);
            continue;
        }
        if (!knownTypes.count(type)) {
            LOG().error("unknown parameter type '" + printable(type) + "' in \"" + printable(decl.text) + "\"; ignored", decl.loc);
            continue;
        }
        Param p;
        p.type = type;
        p.name = name;
        p.loc = decl.loc;
        bool ok = true;
        std::string why;
        if (numericTypes.count(type)) {
            for (const auto& v : vals) {
                double d;
                if (v.quoted || !parseNumber(v.text, &d)) {
                    ok = false;
                    why = "non-numeric value '" + printable(v.text) + "'";
                    break;
                }
                if (type == "integer" && d != std::floor(d)) {
                    ok = false;
                    why = "non-integer value '" + v.text + "'";
                    break;
                }
                p.nums.push_back(d);
            }
            if (ok) {
                size_t n = p.nums.size();
                if (n == 0) { ok = false; why = "no values"; }
                else if ((type == "point2" || type == "vector2") && n % 2) { ok = false; why = "value count not a multiple of 2"; }
                else if ((type == "point3" || type == "vector3" || type == "normal3") && n % 3) { ok = false; why = "value count not a multiple of 3"; }
                else if (type == "rgb" && n != 3) { ok = false; why = "rgb needs exactly 3 values"; }
                else if (type == "blackbody" && n > 2) { ok = false; why = "blackbody takes a single temperature"; }
            }
        } else if (type == "bool") {
            for (const auto& v : vals) {
                if (v.text == "true") p.bools.push_back(true);
                else if (v.text == "false") p.bools.push_back(false);
                else { ok = false; why = "bool value must be true or false, got '" + v.text + "'"; break; }
            }
        } else if (type == "string" || type == "texture") {
            for (const auto& v : vals) {
                if (!v.quoted) { ok = false; why = "string values must be quoted, got '" + v.text + "'"; break; }
                p.strs.push_back(v.text);
            }
        } else {  // spectrum: numbers or one string
            bool allNum = true;
            for (const auto& v : vals) {
                double d;
                if (v.quoted || !parseNumber(v.text, &d)) { allNum = false; break; }
                p.nums.push_back(d);
            }
            if (!allNum) {
                p.nums.clear();
                if (vals.size() == 1 && vals[0].quoted) p.strs.push_back(vals[0].text);
                else { ok = false; why = "spectrum must be (lambda, value) pairs or a quoted name/filename"; }
            } else if (p.nums.size() % 2) {
                ok = false;
                why = "spectrum needs (lambda, value) pairs";
            }
        }
        if (ok && (p.nums.size() + p.strs.size() + p.bools.size()) == 0) { ok = false; why = "no values"; }
        if (!ok) {
            LOG().error("invalid parameter \"" + decl.text + "\": " + why + "; parameter ignored", decl.loc);
            continue;
        }
        if (ps.find(name)) LOG().warning("parameter '" + name + "' given more than once; the last one is used", decl.loc);
        ps.params.push_back(p);
    }
    return ps;
}

void Parser::applyTransform(const Token& dir, const Transform& t, bool concat) {
    if (!t.valid()) {
        LOG().error(dir.text + " produces a singular (non-invertible) transform; directive ignored", dir.loc);
        return;
    }
    gs_.ctm = concat ? gs_.ctm * t : t;
}

void Parser::handle(const Token& t) {
    const std::string& d = t.text;
    std::vector<double> v;
    std::string s1, s2, s3;
    auto requireWorld = [&](bool world) {
        if (world && !inWorld_) {
            LOG().error(d + " is only allowed after WorldBegin; ignored", t.loc);
            return false;
        }
        if (!world && inWorld_) {
            LOG().error(d + " is only allowed before WorldBegin; ignored", t.loc);
            return false;
        }
        return true;
    };

    if (d == "Identity") {
        gs_.ctm = Transform();
    } else if (d == "Translate") {
        if (readNumbers(t, 3, &v)) applyTransform(t, translate(Vec3(v[0], v[1], v[2])), true);
    } else if (d == "Scale") {
        if (readNumbers(t, 3, &v)) applyTransform(t, scale(v[0], v[1], v[2]), true);
    } else if (d == "Rotate") {
        if (readNumbers(t, 4, &v)) {
            if (v[1] == 0 && v[2] == 0 && v[3] == 0) LOG().error("Rotate axis must be non-zero; ignored", t.loc);
            else applyTransform(t, rotate(v[0], Vec3(v[1], v[2], v[3])), true);
        }
    } else if (d == "LookAt") {
        if (readNumbers(t, 9, &v)) {
            bool ok;
            Transform la = lookAt(Vec3(v[0], v[1], v[2]), Vec3(v[3], v[4], v[5]), Vec3(v[6], v[7], v[8]), &ok);
            if (!ok) LOG().error("LookAt: eye equals look point or up is parallel to the view direction; ignored", t.loc);
            else applyTransform(t, la, true);
        }
    } else if (d == "Transform" || d == "ConcatTransform") {
        if (readNumbers(t, 16, &v)) applyTransform(t, fromPbrtMatrix(v.data()), d == "ConcatTransform");
    } else if (d == "CoordinateSystem") {
        if (readString(t, &s1)) coordSys_[s1] = gs_.ctm;
    } else if (d == "CoordSysTransform") {
        if (readString(t, &s1)) {
            auto it = coordSys_.find(s1);
            if (it == coordSys_.end()) LOG().error("unknown coordinate system '" + s1 + "'", t.loc);
            else gs_.ctm = it->second;
        }
    } else if (d == "ReverseOrientation") {
        gs_.reverseOrientation = !gs_.reverseOrientation;
    } else if (d == "Camera" || d == "Film" || d == "Sampler" || d == "PixelFilter" || d == "Integrator" ||
               d == "Accelerator") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(false)) return;
        if (d == "Camera") {
            builder_.camera(s1, ps, gs_.ctm, t.loc);
            coordSys_["camera"] = gs_.ctm.valid() ? gs_.ctm.inverse() : Transform();
        } else if (d == "Film") builder_.film(s1, ps, t.loc);
        else if (d == "Sampler") builder_.sampler(s1, ps, t.loc);
        else if (d == "PixelFilter") builder_.pixelFilter(s1, ps, t.loc);
        else if (d == "Integrator") builder_.integrator(s1, ps, t.loc);
        else builder_.accelerator(s1, ps, t.loc);
    } else if (d == "ColorSpace") {
        if (readString(t, &s1) && s1 != "srgb")
            LOG().warning("colour space '" + s1 + "' not supported; rendering in linear sRGB", t.loc);
    } else if (d == "Option") {
        ParamSet ps = parseParams();
        for (auto& p : ps.params) LOG().info("Option \"" + p.type + " " + p.name + "\" ignored");
    } else if (d == "WorldBegin") {
        if (inWorld_) LOG().error("WorldBegin appears more than once", t.loc);
        inWorld_ = true;
        gs_.ctm = Transform();
        coordSys_["world"] = Transform();
    } else if (d == "WorldEnd") {
        // pbrt-v3 syntax, accepted for compatibility.
    } else if (d == "AttributeBegin") {
        attrStack_.push_back(gs_);
    } else if (d == "AttributeEnd") {
        if (attrStack_.empty()) {
            LOG().error("AttributeEnd without matching AttributeBegin; ignored", t.loc);
        } else {
            gs_ = attrStack_.back();
            attrStack_.pop_back();
        }
    } else if (d == "TransformBegin") {
        LOG().info("TransformBegin is deprecated in pbrt-v4 (use AttributeBegin)");
        xformStack_.push_back(gs_.ctm);
    } else if (d == "TransformEnd") {
        if (xformStack_.empty()) {
            LOG().error("TransformEnd without matching TransformBegin; ignored", t.loc);
        } else {
            gs_.ctm = xformStack_.back();
            xformStack_.pop_back();
        }
    } else if (d == "Attribute") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        LOG().warning("Attribute \"" + s1 + "\" (default parameter values) not supported; ignored", t.loc);
    } else if (d == "Shape") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        if (!currentObject_.empty()) {
            if (gs_.area.active)
                LOG().warning("area lights inside ObjectBegin/ObjectEnd are not supported; instance is not emissive",
                              t.loc);
            objects_[currentObject_].push_back({s1, ps, gs_.ctm, gs_.reverseOrientation, gs_.material, t.loc});
            return;
        }
        builder_.shape(s1, ps, gs_.ctm, gs_.reverseOrientation, gs_.material, gs_.area, t.loc);
    } else if (d == "Material") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        gs_.material = builder_.material(s1, ps, "", t.loc);
    } else if (d == "MakeNamedMaterial") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        std::string type = ps.getString("type", "");
        if (type.empty()) {
            LOG().error("MakeNamedMaterial \"" + s1 + "\" lacks \"string type\"; using diffuse", t.loc);
            type = "diffuse";
        }
        if (namedMaterials_.count(s1)) LOG().warning("named material '" + s1 + "' redefined", t.loc);
        namedMaterials_[s1] = builder_.material(type, ps, s1, t.loc);
    } else if (d == "NamedMaterial") {
        if (!readString(t, &s1)) return;
        auto it = namedMaterials_.find(s1);
        if (it == namedMaterials_.end())
            LOG().error("undefined named material '" + s1 + "'; keeping the current material", t.loc);
        else gs_.material = it->second;
    } else if (d == "Texture") {
        if (!readString(t, &s1) || !readString(t, &s2) || !readString(t, &s3)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        builder_.texture(s1, s2, s3, ps, t.loc);
    } else if (d == "LightSource") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        if (!currentObject_.empty()) LOG().warning("LightSource inside an object definition is applied once", t.loc);
        builder_.light(s1, ps, gs_.ctm, t.loc);
    } else if (d == "AreaLightSource") {
        if (!readString(t, &s1)) return;
        ParamSet ps = parseParams();
        if (!requireWorld(true)) return;
        gs_.area.active = true;
        gs_.area.type = s1;
        gs_.area.params = ps;
        gs_.area.loc = t.loc;
    } else if (d == "ObjectBegin") {
        if (!readString(t, &s1)) return;
        if (!currentObject_.empty()) {
            LOG().error("ObjectBegin \"" + s1 + "\" inside object \"" + currentObject_ + "\" (nesting not allowed)",
                        t.loc);
            return;
        }
        if (objects_.count(s1)) LOG().warning("object '" + s1 + "' redefined", t.loc);
        objects_[s1].clear();
        currentObject_ = s1;
        attrStack_.push_back(gs_);
    } else if (d == "ObjectEnd") {
        if (currentObject_.empty()) {
            LOG().error("ObjectEnd without matching ObjectBegin; ignored", t.loc);
        } else {
            currentObject_.clear();
            if (!attrStack_.empty()) {
                gs_ = attrStack_.back();
                attrStack_.pop_back();
            }
        }
    } else if (d == "ObjectInstance") {
        if (!readString(t, &s1)) return;
        if (!requireWorld(true)) return;
        auto it = objects_.find(s1);
        if (it == objects_.end()) {
            LOG().error("ObjectInstance of undefined object '" + s1 + "'; ignored", t.loc);
            return;
        }
        AreaLightState none;
        for (const auto& rec : it->second)
            builder_.shape(rec.type, rec.params, gs_.ctm * rec.ctm, rec.reverseOrientation, rec.material, none,
                           rec.loc);
    } else if (d == "Include" || d == "Import") {
        if (!readString(t, &s1)) return;
        std::string path = (!s1.empty() && s1[0] == '/') ? s1 : baseDir_ + s1;
        if (stack_.size() > 32) {
            LOG().error(d + " nesting too deep (recursive include?) for '" + s1 + "'; ignored", t.loc);
            return;
        }
        std::string src;
        if (!readFile(path, &src)) {
            LOG().error(d + ": cannot open file '" + s1 + "'; ignored", t.loc);
            return;
        }
        if (havePeek_) {
            LOG().error("internal parser state error before " + d, t.loc);
            return;
        }
        LOG().info(d + " '" + s1 + "'");
        stack_.push_back(std::make_unique<Tokenizer>(src, path));
    } else if (d == "MakeNamedMedium") {
        if (!readString(t, &s1)) return;
        parseParams();
        LOG().warning("participating media not supported; MakeNamedMedium \"" + s1 + "\" ignored", t.loc);
    } else if (d == "MediumInterface") {
        Token* pk;
        for (int i = 0; i < 2 && peekToken(&pk) && pk->quoted; ++i) {
            Token x;
            nextToken(&x);
        }
        LOG().warning("participating media not supported; MediumInterface ignored", t.loc);
    } else if (d == "TransformTimes") {
        if (readNumbers(t, 2, &v)) LOG().warning("TransformTimes ignored (no motion blur)", t.loc);
    } else if (d == "ActiveTransform") {
        Token x;
        if (nextToken(&x)) LOG().warning("ActiveTransform " + x.text + " ignored (no motion blur)", t.loc);
    }
}

bool Parser::run(const std::string& path) {
    std::string src;
    if (!readFile(path, &src)) {
        LOG().error("cannot open scene file '" + path + "'");
        return false;
    }
    stack_.push_back(std::make_unique<Tokenizer>(src, path));
    try {
        Token t;
        while (nextToken(&t)) {
            if (!isDirective(t)) {
                std::string shown = t.quoted ? "\"" + printable(t.text) + "\"" : printable(t.text);
                if (!t.quoted && !t.text.empty() && std::isalpha((unsigned char)t.text[0]))
                    LOG().error("unknown directive '" + shown + "'; skipping to the next directive", t.loc);
                else
                    LOG().error("unexpected token " + shown + " (expected a directive); skipping", t.loc);
                skipToDirective();
                continue;
            }
            handle(t);
        }
    } catch (const ParseError& e) {
        LOG().error("syntax error: " + e.msg + " -- parsing aborted", e.loc);
        return false;
    }
    if (!inWorld_) {
        LOG().error("scene has no WorldBegin directive; nothing to render");
        return false;
    }
    if (!attrStack_.empty())
        LOG().warning(std::to_string(attrStack_.size()) + " AttributeBegin block(s) never closed with AttributeEnd");
    if (!currentObject_.empty()) LOG().warning("ObjectBegin \"" + currentObject_ + "\" never closed with ObjectEnd");
    if (!builder_.hasCamera())
        LOG().warning("no Camera directive; using the default perspective camera (fov 90) at the origin");
    return true;
}

}  // namespace

bool parseScene(const std::string& path, Scene* scene) {
    std::string baseDir;
    size_t slash = path.find_last_of('/');
    if (slash != std::string::npos) baseDir = path.substr(0, slash + 1);
    // Material 0: pbrt's default material (diffuse, reflectance 0.5).
    Material def;
    def.name = "default";
    def.Kd = std::make_shared<ConstantTexture>(Color(0.5));
    def.physicalDiffuse = true;
    scene->materials.clear();
    scene->materials.push_back(def);
    Parser parser(scene, baseDir);
    return parser.run(path);
}

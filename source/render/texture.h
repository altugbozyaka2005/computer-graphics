// Spectrum (RGB) textures evaluated at surface (u,v) (pbrt-v4 Section 10.3-10.4).
#pragma once

#include <memory>
#include <string>

#include "../core/image.h"
#include "../core/math.h"

// pbrt "uv" mapping: s = su * u + du, t = sv * v + dv.
struct UVMapping {
    double su = 1, sv = 1, du = 0, dv = 0;
    Vec2 map(const Vec2& uv) const { return {su * uv.x + du, sv * uv.y + dv}; }
};

class Texture {
public:
    virtual ~Texture() {}
    virtual Color eval(const Vec2& uv) const = 0;
    // True (and sets *c) when the texture is a single constant value.
    virtual bool constantValue(Color*) const { return false; }
};
using TexturePtr = std::shared_ptr<const Texture>;

class ConstantTexture : public Texture {
public:
    explicit ConstantTexture(const Color& c) : c_(c) {}
    Color eval(const Vec2&) const override { return c_; }
    bool constantValue(Color* c) const override { *c = c_; return true; }

private:
    Color c_;
};

class ImageTexture : public Texture {
public:
    enum class Wrap { Repeat, Clamp, Black };
    ImageTexture(std::shared_ptr<const Image> img, UVMapping m, Wrap wrap, bool nearest, double scale, bool invert)
        : img_(std::move(img)), map_(m), wrap_(wrap), nearest_(nearest), scale_(scale), invert_(invert) {}
    Color eval(const Vec2& uv) const override;

private:
    bool texel(int x, int y, Color* c) const;
    std::shared_ptr<const Image> img_;  // linear RGB, row 0 = top
    UVMapping map_;
    Wrap wrap_;
    bool nearest_;
    double scale_;
    bool invert_;
};

class CheckerboardTexture : public Texture {
public:
    CheckerboardTexture(TexturePtr t1, TexturePtr t2, UVMapping m) : t1_(std::move(t1)), t2_(std::move(t2)), map_(m) {}
    Color eval(const Vec2& uv) const override {
        Vec2 st = map_.map(uv);
        long c = (long)std::floor(st.x) + (long)std::floor(st.y);
        return (c % 2 == 0) ? t1_->eval(uv) : t2_->eval(uv);
    }

private:
    TexturePtr t1_, t2_;
    UVMapping map_;
};

class ScaleTexture : public Texture {
public:
    ScaleTexture(TexturePtr t, TexturePtr s) : t_(std::move(t)), s_(std::move(s)) {}
    Color eval(const Vec2& uv) const override { return t_->eval(uv) * s_->eval(uv); }

private:
    TexturePtr t_, s_;
};

class MixTexture : public Texture {
public:
    MixTexture(TexturePtr t1, TexturePtr t2, TexturePtr amount)
        : t1_(std::move(t1)), t2_(std::move(t2)), a_(std::move(amount)) {}
    Color eval(const Vec2& uv) const override {
        double a = a_->eval(uv).average();
        return t1_->eval(uv) * (1 - a) + t2_->eval(uv) * a;
    }

private:
    TexturePtr t1_, t2_, a_;
};

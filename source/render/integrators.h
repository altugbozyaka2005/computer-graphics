// The two ray-tracing integrators required by the coursework.
//
//  WhittedIntegrator  : Whitted-style ray tracer. Blinn-Phong local shading with
//                       ambient term, hard shadows from point-like lights, and
//                       recursive ideal reflection/refraction (Fresnel, TIR).
//  DistributedIntegrator : Cook-style distributed ray tracer. Area lights sampled
//                       with N shadow rays to random points on the light (soft
//                       shadows), energy-conserving Phong BRDF, and one indirect
//                       ray per bounce (uniform hemisphere) up to maxdepth.
#pragma once

#include "../core/log.h"
#include "../core/rng.h"
#include "../scene/scene.h"

class Integrator {
public:
    explicit Integrator(const Scene& s) : scene_(s) {}
    virtual ~Integrator() {}
    virtual Color Li(const Ray& ray, RNG& rng) const = 0;

protected:
    Ray spawn(const Vec3& p, const Vec3& ng, const Vec3& dir) const {
        ++tlsStats.secondaryRays;
        return Ray(offsetRayOrigin(p, ng, dir), dir);
    }
    // True if the segment from p (offset along ng) to target is blocked.
    bool occludedTo(const Vec3& p, const Vec3& ng, const Vec3& target) const;
    bool occludedDir(const Vec3& p, const Vec3& ng, const Vec3& dir) const;
    const Scene& scene_;
};

class WhittedIntegrator : public Integrator {
public:
    using Integrator::Integrator;
    Color Li(const Ray& ray, RNG& rng) const override { return trace(ray, 0, Color(1), rng); }

private:
    // `weight` is the product of the reflection/transmission factors along the path
    // to this ray; branches whose weight drops below kMinWeight are not traced
    // (adaptive ray-tree depth control, Hall & Greenberg 1983).
    Color trace(const Ray& ray, int depth, const Color& weight, RNG& rng) const;
    static constexpr double kMinWeight = 1e-3;
    // Fraction of a light's illumination reaching p (shadow test). Classic Whitted:
    // 0 or 1. With "transparentshadows": dielectrics attenuate the shadow ray by their
    // Fresnel transmission and tint Kt instead of blocking it (filtered shadow rays;
    // the bending of the light by refraction is ignored).
    Color visibility(const Vec3& p, const Vec3& ng, const Vec3& wi, bool toInfinity, const Vec3& target) const;
};

class DistributedIntegrator : public Integrator {
public:
    using Integrator::Integrator;
    Color Li(const Ray& ray, RNG& rng) const override { return trace(ray, 0, true, rng); }

private:
    Color trace(const Ray& ray, int depth, bool countEmission, RNG& rng) const;
    Color directLighting(const Hit& hit, const Vec3& wo, const Vec3& ns, const Vec3& ng, const Color& kd,
                         const Material& m, RNG& rng) const;
};

// Energy-conserving modified Phong BRDF (Lafortune & Willems 1994):
//   f = kd / pi + ks (n + 2) / (2 pi) * max(0, r . wi)^n,  r = reflect(wo, n_s)
inline Color phongBRDF(const Color& kd, const Color& ks, double n, const Vec3& r, const Vec3& wi) {
    Color f = kd * InvPi;
    if (!ks.isBlack()) {
        double c = dot(r, wi);
        if (c > 0) f += ks * ((n + 2) * Inv2Pi * std::pow(c, n));
    }
    return f;
}

// Materials. One "Phong family" material carries the parameters used by both
// integrators: the WSRT evaluates the Blinn-Phong illumination model with them,
// the DRT evaluates the energy-conserving (modified) Phong BRDF.
#pragma once

#include <string>

#include "../core/math.h"
#include "texture.h"

enum class MaterialType {
    Phong,       // pbrt "diffuse", ext "phong"/"blinnphong", approximations of "coateddiffuse"
    Mirror,      // ext "mirror", pbrt "conductor" (smooth)
    Dielectric,  // pbrt "dielectric" (smooth)
    Interface    // pbrt "interface": invisible boundary, rays pass straight through
};

struct Material {
    std::string name = "default";
    MaterialType type = MaterialType::Phong;
    TexturePtr Kd;              // diffuse reflectance (texturable)
    Color Ks{0, 0, 0};          // specular reflectance
    Color Ka{0, 0, 0};          // WSRT ambient coefficient
    Color Kr{0, 0, 0};          // ideal mirror reflectance (mirror material, or added to Phong)
    Color Kt{1, 1, 1};          // transmission tint (dielectric)
    double exponent = 32;       // Phong / Blinn-Phong shininess
    double eta = 1.5;           // index of refraction (dielectric)
    bool physicalDiffuse = false;  // WSRT: use Kd/pi (pbrt "diffuse") instead of classic Kd

    Color diffuse(const Vec2& uv) const { return Kd ? Kd->eval(uv) : Color(0.5); }
    // Diffuse reflectance clamped so that kd + ks + kr <= 1 per channel (energy conservation).
    Color diffuseConserving(const Vec2& uv) const {
        Color kd = diffuse(uv);
        Color budget = vmax(Color(1) - Ks - Kr, Color(0));
        return vmin(vmax(kd, Color(0)), budget);
    }
};

// Fresnel reflectance for a dielectric interface (pbrt-v4 FrDielectric).
// cosThetaI is measured against the outward normal; negative means the ray
// arrives from inside, in which case eta is inverted.
inline double frDielectric(double cosThetaI, double eta) {
    cosThetaI = clampd(cosThetaI, -1, 1);
    if (cosThetaI < 0) {
        eta = 1 / eta;
        cosThetaI = -cosThetaI;
    }
    double sin2ThetaI = 1 - cosThetaI * cosThetaI;
    double sin2ThetaT = sin2ThetaI / (eta * eta);
    if (sin2ThetaT >= 1) return 1.0;  // total internal reflection
    double cosThetaT = safeSqrt(1 - sin2ThetaT);
    double rParl = (eta * cosThetaI - cosThetaT) / (eta * cosThetaI + cosThetaT);
    double rPerp = (cosThetaI - eta * cosThetaT) / (cosThetaI + eta * cosThetaT);
    return (rParl * rParl + rPerp * rPerp) / 2;
}

// Snell refraction (pbrt-v4 Refract). wi points away from the surface, n is the
// outward normal. Returns false on total internal reflection. *etap receives
// the relative IOR actually used (eta or 1/eta).
inline bool refractDir(const Vec3& wi, Vec3 n, double eta, double* etap, Vec3* wt) {
    double cosThetaI = dot(n, wi);
    if (cosThetaI < 0) {
        eta = 1 / eta;
        cosThetaI = -cosThetaI;
        n = -n;
    }
    double sin2ThetaI = std::max(0.0, 1 - cosThetaI * cosThetaI);
    double sin2ThetaT = sin2ThetaI / (eta * eta);
    if (sin2ThetaT >= 1) return false;
    double cosThetaT = safeSqrt(1 - sin2ThetaT);
    *wt = normalize(-wi / eta + n * (cosThetaI / eta - cosThetaT));
    if (etap) *etap = eta;
    return true;
}

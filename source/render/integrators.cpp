#include "integrators.h"

#include "../core/sampling.h"

bool Integrator::occludedTo(const Vec3& p, const Vec3& ng, const Vec3& target) const {
    Vec3 dir = target - p;
    Vec3 o = offsetRayOrigin(p, ng, dir);
    Vec3 d = target - o;
    double dist = length(d);
    if (dist <= 0) return false;
    // Stop just short of the target so the light's own surface does not occlude.
    return scene_.occluded(Ray(o, d / dist), dist * (1 - 1e-6));
}

bool Integrator::occludedDir(const Vec3& p, const Vec3& ng, const Vec3& dir) const {
    return scene_.occluded(Ray(offsetRayOrigin(p, ng, dir), dir), Infinity);
}

// ======================================================================= WSRT
Color WhittedIntegrator::visibility(const Vec3& p, const Vec3& ng, const Vec3& wi, bool toInfinity,
                                    const Vec3& target) const {
    if (!scene_.integrator.transparentShadows) {
        bool blocked = toInfinity ? occludedDir(p, ng, wi) : occludedTo(p, ng, target);
        return blocked ? Color(0) : Color(1);
    }
    Color T(1);
    Vec3 o = offsetRayOrigin(p, ng, wi);
    for (int i = 0; i < 64; ++i) {
        double tMax = toInfinity ? Infinity : length(target - o) * (1 - 1e-6);
        Hit h;
        ++tlsStats.shadowRays;
        if (!scene_.intersect(Ray(o, wi), &h) || h.t >= tMax) return T;
        const Material& m = scene_.materials[h.shape->materialId];
        if (m.type == MaterialType::Dielectric) {
            // Same Fresnel factor on entry and exit (no spurious total internal
            // reflection, since the straight shadow ray ignores refraction).
            T *= m.Kt * (1 - frDielectric(absDot(wi, h.ns), m.eta));
        } else if (m.type != MaterialType::Interface) {
            return Color(0);
        }
        if (T.maxComponent() < 1e-4) return Color(0);
        o = offsetRayOrigin(h.p, h.ng, wi);
    }
    return T;
}

Color WhittedIntegrator::trace(const Ray& ray, int depth, const Color& weight, RNG& rng) const {
    Hit hit;
    if (!scene_.intersect(ray, &hit)) return scene_.envL;
    const IntegratorSettings& set = scene_.integrator;
    Vec3 wo = -ray.d;
    Color L(0);
    const Shape* sh = hit.shape;
    if (sh->areaLight) L += sh->areaLight->Le(hit.ng, wo);
    const Material& m = scene_.materials[sh->materialId];

    // Normals facing the viewer (two-sided shading).
    Vec3 ngF = faceForward(hit.ng, wo);
    Vec3 nsF = faceForward(hit.ns, ngF);
    // Trace a secondary ray scaled by factor k, unless its contribution is negligible.
    auto secondary = [&](const Vec3& dir, const Color& k) {
        Color w = weight * k;
        if (depth >= set.maxDepth || w.maxComponent() < kMinWeight) return Color(0);
        return k * trace(spawn(hit.p, ngF, dir), depth + 1, w, rng);
    };

    switch (m.type) {
        case MaterialType::Phong: {
            Color kd = m.diffuse(hit.uv);
            L += m.Ka * kd * set.ambient;  // ambient term: I_a * k_a * O_d
            Color kdTerm = m.physicalDiffuse ? kd * InvPi : kd;
            double specNorm = m.physicalDiffuse ? (m.exponent + 8) / (8 * Pi) : 1.0;
            auto shade = [&](const Vec3& wi, const Color& Li) {
                double cosI = dot(nsF, wi);
                if (cosI <= 0 || dot(ngF, wi) <= 0) return Color(0);
                Color c = kdTerm * cosI;
                if (!m.Ks.isBlack()) {
                    Vec3 h = normalize(wi + wo);
                    double nh = std::max(0.0, dot(nsF, h));
                    // Classic Blinn-Phong: ks (n.h)^s; normalised variant also weights by cos.
                    c += m.Ks * (std::pow(nh, m.exponent) * specNorm * (m.physicalDiffuse ? cosI : 1.0));
                }
                return c * Li;
            };
            for (const DeltaLight& l : scene_.deltaLights) {
                Vec3 wi;
                double dist;
                Color Li;
                l.illuminate(hit.p, &wi, &dist, &Li);
                if (Li.isBlack() || dot(ngF, wi) <= 0) continue;
                Color vis = visibility(hit.p, ngF, wi, std::isinf(dist), l.pos);
                if (!vis.isBlack()) L += shade(wi, Li * vis);
            }
            // Area lights act as point lights at a representative point (WSRT has hard shadows).
            for (const auto& al : scene_.areaLights) {
                Vec3 pl;
                Color I;
                if (al->sphere) {
                    const Sphere* s = static_cast<const Sphere*>(al->shapes[0]);
                    Vec3 c = s->centroid();
                    Vec3 toP = hit.p - c;
                    if (length(toP) <= s->worldRadius()) continue;  // inside the emitter
                    pl = c + normalize(toP) * s->worldRadius();
                    I = al->L * (al->totalArea / 4);  // projected area of a sphere = A / 4
                    Vec3 d = c - hit.p;
                    double d2 = lengthSquared(d);
                    Vec3 wi = d / std::sqrt(d2);
                    if (dot(ngF, wi) <= 0) continue;
                    Color vis = visibility(hit.p, ngF, wi, false, pl);
                    if (!vis.isBlack()) L += shade(wi, I / d2 * vis);
                } else {
                    pl = al->repPoint;
                    Vec3 d = pl - hit.p;
                    double d2 = lengthSquared(d);
                    if (d2 == 0) continue;
                    Vec3 wi = d / std::sqrt(d2);
                    double cosL = dot(al->repNormal, -wi);
                    if (!al->twoSided && cosL <= 0) continue;
                    I = al->L * (al->totalArea * std::fabs(cosL));
                    if (dot(ngF, wi) <= 0) continue;
                    Color vis = visibility(hit.p, ngF, wi, false, pl);
                    if (!vis.isBlack()) L += shade(wi, I / d2 * vis);
                }
            }
            if (!m.Kr.isBlack()) L += secondary(reflect(wo, nsF), m.Kr);
            break;
        }
        case MaterialType::Mirror:
            L += secondary(reflect(wo, nsF), m.Kr);
            break;
        case MaterialType::Dielectric: {
            // hit.ns keeps the surface's outward orientation: its sign tells entering vs exiting.
            double F = frDielectric(dot(wo, hit.ns), m.eta);
            L += secondary(reflect(wo, nsF), Color(F));
            Vec3 wt;
            double etap;
            if (F < 1 && refractDir(wo, hit.ns, m.eta, &etap, &wt))
                L += secondary(wt, m.Kt * ((1 - F) / (etap * etap)));
            break;
        }
        case MaterialType::Interface:
            L += secondary(ray.d, Color(1));
            break;
    }
    return L;
}

// ======================================================================= DRT
Color DistributedIntegrator::directLighting(const Hit& hit, const Vec3& wo, const Vec3& ns, const Vec3& ng,
                                            const Color& kd, const Material& m, RNG& rng) const {
    const IntegratorSettings& set = scene_.integrator;
    Vec3 r = reflect(wo, ns);
    Color L(0);
    for (const DeltaLight& l : scene_.deltaLights) {
        Vec3 wi;
        double dist;
        Color Li;
        l.illuminate(hit.p, &wi, &dist, &Li);
        double cosI = dot(ns, wi);
        if (Li.isBlack() || cosI <= 0 || dot(ng, wi) <= 0) continue;
        bool blocked = std::isinf(dist) ? occludedDir(hit.p, ng, wi) : occludedTo(hit.p, ng, l.pos);
        if (!blocked) L += phongBRDF(kd, m.Ks, m.exponent, r, wi) * Li * cosI;
    }
    for (const auto& al : scene_.areaLights) {
        if (al->shapes.size() == 1 && al->shapes[0] == hit.shape) continue;  // a light does not light itself
        // N shadow rays towards uniformly random points on the light (soft shadows).
        int n = al->nSamples > 0 ? al->nSamples : set.lightSamples;
        Color sum(0);
        for (int i = 0; i < n; ++i) {
            SurfaceSample s = al->sample(rng.uniform2());
            Vec3 d = s.p - hit.p;
            double d2 = lengthSquared(d);
            if (d2 == 0) continue;
            Vec3 wi = d / std::sqrt(d2);
            double cosI = dot(ns, wi);
            if (cosI <= 0 || dot(ng, wi) <= 0) continue;
            Color Le = al->Le(s.n, -wi);
            if (Le.isBlack()) continue;
            double cosL = absDot(s.n, wi);
            if (occludedTo(hit.p, ng, s.p)) continue;
            // Area-measure estimator: f Le cos(theta_i) cos(theta_l) / d^2 / pdf_A, pdf_A = 1 / A.
            sum += phongBRDF(kd, m.Ks, m.exponent, r, wi) * Le * (cosI * cosL / d2 * al->totalArea);
        }
        L += sum / (double)n;
    }
    return L;
}

Color DistributedIntegrator::trace(const Ray& ray, int depth, bool countEmission, RNG& rng) const {
    Hit hit;
    if (!scene_.intersect(ray, &hit)) return scene_.envL;
    const IntegratorSettings& set = scene_.integrator;
    Vec3 wo = -ray.d;
    Color L(0);
    const Shape* sh = hit.shape;
    // Emission is skipped after diffuse/glossy bounces: those already sampled the
    // lights explicitly (next-event estimation), counting it twice would be biased.
    if (sh->areaLight && countEmission) L += sh->areaLight->Le(hit.ng, wo);
    if (depth >= set.maxDepth) return L;
    const Material& m = scene_.materials[sh->materialId];
    Vec3 ngF = faceForward(hit.ng, wo);
    Vec3 nsF = faceForward(hit.ns, ngF);

    switch (m.type) {
        case MaterialType::Phong: {
            Color kd = m.diffuseConserving(hit.uv);
            L += directLighting(hit, wo, nsF, ngF, kd, m, rng);
            Vec3 r = reflect(wo, nsF);
            if (!kd.isBlack() || !m.Ks.isBlack()) {
                // Indirect light: one ray in a uniformly random hemisphere direction,
                // weighted by f * cos / pdf with pdf = 1 / (2 pi).
                Frame frame = Frame::fromZ(nsF);
                Vec3 wi = frame.fromLocal(sampleUniformHemisphere(rng.uniform2()));
                double cosI = dot(wi, nsF);
                if (cosI > 0 && dot(wi, ngF) > 0) {
                    Color f = phongBRDF(kd, m.Ks, m.exponent, r, wi);
                    if (!f.isBlack()) {
                        Color Li = trace(spawn(hit.p, ngF, wi), depth + 1, false, rng);
                        L += f * Li * (cosI / uniformHemispherePdf());
                    }
                }
            }
            if (!m.Kr.isBlack()) L += m.Kr * trace(spawn(hit.p, ngF, r), depth + 1, true, rng);
            break;
        }
        case MaterialType::Mirror:
            L += m.Kr * trace(spawn(hit.p, ngF, reflect(wo, nsF)), depth + 1, true, rng);
            break;
        case MaterialType::Dielectric: {
            double F = frDielectric(dot(wo, hit.ns), m.eta);
            // Choose reflection with probability F: the Fresnel weight and the
            // selection probability cancel, so each branch has weight 1.
            if (rng.uniform() < F) {
                L += trace(spawn(hit.p, ngF, reflect(wo, nsF)), depth + 1, true, rng);
            } else {
                Vec3 wt;
                double etap;
                if (refractDir(wo, hit.ns, m.eta, &etap, &wt))
                    L += m.Kt * trace(spawn(hit.p, ngF, wt), depth + 1, true, rng) / (etap * etap);
            }
            break;
        }
        case MaterialType::Interface:
            L += trace(spawn(hit.p, ngF, ray.d), depth + 1, countEmission, rng);
            break;
    }
    return L;
}

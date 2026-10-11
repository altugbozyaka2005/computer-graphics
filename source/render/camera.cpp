#include "camera.h"

#include "../core/sampling.h"

Camera::Camera(const CameraSettings& s, int xRes, int yRes) : s_(s), xRes_(xRes), yRes_(yRes) {
    double aspect = s.frameAspect > 0 ? s.frameAspect : (double)xRes / (double)yRes;
    if (s.hasScreenWindow) {
        for (int i = 0; i < 4; ++i) win_[i] = s.screenWindow[i];
    } else if (aspect > 1) {
        win_[0] = -aspect; win_[1] = aspect; win_[2] = -1; win_[3] = 1;
    } else {
        win_[0] = -1; win_[1] = 1; win_[2] = -1 / aspect; win_[3] = 1 / aspect;
    }
    tanHalf_ = std::tan(radians(s.fov) / 2);
}

Ray Camera::generateRay(Vec2 pFilm, Vec2 uLens) const {
    // Raster -> screen space (NDC y is flipped: raster y grows downwards).
    double sx = win_[0] + (pFilm.x / xRes_) * (win_[1] - win_[0]);
    double sy = win_[3] - (pFilm.y / yRes_) * (win_[3] - win_[2]);
    Vec3 o(0, 0, 0);
    Vec3 d = normalize(Vec3(sx * tanHalf_, sy * tanHalf_, 1));
    if (s_.lensRadius > 0) {
        // Thin lens: all rays through a film point converge on the plane of focus.
        Vec2 pl = sampleUniformDiskConcentric(uLens);
        Vec3 pLens(s_.lensRadius * pl.x, s_.lensRadius * pl.y, 0);
        double ft = s_.focalDistance / d.z;
        Vec3 pFocus = o + d * ft;
        d = normalize(pFocus - pLens);
        o = pLens;
    }
    return Ray(s_.worldFromCamera.point(o), normalize(s_.worldFromCamera.vector(d)));
}

// Perspective camera following pbrt-v4 Section 5.2 exactly (screen window,
// raster y-flip, fov on the shorter image axis, thin lens) so that framing
// matches pbrt pixel-for-pixel.
#pragma once

#include <string>

#include "../core/transform.h"
#include "../geometry/shape.h"

struct CameraSettings {
    std::string type = "perspective";
    double fov = 90;                   // degrees, along the shorter image axis
    double lensRadius = 0;
    double focalDistance = 1e6;
    bool hasScreenWindow = false;
    double screenWindow[4] = {-1, 1, -1, 1};  // xmin xmax ymin ymax
    double frameAspect = 0;                  // 0 = from resolution
    Transform worldFromCamera;
};

class Camera {
public:
    Camera(const CameraSettings& s, int xRes, int yRes);
    // pFilm in raster coordinates (x right, y down, continuous); uLens in [0,1)^2.
    Ray generateRay(Vec2 pFilm, Vec2 uLens) const;
    const CameraSettings& settings() const { return s_; }
    double screen(int i) const { return win_[i]; }

private:
    CameraSettings s_;
    int xRes_, yRes_;
    double win_[4];
    double tanHalf_;
};

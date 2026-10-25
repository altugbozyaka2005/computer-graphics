// Projective cameras following pbrt-v4 Section 5.2 exactly (screen window,
// raster y-flip, fov on the shorter image axis, thin lens) so that framing
// matches pbrt pixel-for-pixel.
//
//  perspective  : a camera-space point (x, y, z) projects to screen (x / (z tan(fov/2)), y / (z tan(fov/2))),
//                 so apparent size falls off as 1/z; all rays start at the eye.
//  orthographic : (x, y, z) projects to screen (x, y); depth is dropped, so apparent size does not
//                 depend on distance; rays are parallel to +z and start on the z = 0 plane.
#pragma once

#include <string>

#include "../core/transform.h"
#include "../geometry/shape.h"

struct CameraSettings {
    std::string type = "perspective";  // "perspective" | "orthographic"
    double fov = 90;                   // degrees, along the shorter image axis (perspective only)
    double lensRadius = 0;
    double focalDistance = 1e6;
    bool hasScreenWindow = false;
    double screenWindow[4] = {-1, 1, -1, 1};  // xmin xmax ymin ymax (orthographic: camera-space units)
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
    bool ortho_;
    int xRes_, yRes_;
    double win_[4];
    double tanHalf_;
};

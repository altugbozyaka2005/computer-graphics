#include "texture.h"

bool ImageTexture::texel(int x, int y, Color* c) const {
    int w = img_->width, h = img_->height;
    switch (wrap_) {
        case Wrap::Repeat:
            x = ((x % w) + w) % w;
            y = ((y % h) + h) % h;
            break;
        case Wrap::Clamp:
            x = std::min(std::max(x, 0), w - 1);
            y = std::min(std::max(y, 0), h - 1);
            break;
        case Wrap::Black:
            if (x < 0 || x >= w || y < 0 || y >= h) {
                *c = Color(0);
                return true;
            }
            break;
    }
    *c = img_->at(x, y);
    return true;
}

Color ImageTexture::eval(const Vec2& uv) const {
    Vec2 st = map_.map(uv);
    st.y = 1 - st.y;  // pbrt-v4 flips t so that v = 1 is the top row of the image
    Color v;
    if (nearest_) {
        int x = (int)std::floor(st.x * img_->width);
        int y = (int)std::floor(st.y * img_->height);
        texel(x, y, &v);
    } else {
        // Bilinear interpolation between the four nearest texel centres.
        double x = st.x * img_->width - 0.5, y = st.y * img_->height - 0.5;
        double fx = std::floor(x), fy = std::floor(y);
        int xi = (int)fx, yi = (int)fy;
        double dx = x - fx, dy = y - fy;
        Color c00, c10, c01, c11;
        texel(xi, yi, &c00);
        texel(xi + 1, yi, &c10);
        texel(xi, yi + 1, &c01);
        texel(xi + 1, yi + 1, &c11);
        v = c00 * ((1 - dx) * (1 - dy)) + c10 * (dx * (1 - dy)) + c01 * ((1 - dx) * dy) + c11 * (dx * dy);
    }
    v *= scale_;
    if (invert_) v = vmax(Color(1) - v, Color(0));
    return v;
}

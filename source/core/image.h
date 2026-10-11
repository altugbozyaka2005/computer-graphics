// Float RGB images, file I/O (PPM, PFM, PNG writer) and tone mapping.
#pragma once

#include <string>
#include <vector>

#include "math.h"

struct Image {
    int width = 0, height = 0;
    std::vector<Color> pixels;  // row-major, row 0 = top of the image
    Image() {}
    Image(int w, int h) : width(w), height(h), pixels((size_t)w * h) {}
    Color& at(int x, int y) { return pixels[(size_t)y * width + x]; }
    const Color& at(int x, int y) const { return pixels[(size_t)y * width + x]; }
};

double srgbEncode(double linear);  // linear [0,1] -> sRGB [0,1]
double srgbDecode(double encoded);

// All readers return values as stored in the file: PPM normalised to [0,1]
// (no colour decoding), PFM as linear floats. On failure err describes why.
bool readPPM(const std::string& path, Image* img, std::string* err);
bool readPFM(const std::string& path, Image* img, std::string* err);
// Dispatches on extension (.ppm/.pgm/.pfm).
bool readImage(const std::string& path, Image* img, bool* isLinear, std::string* err);

// Writers expect display-referred values in [0,1] (already encoded) for 8-bit
// formats and linear values for PFM.
bool writePPM(const std::string& path, const Image& img);
bool writePNG(const std::string& path, const Image& img);
bool writePFM(const std::string& path, const Image& img);

struct ToneMapSettings {
    std::string op = "none";        // "none" | "reinhard"
    std::string mode = "luminance"; // "luminance" | "rgb"
    double whitePoint = 0;          // <= 0 : use the maximum (scaled) luminance
    double key = 0;                 // > 0 : Reinhard photographic key (log-average scaling)
    double exposure = 1;
};

struct ToneMapReport {
    double logAverageLum = 0, maxLum = 0, usedWhite = 0, scale = 1;
};

// HDR linear -> display [0,1] sRGB-encoded image.
Image toneMapAndEncode(const Image& hdr, const ToneMapSettings& s, ToneMapReport* rep);

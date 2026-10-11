// Pixel sampling settings: random (jittered) samples inside each pixel.
#pragma once

struct SamplerSettings {
    int pixelSamples = 16;  // camera rays per pixel
    int seed = 0;
};

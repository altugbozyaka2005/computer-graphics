// PCG32 random number generator (as in pbrt-v4, Section B.2.7) and hashing helpers.
#pragma once

#include <cstdint>
#include "math.h"

inline uint64_t mixBits(uint64_t v) {
    v ^= (v >> 31);
    v *= 0x7fb5d329728ea185ULL;
    v ^= (v >> 27);
    v *= 0x81dadef4bc2dd44dULL;
    v ^= (v >> 33);
    return v;
}

inline uint64_t hashCombine(uint64_t a, uint64_t b) { return mixBits(a ^ (mixBits(b) + 0x9e3779b97f4a7c15ULL + (a << 6) + (a >> 2))); }

class RNG {
public:
    RNG() : state_(0x853c49e6748fea9bULL), inc_(0xda3e39cb94b95bdbULL) {}
    RNG(uint64_t seqIndex, uint64_t offset) { setSequence(seqIndex, offset); }

    void setSequence(uint64_t seqIndex, uint64_t offset) {
        state_ = 0u;
        inc_ = (seqIndex << 1u) | 1u;
        nextU32();
        state_ += offset;
        nextU32();
    }
    uint32_t nextU32() {
        uint64_t old = state_;
        state_ = old * 0x5851f42d4c957f2dULL + inc_;
        uint32_t xorshifted = (uint32_t)(((old >> 18u) ^ old) >> 27u);
        uint32_t rot = (uint32_t)(old >> 59u);
        return (xorshifted >> rot) | (xorshifted << ((~rot + 1u) & 31));
    }
    // Uniform double in [0, 1) with 53 bits of randomness.
    double uniform() {
        uint64_t hi = nextU32(), lo = nextU32();
        uint64_t bits = ((hi << 21) ^ lo) & ((1ULL << 53) - 1);
        return std::min(OneMinusEpsilon, bits * 0x1p-53);
    }
    Vec2 uniform2() { double a = uniform(); return {a, uniform()}; }

private:
    uint64_t state_, inc_;
};

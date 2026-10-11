// Basic vector maths used everywhere in the renderer (standard library only).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

constexpr double Pi = 3.14159265358979323846;
constexpr double InvPi = 1.0 / Pi;
constexpr double Inv2Pi = 0.5 / Pi;
constexpr double Inv4Pi = 0.25 / Pi;
constexpr double Infinity = std::numeric_limits<double>::infinity();
constexpr double OneMinusEpsilon = 0x1.fffffffffffffp-1;

inline double radians(double deg) { return deg * (Pi / 180.0); }
inline double degrees(double rad) { return rad * (180.0 / Pi); }
inline double clampd(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }
inline double lerp(double t, double a, double b) { return (1 - t) * a + t * b; }
inline double sqr(double v) { return v * v; }
inline double safeSqrt(double v) { return std::sqrt(std::max(0.0, v)); }
inline double safeAcos(double v) { return std::acos(clampd(v, -1.0, 1.0)); }

struct Vec2 {
    double x = 0, y = 0;
    constexpr Vec2() {}
    constexpr Vec2(double x_, double y_) : x(x_), y(y_) {}
    Vec2 operator+(const Vec2& o) const { return {x + o.x, y + o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x - o.x, y - o.y}; }
    Vec2 operator*(double s) const { return {x * s, y * s}; }
};

struct Vec3 {
    double x = 0, y = 0, z = 0;
    constexpr Vec3() {}
    constexpr Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
    explicit constexpr Vec3(double v) : x(v), y(v), z(v) {}

    double operator[](int i) const { return i == 0 ? x : (i == 1 ? y : z); }
    double& operator[](int i) { return i == 0 ? x : (i == 1 ? y : z); }

    Vec3 operator-() const { return {-x, -y, -z}; }
    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3& operator-=(const Vec3& o) { x -= o.x; y -= o.y; z -= o.z; return *this; }
    Vec3& operator*=(const Vec3& o) { x *= o.x; y *= o.y; z *= o.z; return *this; }
    Vec3& operator*=(double s) { x *= s; y *= s; z *= s; return *this; }
    Vec3& operator/=(double s) { double inv = 1.0 / s; x *= inv; y *= inv; z *= inv; return *this; }

    bool isBlack() const { return x == 0 && y == 0 && z == 0; }
    double maxComponent() const { return std::max(x, std::max(y, z)); }
    double minComponent() const { return std::min(x, std::min(y, z)); }
    double average() const { return (x + y + z) / 3.0; }
    bool hasNaN() const { return std::isnan(x) || std::isnan(y) || std::isnan(z); }
    bool isFinite() const { return std::isfinite(x) && std::isfinite(y) && std::isfinite(z); }
};

inline Vec3 operator+(const Vec3& a, const Vec3& b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(const Vec3& a, const Vec3& b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator*(const Vec3& a, const Vec3& b) { return {a.x * b.x, a.y * b.y, a.z * b.z}; }
inline Vec3 operator/(const Vec3& a, const Vec3& b) { return {a.x / b.x, a.y / b.y, a.z / b.z}; }
inline Vec3 operator*(const Vec3& a, double s) { return {a.x * s, a.y * s, a.z * s}; }
inline Vec3 operator*(double s, const Vec3& a) { return {a.x * s, a.y * s, a.z * s}; }
inline Vec3 operator/(const Vec3& a, double s) { double inv = 1.0 / s; return {a.x * inv, a.y * inv, a.z * inv}; }

inline double dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline double absDot(const Vec3& a, const Vec3& b) { return std::fabs(dot(a, b)); }
inline Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline double lengthSquared(const Vec3& v) { return dot(v, v); }
inline double length(const Vec3& v) { return std::sqrt(dot(v, v)); }
inline Vec3 normalize(const Vec3& v) {
    double l = length(v);
    return l > 0 ? v / l : v;
}
inline Vec3 vmin(const Vec3& a, const Vec3& b) { return {std::min(a.x, b.x), std::min(a.y, b.y), std::min(a.z, b.z)}; }
inline Vec3 vmax(const Vec3& a, const Vec3& b) { return {std::max(a.x, b.x), std::max(a.y, b.y), std::max(a.z, b.z)}; }
inline Vec3 vabs(const Vec3& a) { return {std::fabs(a.x), std::fabs(a.y), std::fabs(a.z)}; }
inline Vec3 vclamp(const Vec3& a, double lo, double hi) {
    return {clampd(a.x, lo, hi), clampd(a.y, lo, hi), clampd(a.z, lo, hi)};
}
// Flip n so that it lies in the same hemisphere as v.
inline Vec3 faceForward(const Vec3& n, const Vec3& v) { return dot(n, v) < 0 ? -n : n; }
// Mirror reflection of wo about n (pbrt convention: both point away from the surface).
inline Vec3 reflect(const Vec3& wo, const Vec3& n) { return -wo + 2 * dot(wo, n) * n; }

using Color = Vec3;
// Rec.709 / linear sRGB luminance weights.
inline double luminance(const Color& c) { return 0.2126 * c.x + 0.7152 * c.y + 0.0722 * c.z; }

// Orthonormal basis around a unit vector (Duff et al. 2017, as used in pbrt-v4).
inline void coordinateSystem(const Vec3& v1, Vec3* v2, Vec3* v3) {
    double sign = std::copysign(1.0, v1.z);
    double a = -1.0 / (sign + v1.z);
    double b = v1.x * v1.y * a;
    *v2 = Vec3(1 + sign * v1.x * v1.x * a, sign * b, -sign * v1.x);
    *v3 = Vec3(b, sign + v1.y * v1.y * a, -v1.y);
}

struct Frame {
    Vec3 s, t, n;
    static Frame fromZ(const Vec3& n) {
        Frame f;
        f.n = n;
        coordinateSystem(n, &f.s, &f.t);
        return f;
    }
    Vec3 toLocal(const Vec3& v) const { return {dot(v, s), dot(v, t), dot(v, n)}; }
    Vec3 fromLocal(const Vec3& v) const { return s * v.x + t * v.y + n * v.z; }
};

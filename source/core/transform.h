// 4x4 matrices and affine transforms (pbrt-v4 conventions, Sections 3.9-3.10).
#pragma once

#include "math.h"

struct Mat4 {
    double m[4][4];
    Mat4() {
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j) m[i][j] = (i == j) ? 1.0 : 0.0;
    }
    static Mat4 fromRowMajor(const double v[16]) {
        Mat4 r;
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j) r.m[i][j] = v[i * 4 + j];
        return r;
    }
    Mat4 operator*(const Mat4& o) const {
        Mat4 r;
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j) {
                double s = 0;
                for (int k = 0; k < 4; ++k) s += m[i][k] * o.m[k][j];
                r.m[i][j] = s;
            }
        return r;
    }
    Mat4 transpose() const {
        Mat4 r;
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j) r.m[i][j] = m[j][i];
        return r;
    }
    bool isIdentity() const {
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j)
                if (m[i][j] != ((i == j) ? 1.0 : 0.0)) return false;
        return true;
    }
    // Gauss-Jordan elimination with partial pivoting. Returns false if singular.
    bool inverse(Mat4* out) const;
};

class Transform {
public:
    Transform() {}
    explicit Transform(const Mat4& m) : m_(m) { valid_ = m.inverse(&inv_); }
    Transform(const Mat4& m, const Mat4& inv) : m_(m), inv_(inv) {}

    const Mat4& matrix() const { return m_; }
    const Mat4& inverseMatrix() const { return inv_; }
    bool valid() const { return valid_; }
    Transform inverse() const { return Transform(inv_, m_); }
    bool isIdentity() const { return m_.isIdentity(); }

    Transform operator*(const Transform& t) const { return Transform(m_ * t.m_, t.inv_ * inv_); }

    Vec3 point(const Vec3& p) const {
        double x = m_.m[0][0] * p.x + m_.m[0][1] * p.y + m_.m[0][2] * p.z + m_.m[0][3];
        double y = m_.m[1][0] * p.x + m_.m[1][1] * p.y + m_.m[1][2] * p.z + m_.m[1][3];
        double z = m_.m[2][0] * p.x + m_.m[2][1] * p.y + m_.m[2][2] * p.z + m_.m[2][3];
        double w = m_.m[3][0] * p.x + m_.m[3][1] * p.y + m_.m[3][2] * p.z + m_.m[3][3];
        return (w == 1.0) ? Vec3(x, y, z) : Vec3(x, y, z) / w;
    }
    Vec3 vector(const Vec3& v) const {
        return {m_.m[0][0] * v.x + m_.m[0][1] * v.y + m_.m[0][2] * v.z,
                m_.m[1][0] * v.x + m_.m[1][1] * v.y + m_.m[1][2] * v.z,
                m_.m[2][0] * v.x + m_.m[2][1] * v.y + m_.m[2][2] * v.z};
    }
    // Normals transform by the inverse transpose.
    Vec3 normal(const Vec3& n) const {
        return {inv_.m[0][0] * n.x + inv_.m[1][0] * n.y + inv_.m[2][0] * n.z,
                inv_.m[0][1] * n.x + inv_.m[1][1] * n.y + inv_.m[2][1] * n.z,
                inv_.m[0][2] * n.x + inv_.m[1][2] * n.y + inv_.m[2][2] * n.z};
    }
    // Determinant of the upper-left 3x3: negative means handedness is swapped.
    double det3() const {
        const auto& a = m_.m;
        return a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) -
               a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) +
               a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]);
    }
    bool swapsHandedness() const { return det3() < 0; }

private:
    Mat4 m_, inv_;
    bool valid_ = true;
};

Transform translate(const Vec3& d);
Transform scale(double x, double y, double z);
// Rotation by theta degrees about an arbitrary axis (pbrt Rotate).
Transform rotate(double thetaDeg, const Vec3& axis);
// pbrt LookAt: returns cameraFromWorld. ok=false if up is parallel to view dir.
Transform lookAt(const Vec3& pos, const Vec3& look, const Vec3& up, bool* ok);
// pbrt "Transform"/"ConcatTransform" take 16 numbers in column-major order.
Transform fromPbrtMatrix(const double v[16]);

#include "transform.h"

bool Mat4::inverse(Mat4* out) const {
    double a[4][8];
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            a[i][j] = m[i][j];
            a[i][j + 4] = (i == j) ? 1.0 : 0.0;
        }
    for (int col = 0; col < 4; ++col) {
        int pivot = col;
        for (int r = col + 1; r < 4; ++r)
            if (std::fabs(a[r][col]) > std::fabs(a[pivot][col])) pivot = r;
        if (std::fabs(a[pivot][col]) < 1e-300) return false;
        if (pivot != col)
            for (int j = 0; j < 8; ++j) std::swap(a[col][j], a[pivot][j]);
        double inv = 1.0 / a[col][col];
        for (int j = 0; j < 8; ++j) a[col][j] *= inv;
        for (int r = 0; r < 4; ++r) {
            if (r == col) continue;
            double f = a[r][col];
            if (f == 0) continue;
            for (int j = 0; j < 8; ++j) a[r][j] -= f * a[col][j];
        }
    }
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            if (!std::isfinite(a[i][j + 4])) return false;
            out->m[i][j] = a[i][j + 4];
        }
    return true;
}

Transform translate(const Vec3& d) {
    Mat4 m, inv;
    m.m[0][3] = d.x; m.m[1][3] = d.y; m.m[2][3] = d.z;
    inv.m[0][3] = -d.x; inv.m[1][3] = -d.y; inv.m[2][3] = -d.z;
    return Transform(m, inv);
}

Transform scale(double x, double y, double z) {
    Mat4 m;
    m.m[0][0] = x; m.m[1][1] = y; m.m[2][2] = z;
    return Transform(m);  // inverse computed (fails cleanly for a zero scale)
}

Transform rotate(double thetaDeg, const Vec3& axis) {
    Vec3 a = normalize(axis);
    double s = std::sin(radians(thetaDeg)), c = std::cos(radians(thetaDeg));
    Mat4 m;
    m.m[0][0] = a.x * a.x + (1 - a.x * a.x) * c;
    m.m[0][1] = a.x * a.y * (1 - c) - a.z * s;
    m.m[0][2] = a.x * a.z * (1 - c) + a.y * s;
    m.m[1][0] = a.x * a.y * (1 - c) + a.z * s;
    m.m[1][1] = a.y * a.y + (1 - a.y * a.y) * c;
    m.m[1][2] = a.y * a.z * (1 - c) - a.x * s;
    m.m[2][0] = a.x * a.z * (1 - c) - a.y * s;
    m.m[2][1] = a.y * a.z * (1 - c) + a.x * s;
    m.m[2][2] = a.z * a.z + (1 - a.z * a.z) * c;
    return Transform(m, m.transpose());
}

Transform lookAt(const Vec3& pos, const Vec3& look, const Vec3& up, bool* ok) {
    Mat4 worldFromCamera;
    worldFromCamera.m[0][3] = pos.x;
    worldFromCamera.m[1][3] = pos.y;
    worldFromCamera.m[2][3] = pos.z;
    Vec3 dir = normalize(look - pos);
    Vec3 upn = normalize(up);
    Vec3 rightRaw = cross(upn, dir);
    *ok = length(dir) > 0 && length(rightRaw) > 1e-12;
    if (!*ok) return Transform();
    Vec3 right = normalize(rightRaw);
    Vec3 newUp = cross(dir, right);
    worldFromCamera.m[0][0] = right.x; worldFromCamera.m[1][0] = right.y; worldFromCamera.m[2][0] = right.z;
    worldFromCamera.m[0][1] = newUp.x; worldFromCamera.m[1][1] = newUp.y; worldFromCamera.m[2][1] = newUp.z;
    worldFromCamera.m[0][2] = dir.x;   worldFromCamera.m[1][2] = dir.y;   worldFromCamera.m[2][2] = dir.z;
    Mat4 cameraFromWorld;
    worldFromCamera.inverse(&cameraFromWorld);
    return Transform(cameraFromWorld, worldFromCamera);
}

Transform fromPbrtMatrix(const double v[16]) {
    return Transform(Mat4::fromRowMajor(v).transpose());
}

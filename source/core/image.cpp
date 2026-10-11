#include "image.h"

#include <cctype>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <sstream>

double srgbEncode(double v) {
    if (v <= 0.0031308) return 12.92 * v;
    return 1.055 * std::pow(v, 1.0 / 2.4) - 0.055;
}

double srgbDecode(double v) {
    if (v <= 0.04045) return v / 12.92;
    return std::pow((v + 0.055) / 1.055, 2.4);
}

static std::string lowerExt(const std::string& path) {
    size_t dot = path.find_last_of('.');
    if (dot == std::string::npos) return "";
    std::string e = path.substr(dot);
    for (auto& c : e) c = (char)std::tolower((unsigned char)c);
    return e;
}

// ---------------------------------------------------------------- PPM / PGM
namespace {
struct PnmReader {
    std::vector<unsigned char> data;
    size_t pos = 0;
    void skipWsAndComments() {
        while (pos < data.size()) {
            if (data[pos] == '#') {
                while (pos < data.size() && data[pos] != '\n') ++pos;
            } else if (std::isspace(data[pos])) {
                ++pos;
            } else {
                break;
            }
        }
    }
    bool readInt(long* v) {
        skipWsAndComments();
        if (pos >= data.size() || !std::isdigit(data[pos])) return false;
        long r = 0;
        while (pos < data.size() && std::isdigit(data[pos])) {
            r = r * 10 + (data[pos] - '0');
            if (r > 100000000) return false;
            ++pos;
        }
        *v = r;
        return true;
    }
};
}  // namespace

bool readPPM(const std::string& path, Image* img, std::string* err) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { *err = "cannot open file '" + path + "'"; return false; }
    PnmReader r;
    r.data.assign(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
    if (r.data.size() < 2 || r.data[0] != 'P') { *err = "not a PPM/PGM file (bad magic number)"; return false; }
    char kind = (char)r.data[1];
    if (kind != '3' && kind != '6' && kind != '2' && kind != '5') {
        *err = std::string("unsupported PNM variant P") + kind + " (supported: P2, P3, P5, P6)";
        return false;
    }
    r.pos = 2;
    long w, h, maxv;
    if (!r.readInt(&w) || !r.readInt(&h) || !r.readInt(&maxv)) { *err = "malformed PPM header"; return false; }
    if (w <= 0 || h <= 0 || w > 65536 || h > 65536) { *err = "invalid PPM dimensions"; return false; }
    if (maxv <= 0 || maxv > 65535) { *err = "invalid PPM maxval"; return false; }
    int channels = (kind == '3' || kind == '6') ? 3 : 1;
    *img = Image((int)w, (int)h);
    size_t n = (size_t)w * h * channels;
    std::vector<double> vals(n);
    if (kind == '3' || kind == '2') {
        for (size_t i = 0; i < n; ++i) {
            long v;
            if (!r.readInt(&v)) { *err = "PPM ended early or contains invalid data"; return false; }
            vals[i] = (double)std::min(v, maxv) / maxv;
        }
    } else {
        ++r.pos;  // exactly one whitespace byte after maxval
        size_t bpc = maxv < 256 ? 1 : 2;
        if (r.pos + n * bpc > r.data.size()) { *err = "PPM ended early (truncated binary data)"; return false; }
        for (size_t i = 0; i < n; ++i) {
            unsigned v = bpc == 1 ? r.data[r.pos + i]
                                  : (unsigned)(r.data[r.pos + 2 * i] << 8 | r.data[r.pos + 2 * i + 1]);
            vals[i] = (double)std::min<unsigned>(v, (unsigned)maxv) / maxv;
        }
    }
    for (size_t p = 0; p < (size_t)w * h; ++p) {
        if (channels == 3) img->pixels[p] = Color(vals[3 * p], vals[3 * p + 1], vals[3 * p + 2]);
        else img->pixels[p] = Color(vals[p]);
    }
    return true;
}

bool writePPM(const std::string& path, const Image& img) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    f << "P6\n" << img.width << " " << img.height << "\n255\n";
    std::vector<unsigned char> buf((size_t)img.width * img.height * 3);
    for (size_t i = 0; i < img.pixels.size(); ++i)
        for (int c = 0; c < 3; ++c)
            buf[3 * i + c] = (unsigned char)std::lround(clampd(img.pixels[i][c], 0, 1) * 255.0);
    f.write((const char*)buf.data(), (std::streamsize)buf.size());
    return (bool)f;
}

// ---------------------------------------------------------------- PFM
bool readPFM(const std::string& path, Image* img, std::string* err) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { *err = "cannot open file '" + path + "'"; return false; }
    std::string magic;
    f >> magic;
    int channels = magic == "PF" ? 3 : (magic == "Pf" ? 1 : 0);
    if (!channels) { *err = "not a PFM file (bad magic)"; return false; }
    long w, h;
    double sc;
    if (!(f >> w >> h >> sc)) { *err = "malformed PFM header"; return false; }
    if (w <= 0 || h <= 0 || w > 65536 || h > 65536) { *err = "invalid PFM dimensions"; return false; }
    f.get();  // single whitespace character
    bool littleEndian = sc < 0;
    uint16_t probe = 1;
    bool hostLittle = *(unsigned char*)&probe == 1;
    *img = Image((int)w, (int)h);
    std::vector<float> row((size_t)w * channels);
    for (long y = 0; y < h; ++y) {
        f.read((char*)row.data(), (std::streamsize)(row.size() * sizeof(float)));
        if (!f) { *err = "PFM ended early (truncated data)"; return false; }
        if (littleEndian != hostLittle) {
            for (auto& v : row) {
                unsigned char* b = (unsigned char*)&v;
                std::swap(b[0], b[3]);
                std::swap(b[1], b[2]);
            }
        }
        long outY = h - 1 - y;  // PFM stores rows bottom-to-top
        for (long x = 0; x < w; ++x) {
            Color c = channels == 3 ? Color(row[3 * x], row[3 * x + 1], row[3 * x + 2]) : Color(row[x]);
            img->at((int)x, (int)outY) = c;  // |scale| is conventionally 1; only its sign matters
        }
    }
    return true;
}

bool writePFM(const std::string& path, const Image& img) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    uint16_t probe = 1;
    bool hostLittle = *(unsigned char*)&probe == 1;
    f << "PF\n" << img.width << " " << img.height << "\n" << (hostLittle ? "-1.0" : "1.0") << "\n";
    std::vector<float> row((size_t)img.width * 3);
    for (int y = img.height - 1; y >= 0; --y) {
        for (int x = 0; x < img.width; ++x)
            for (int c = 0; c < 3; ++c) row[3 * x + c] = (float)img.at(x, y)[c];
        f.write((const char*)row.data(), (std::streamsize)(row.size() * sizeof(float)));
    }
    return (bool)f;
}

bool readImage(const std::string& path, Image* img, bool* isLinear, std::string* err) {
    std::string ext = lowerExt(path);
    if (ext == ".pfm") { *isLinear = true; return readPFM(path, img, err); }
    if (ext == ".ppm" || ext == ".pgm" || ext == ".pnm") { *isLinear = false; return readPPM(path, img, err); }
    *err = "unsupported image format '" + ext + "' (supported: .ppm, .pgm, .pfm)";
    return false;
}

// ---------------------------------------------------------------- PNG (uncompressed deflate)
namespace {
uint32_t crcTable[256];
bool crcInit = false;
void initCrc() {
    for (uint32_t n = 0; n < 256; ++n) {
        uint32_t c = n;
        for (int k = 0; k < 8; ++k) c = (c & 1) ? 0xedb88320u ^ (c >> 1) : c >> 1;
        crcTable[n] = c;
    }
    crcInit = true;
}
uint32_t crc32(const unsigned char* buf, size_t len, uint32_t crc = 0xffffffffu) {
    for (size_t i = 0; i < len; ++i) crc = crcTable[(crc ^ buf[i]) & 0xff] ^ (crc >> 8);
    return crc;
}
void put32(std::vector<unsigned char>& v, uint32_t x) {
    v.push_back((unsigned char)(x >> 24)); v.push_back((unsigned char)(x >> 16));
    v.push_back((unsigned char)(x >> 8));  v.push_back((unsigned char)x);
}
void writeChunk(std::ofstream& f, const char* type, const std::vector<unsigned char>& data) {
    std::vector<unsigned char> buf;
    put32(buf, (uint32_t)data.size());
    buf.insert(buf.end(), type, type + 4);
    buf.insert(buf.end(), data.begin(), data.end());
    uint32_t crc = crc32(buf.data() + 4, buf.size() - 4) ^ 0xffffffffu;
    put32(buf, crc);
    f.write((const char*)buf.data(), (std::streamsize)buf.size());
}
}  // namespace

bool writePNG(const std::string& path, const Image& img) {
    if (!crcInit) initCrc();
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    const unsigned char sig[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    f.write((const char*)sig, 8);

    std::vector<unsigned char> ihdr;
    put32(ihdr, (uint32_t)img.width);
    put32(ihdr, (uint32_t)img.height);
    ihdr.push_back(8);  // bit depth
    ihdr.push_back(2);  // colour type: truecolour RGB
    ihdr.push_back(0); ihdr.push_back(0); ihdr.push_back(0);
    writeChunk(f, "IHDR", ihdr);

    // Raw scanlines, each prefixed with filter type 0.
    std::vector<unsigned char> raw;
    raw.reserve((size_t)img.height * (img.width * 3 + 1));
    for (int y = 0; y < img.height; ++y) {
        raw.push_back(0);
        for (int x = 0; x < img.width; ++x)
            for (int c = 0; c < 3; ++c)
                raw.push_back((unsigned char)std::lround(clampd(img.at(x, y)[c], 0, 1) * 255.0));
    }
    // zlib stream made of "stored" (uncompressed) deflate blocks.
    std::vector<unsigned char> z;
    z.push_back(0x78);
    z.push_back(0x01);
    size_t pos = 0;
    do {
        size_t len = std::min<size_t>(65535, raw.size() - pos);
        bool last = pos + len == raw.size();
        z.push_back(last ? 1 : 0);
        z.push_back((unsigned char)(len & 0xff));
        z.push_back((unsigned char)(len >> 8));
        z.push_back((unsigned char)(~len & 0xff));
        z.push_back((unsigned char)((~len >> 8) & 0xff));
        z.insert(z.end(), raw.begin() + (long)pos, raw.begin() + (long)(pos + len));
        pos += len;
    } while (pos < raw.size());
    uint32_t a = 1, b = 0;
    for (unsigned char c : raw) {
        a = (a + c) % 65521;
        b = (b + a) % 65521;
    }
    put32(z, (b << 16) | a);
    writeChunk(f, "IDAT", z);
    writeChunk(f, "IEND", {});
    return (bool)f;
}

// ---------------------------------------------------------------- tone mapping
Image toneMapAndEncode(const Image& hdr, const ToneMapSettings& s, ToneMapReport* rep) {
    Image out(hdr.width, hdr.height);
    double scale = s.exposure;
    double sumLog = 0, maxLum = 0;
    size_t n = hdr.pixels.size();
    const double delta = 1e-6;
    for (const auto& c : hdr.pixels) {
        double L = std::max(0.0, luminance(c));
        sumLog += std::log(delta + L);
        maxLum = std::max(maxLum, L);
    }
    double logAvg = n ? std::exp(sumLog / (double)n) : 0;
    if (s.op == "reinhard" && s.key > 0 && logAvg > 0) scale *= s.key / logAvg;
    double white = s.whitePoint > 0 ? s.whitePoint : maxLum * scale;
    if (white <= 0) white = 1;
    double invW2 = 1.0 / (white * white);
    for (size_t i = 0; i < n; ++i) {
        Color c = vmax(hdr.pixels[i] * scale, Color(0));
        Color d;
        if (s.op == "reinhard") {
            if (s.mode == "rgb") {
                for (int k = 0; k < 3; ++k) d[k] = c[k] * (1 + c[k] * invW2) / (1 + c[k]);
            } else {
                double L = luminance(c);
                double Ld = L * (1 + L * invW2) / (1 + L);
                d = L > 0 ? c * (Ld / L) : Color(0);
            }
        } else {
            d = c;
        }
        for (int k = 0; k < 3; ++k) d[k] = srgbEncode(clampd(d[k], 0, 1));
        out.pixels[i] = d;
    }
    if (rep) {
        rep->logAverageLum = logAvg;
        rep->maxLum = maxLum;
        rep->usedWhite = white;
        rep->scale = scale;
    }
    return out;
}

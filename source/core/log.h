// Logging (to a .log file next to every output image) and profiling helpers.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

struct FileLoc {
    std::string file;
    int line = 0, column = 0;
    std::string str() const {
        if (file.empty()) return "";
        return file + ":" + std::to_string(line) + ":" + std::to_string(column);
    }
};

class Logger {
public:
    static Logger& get();

    // Messages are buffered until the log file is opened (its name depends on
    // the Film filename found while parsing), then written immediately.
    bool openFile(const std::string& path);
    void close();

    void info(const std::string& msg);
    void warning(const std::string& msg, const FileLoc& loc = FileLoc());
    void error(const std::string& msg, const FileLoc& loc = FileLoc());
    void raw(const std::string& line);

    int warningCount() const { return warnings_; }
    int errorCount() const { return errors_; }
    void setEcho(bool quiet) { quiet_ = quiet; }
    const std::string& path() const { return path_; }

private:
    void emit(const std::string& line, bool toStderr);
    std::mutex mutex_;
    std::ofstream file_;
    std::string path_;
    std::vector<std::string> pending_;
    std::atomic<int> warnings_{0}, errors_{0};
    bool quiet_ = false;
};

inline Logger& LOG() { return Logger::get(); }

class Timer {
public:
    Timer() : start_(std::chrono::steady_clock::now()) {}
    void reset() { start_ = std::chrono::steady_clock::now(); }
    double seconds() const {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    }

private:
    std::chrono::steady_clock::time_point start_;
};

// Per-thread ray statistics, merged into a global total when a thread finishes.
struct RayStats {
    static constexpr int kDepths = 65;  // depths 0..64 (maxdepth is at most 64)
    uint64_t cameraRays = 0, shadowRays = 0, secondaryRays = 0;
    uint64_t primTests = 0;
    uint64_t nanSamples = 0;
    uint64_t depthRays[kDepths] = {};  // rays traced at each depth of the ray tree (0 = camera rays)
    void add(const RayStats& o) {
        cameraRays += o.cameraRays; shadowRays += o.shadowRays; secondaryRays += o.secondaryRays;
        primTests += o.primTests; nanSamples += o.nanSamples;
        for (int i = 0; i < kDepths; ++i) depthRays[i] += o.depthRays[i];
    }
};
extern thread_local RayStats tlsStats;

#include "log.h"

#include <iostream>

thread_local RayStats tlsStats;

Logger& Logger::get() {
    static Logger logger;
    return logger;
}

bool Logger::openFile(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (file_.is_open()) file_.close();
    file_.open(path, std::ios::out | std::ios::trunc);
    if (!file_) {
        std::cerr << "[ERROR] cannot open log file '" << path << "'\n";
        return false;
    }
    path_ = path;
    for (const auto& l : pending_) file_ << l << '\n';
    pending_.clear();
    file_.flush();
    return true;
}

void Logger::close() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (file_.is_open()) file_.close();
}

void Logger::emit(const std::string& line, bool toStderr) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (file_.is_open()) {
        file_ << line << '\n';
        file_.flush();
    } else {
        pending_.push_back(line);
    }
    if (toStderr) std::cerr << line << '\n';
    else if (!quiet_) std::cout << line << '\n';
}

void Logger::info(const std::string& msg) { emit("[INFO] " + msg, false); }

void Logger::warning(const std::string& msg, const FileLoc& loc) {
    ++warnings_;
    std::string where = loc.str();
    emit("[WARNING] " + (where.empty() ? "" : where + ": ") + msg, !quiet_);
}

void Logger::error(const std::string& msg, const FileLoc& loc) {
    ++errors_;
    std::string where = loc.str();
    emit("[ERROR] " + (where.empty() ? "" : where + ": ") + msg, true);
}

void Logger::raw(const std::string& line) { emit(line, false); }

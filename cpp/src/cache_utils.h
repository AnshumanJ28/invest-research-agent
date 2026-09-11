#pragma once
#include <string>
#include <fstream>
#include <filesystem>
#include <chrono>
#include <iostream>
namespace fs = std::filesystem;
namespace cache {
    constexpr int DEFAULT_TTL_SECONDS = 86400; 
    inline std::string cache_dir(const std::string& ticker) {
        std::string dir = "cache/" + ticker;
        fs::create_directories(dir);
        return dir;
    }
    inline std::string cache_path(const std::string& ticker, const std::string& key) {
        return cache_dir(ticker) + "/" + key + ".json";
    }
    inline bool is_cache_valid(const std::string& path, int ttl_seconds = DEFAULT_TTL_SECONDS) {
        if (!fs::exists(path)) return false;
        auto last_write = fs::last_write_time(path);
        auto now = fs::file_time_type::clock::now();
        auto age = std::chrono::duration_cast<std::chrono::seconds>(now - last_write).count();
        return age < ttl_seconds;
    }
    inline std::string read_cache(const std::string& path) {
        std::ifstream f(path);
        if (!f.is_open()) return "";
        std::string content((std::istreambuf_iterator<char>(f)),
                             std::istreambuf_iterator<char>());
        return content;
    }
    inline void write_cache(const std::string& path, const std::string& content) {
        fs::path p(path);
        if (p.has_parent_path()) {
            fs::create_directories(p.parent_path());
        }
        std::ofstream f(path);
        if (f.is_open()) {
            f << content;
        }
    }
    inline bool has_valid_unified_cache(const std::string& ticker, int ttl_seconds = DEFAULT_TTL_SECONDS) {
        return is_cache_valid(cache_path(ticker, "unified_fetch"), ttl_seconds);
    }
} 

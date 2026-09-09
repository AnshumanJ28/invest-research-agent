#include "edgar_agent.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <cstdlib>
#include <thread>
#include <chrono>

using json = nlohmann::json;

std::map<std::string, EdgarDocument> EdgarAgent::fetch_latest_filings(const std::string& ticker) {
    std::map<std::string, EdgarDocument> docs;

    std::string out_path = "json/edgar_temp.json";
    std::string cmd = "python python/ingestion/edgar_json.py " + ticker + " > " + out_path;
    
    // Exponential backoff for API rate limits (SEC allows max 10 requests/sec)
    int ret = -1;
    int max_retries = 3;
    int base_wait_ms = 1000;
    
    for (int attempt = 0; attempt < max_retries; ++attempt) {
        ret = std::system(cmd.c_str());
        if (ret == 0) break;
        
        std::cerr << "  [WARN] Python edgar script failed (attempt " << (attempt + 1) << "/" << max_retries << "). Retrying..." << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(base_wait_ms * (1 << attempt)));
    }
    
    if (ret != 0) {
        std::cerr << "[ERROR] Circuit breaker tripped. Failed to execute Python edgar script after retries." << std::endl;
        return docs;
    }

    std::ifstream file(out_path);
    if (!file.is_open()) {
        std::cerr << "[ERROR] Could not read output from Python edgar script." << std::endl;
        return docs;
    }

    try {
        json j;
        file >> j;
        
        if (j.is_object() && j.contains("error")) {
            std::cerr << "[ERROR] Python edgar script returned error: " << j["error"] << std::endl;
            return docs;
        }

        if (j.is_object()) {
            for (auto& el : j.items()) {
                if (el.value().is_null()) continue;
                
                EdgarDocument ed;
                ed.filed_date = el.value().value("filed_date", "");
                
                if (el.value().contains("sections") && el.value()["sections"].is_array()) {
                    for (const auto& sec : el.value()["sections"]) {
                        EdgarSection s;
                        s.name = sec.value("name", "");
                        s.text = sec.value("text", "");
                        ed.sections.push_back(s);
                    }
                }
                docs[el.key()] = ed;
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse edgar JSON: " << e.what() << std::endl;
    }

    std::remove(out_path.c_str());
    return docs;
}

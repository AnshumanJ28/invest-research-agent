#include "edgar_agent.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <cstdlib>

using json = nlohmann::json;

std::map<std::string, EdgarDocument> EdgarAgent::fetch_latest_filings(const std::string& ticker) {
    std::map<std::string, EdgarDocument> docs;

    std::string cmd = "python ../ingestion/edgar_json.py " + ticker + " > edgar_temp.json";
    int ret = std::system(cmd.c_str());
    
    if (ret != 0) {
        std::cerr << "[ERROR] Failed to execute Python edgar script." << std::endl;
        return docs;
    }

    std::ifstream file("edgar_temp.json");
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

    std::remove("edgar_temp.json");
    return docs;
}

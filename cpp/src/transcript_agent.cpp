#include "transcript_agent.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <cstdlib>

using json = nlohmann::json;

TranscriptDocument TranscriptAgent::fetch_transcript(const std::string& ticker) {
    TranscriptDocument doc;
    doc.available = false;

    std::string out_path = "json/transcript_temp.json";
    std::string cmd = "python python/ingestion/transcript_json.py " + ticker + " > " + out_path;
    int ret = std::system(cmd.c_str());
    
    if (ret != 0) {
        std::cerr << "[ERROR] Failed to execute Python transcript script." << std::endl;
        return doc;
    }

    std::ifstream file(out_path);
    if (!file.is_open()) {
        std::cerr << "[ERROR] Could not read output from Python transcript script." << std::endl;
        return doc;
    }

    try {
        json j;
        file >> j;
        
        if (j.is_object() && j.contains("error")) {
            std::cerr << "[ERROR] Python transcript script returned error: " << j["error"] << std::endl;
            return doc;
        }

        if (j.is_object()) {
            doc.available = j.value("available", false);
            doc.unavailable_reason = j.value("unavailable_reason", "");

            if (j.contains("utterances") && j["utterances"].is_array()) {
                for (const auto& u : j["utterances"]) {
                    TranscriptUtterance tu;
                    tu.speaker = u.value("speaker", "");
                    tu.text = u.value("text", "");
                    tu.section = u.value("section", "");
                    doc.utterances.push_back(tu);
                }
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse transcript JSON: " << e.what() << std::endl;
    }

    std::remove(out_path.c_str());
    return doc;
}

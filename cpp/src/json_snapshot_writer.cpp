#include "json_snapshot_writer.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <cmath>
#include <vector>
#include <sqlite3.h>
#include <nlohmann/json.hpp>
using json = nlohmann::json;
static std::string fmt_double(double val, int precision = 4) {
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(precision) << val;
    return ss.str();
}
static std::string fmt_metric(const std::string& name, double val) {
    if (name.find("margin") != std::string::npos ||
        name.find("roe") != std::string::npos ||
        name.find("roa") != std::string::npos ||
        name.find("growth") != std::string::npos ||
        name.find("percent") != std::string::npos) {
        return fmt_double(val * 100.0, 2) + "%";
    } else if (name.find("dividend") != std::string::npos) {
        double pct = (val > 0.5) ? val : (val * 100.0);
        return fmt_double(pct, 2) + "%";
    } else if (name == "enterprise_value" || name == "market_cap") {
        if (val >= 1e12) return "₹" + fmt_double(val / 1e12, 2) + "T";
        if (val >= 1e9)  return "₹" + fmt_double(val / 1e9, 2)  + "B";
        if (val >= 1e6)  return "₹" + fmt_double(val / 1e6, 2)  + "M";
        return "₹" + fmt_double(val, 2);
    } else if (name == "current_price" || name == "target_price" ||
               name == "52_week_high"  || name == "52_week_low") {
        return "₹" + fmt_double(val, 2);
    } else if (name == "beta") {
        if (std::abs(val) < 0.005) return "0.00";
        return fmt_double(val, 2);
    } else {
        return fmt_double(val, 2) + "x";
    }
}
static std::string prettify_name(std::string name) {
    for (char& c : name) { if (c == '_') c = ' '; }
    bool cap = true;
    for (char& c : name) {
        if (std::isspace(static_cast<unsigned char>(c))) {
            cap = true;
        } else if (cap) {
            c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
            cap = false;
        }
    }
    return name;
}
std::string JsonSnapshotWriter::generate_snapshot(const std::string& ticker,
                                                   const std::string& generation_id,
                                                   const std::string& db_path,
                                                   const std::string& output_dir) {
    sqlite3* db;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "[JsonSnapshot] Failed to open DB: " << db_path << "\n";
        return "";
    }
    std::string base_name = ticker + "_" + generation_id;
    std::string json_filename = base_name + ".json";
    std::string pdf_filename  = base_name + ".pdf";
    std::string json_path = output_dir + "/" + json_filename;
    std::string pdf_path  = output_dir + "/" + pdf_filename;
    json snapshot;
    snapshot["generation_id"] = generation_id;
    snapshot["ticker"]        = ticker;
    snapshot["pdf_path"]      = "reports/" + pdf_filename;
    {
        std::string q = "SELECT composite_score, conviction_label FROM investment_assessment WHERE ticker = '" + ticker + "';";
        sqlite3_stmt* st;
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            if (sqlite3_step(st) == SQLITE_ROW) {
                snapshot["composite_score"]    = sqlite3_column_double(st, 0);
                snapshot["conviction_label"]   = reinterpret_cast<const char*>(sqlite3_column_text(st, 1));
            }
        }
        sqlite3_finalize(st);
    }
    {
        std::string q = "SELECT overall_label, overall_score FROM aggregate_sentiment WHERE ticker = '" + ticker + "';";
        sqlite3_stmt* st;
        json sent_obj;
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            if (sqlite3_step(st) == SQLITE_ROW) {
                sent_obj["overall_label"] = reinterpret_cast<const char*>(sqlite3_column_text(st, 0));
                sent_obj["overall_score"] = sqlite3_column_double(st, 1);
            }
        }
        sqlite3_finalize(st);
        snapshot["sentiment"] = sent_obj;
    }
    {
        std::string q = "SELECT ratio_name, category, value, health_flag, narrative, status, note "
                        "FROM financial_ratios WHERE ticker = '" + ticker + "';";
        sqlite3_stmt* st;
        json ratios_arr = json::array();
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            while (sqlite3_step(st) == SQLITE_ROW) {
                json r;
                std::string name   = reinterpret_cast<const char*>(sqlite3_column_text(st, 0));
                std::string cat    = (sqlite3_column_text(st, 1)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 1)) : "";
                double      val    = sqlite3_column_double(st, 2);
                std::string health = (sqlite3_column_text(st, 3)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 3)) : "";
                std::string narr   = (sqlite3_column_text(st, 4)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 4)) : "";
                std::string status = (sqlite3_column_text(st, 5)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 5)) : "CALCULATED";
                std::string note   = (sqlite3_column_text(st, 6)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 6)) : "";
                r["name"]           = name;
                r["display_name"]   = prettify_name(name);
                r["category"]       = cat;
                r["health_flag"]    = health;
                r["narrative"]      = narr;
                r["status"]         = status;
                r["note"]           = note;
                if (status == "CALCULATED") {
                    r["value"]         = val;
                    r["formatted"]     = fmt_metric(name, val);
                } else {
                    r["value"]         = nullptr;
                    r["formatted"]     = "[" + status + "]";
                }
                ratios_arr.push_back(r);
            }
        }
        sqlite3_finalize(st);
        snapshot["ratios"] = ratios_arr;
    }
    {
        std::string q = "SELECT line_items FROM financial_statements WHERE ticker = '" + ticker + "' AND statement_type = 'KEY_STATS';";
        sqlite3_stmt* st;
        json key_stats = json::array();
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            if (sqlite3_step(st) == SQLITE_ROW) {
                if (sqlite3_column_text(st, 0)) {
                    try {
                        json raw = json::parse(reinterpret_cast<const char*>(sqlite3_column_text(st, 0)));
                        if (raw.is_array()) {
                            for (const auto& item : raw) {
                                json ks;
                                std::string raw_name = item.value("name", "");
                                double v = item.value("value", 0.0);
                                ks["name"]         = raw_name;
                                ks["display_name"] = prettify_name(raw_name);
                                ks["value"]        = v;
                                ks["formatted"]    = fmt_metric(raw_name, v);
                                key_stats.push_back(ks);
                            }
                        }
                    } catch (...) {}
                }
            }
        }
        sqlite3_finalize(st);
        snapshot["key_statistics"] = key_stats;
    }
    {
        std::string q = "SELECT segment, excerpt, label, confidence, source_url, published_at "
                        "FROM sentiment_excerpts WHERE ticker = '" + ticker + "';";
        sqlite3_stmt* st;
        json news_arr = json::array();
        json transcript_arr = json::array();
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            while (sqlite3_step(st) == SQLITE_ROW) {
                json ex;
                std::string segment = (sqlite3_column_text(st, 0)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 0)) : "";
                ex["excerpt"]      = (sqlite3_column_text(st, 1)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 1)) : "";
                ex["label"]        = (sqlite3_column_text(st, 2)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 2)) : "";
                ex["confidence"]   = sqlite3_column_double(st, 3);
                ex["source_url"]   = (sqlite3_column_text(st, 4)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 4)) : "";
                ex["published_at"] = (sqlite3_column_text(st, 5)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 5)) : "";
                if (segment == "NEWS") {
                    news_arr.push_back(ex);
                } else {
                    transcript_arr.push_back(ex);
                }
            }
        }
        sqlite3_finalize(st);
        snapshot["news_excerpts"]       = news_arr;
        snapshot["transcript_excerpts"] = transcript_arr;
    }
    {
        std::string q = "SELECT peer_ticker, ratio_name, ticker_value, peer_value, premium_discount "
                        "FROM peer_benchmarks WHERE ticker = '" + ticker + "';";
        sqlite3_stmt* st;
        json peers_arr = json::array();
        if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK) {
            while (sqlite3_step(st) == SQLITE_ROW) {
                json pb;
                pb["peer_ticker"]      = (sqlite3_column_text(st, 0)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 0)) : "";
                pb["ratio_name"]       = (sqlite3_column_text(st, 1)) ? reinterpret_cast<const char*>(sqlite3_column_text(st, 1)) : "";
                pb["ticker_value"]     = sqlite3_column_double(st, 2);
                pb["peer_value"]       = sqlite3_column_double(st, 3);
                pb["premium_discount"] = sqlite3_column_double(st, 4);
                peers_arr.push_back(pb);
            }
        }
        sqlite3_finalize(st);
        snapshot["peer_benchmarks"] = peers_arr;
    }
    sqlite3_close(db);
    std::ofstream out(json_path);
    if (!out.is_open()) {
        std::cerr << "[JsonSnapshot] Failed to write: " << json_path << "\n";
        return "";
    }
    out << snapshot.dump(2);
    out.close();
    std::cout << "[C++] Generated JSON snapshot: " << json_path << "\n";
    std::cout << "[GENERATION_ID] " << generation_id << "\n";
    return json_path;
}

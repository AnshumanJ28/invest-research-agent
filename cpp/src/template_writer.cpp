#include "template_writer.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <sqlite3.h>
#include <vector>
#include <iomanip>
#include <chrono>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

struct Ratio {
    std::string name;
    std::string category;
    std::string val_str;
    std::string health;
    std::string narrative;
};

struct SentimentExcerpt {
    std::string segment;
    std::string excerpt;
    std::string label;
    double confidence;
    std::string source_url;
    std::string published_at;
};

struct PeerBenchmarkItem {
    std::string peer_ticker;
    std::string ratio_name;
    double ticker_value;
    double peer_value;
    double premium_discount;
};

std::string format_double(double val, int precision = 4) {
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(precision) << val;
    return ss.str();
}

std::string format_metric_value(const std::string& name, double val) {
    if (name.find("margin") != std::string::npos || 
        name.find("roe") != std::string::npos || 
        name.find("roa") != std::string::npos || 
        name.find("growth") != std::string::npos ||
        name.find("percent") != std::string::npos) {
        return format_double(val * 100.0, 2) + "%";
    } else if (name.find("dividend") != std::string::npos) {
        double pct = (val > 0.5) ? val : (val * 100.0);
        return format_double(pct, 2) + "%";
    } else if (name == "enterprise_value" || name == "market_cap") {
        if (val >= 1e12) return "₹" + format_double(val / 1e12, 2) + "T";
        if (val >= 1e9) return "₹" + format_double(val / 1e9, 2) + "B";
        if (val >= 1e6) return "₹" + format_double(val / 1e6, 2) + "M";
        return "₹" + format_double(val, 2);
    } else if (name == "current_price" || name == "target_price" || name == "52_week_high" || name == "52_week_low") {
        return "₹" + format_double(val, 2);
    } else if (name == "beta") {
        if (std::abs(val) < 0.005) return "0.00";
        return format_double(val, 2);
    } else {
        return format_double(val, 2) + "x";
    }
}

std::string format_ratio_name(std::string name) {
    for (char& c : name) {
        if (c == '_') c = ' ';
    }
    bool capitalize_next = true;
    for (char& c : name) {
        if (std::isspace(c)) {
            capitalize_next = true;
        } else if (capitalize_next) {
            c = std::toupper(c);
            capitalize_next = false;
        }
    }
    return name;
}

void TemplateWriter::generate_markdown(const std::string& ticker, const std::string& db_path, const std::string& output_dir) {
    sqlite3* db;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "Failed to open DB for templating\n";
        return;
    }

    // 1. Get Assessment
    std::string comp_label = "HOLD";
    std::string comp_score = "0.0";
    std::string query_ass = "SELECT composite_score, conviction_label FROM investment_assessment WHERE ticker = '" + ticker + "';";
    sqlite3_stmt* stmt_ass;
    if (sqlite3_prepare_v2(db, query_ass.c_str(), -1, &stmt_ass, 0) == SQLITE_OK) {
        if (sqlite3_step(stmt_ass) == SQLITE_ROW) {
            comp_score = format_double(sqlite3_column_double(stmt_ass, 0), 2);
            if (sqlite3_column_text(stmt_ass, 1)) comp_label = reinterpret_cast<const char*>(sqlite3_column_text(stmt_ass, 1));
        }
    }
    sqlite3_finalize(stmt_ass);

    // 2. Get Sentiment
    std::string overall_sentiment = "Neutral";
    std::string sent_score = "0.0";
    std::string query_sent = "SELECT overall_label, overall_score FROM aggregate_sentiment WHERE ticker = '" + ticker + "';";
    sqlite3_stmt* stmt_sent;
    if (sqlite3_prepare_v2(db, query_sent.c_str(), -1, &stmt_sent, 0) == SQLITE_OK) {
        if (sqlite3_step(stmt_sent) == SQLITE_ROW) {
            if (sqlite3_column_text(stmt_sent, 0)) overall_sentiment = reinterpret_cast<const char*>(sqlite3_column_text(stmt_sent, 0));
            sent_score = format_double(sqlite3_column_double(stmt_sent, 1), 2);
        }
    }
    sqlite3_finalize(stmt_sent);

    // 3. Get Ratios
    std::vector<Ratio> ratios;
    std::string query_rat = "SELECT ratio_name, category, value, health_flag, narrative, status, note FROM financial_ratios WHERE ticker = '" + ticker + "';";
    sqlite3_stmt* stmt_rat;
    if (sqlite3_prepare_v2(db, query_rat.c_str(), -1, &stmt_rat, 0) == SQLITE_OK) {
        while (sqlite3_step(stmt_rat) == SQLITE_ROW) {
            Ratio r;
            if (sqlite3_column_text(stmt_rat, 0)) r.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 0));
            if (sqlite3_column_text(stmt_rat, 1)) r.category = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 1));
            if (sqlite3_column_text(stmt_rat, 3)) r.health = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 3));
            if (sqlite3_column_text(stmt_rat, 4)) r.narrative = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 4));
            
            std::string status = "CALCULATED";
            if (sqlite3_column_text(stmt_rat, 5)) status = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 5));
            std::string note = "";
            if (sqlite3_column_text(stmt_rat, 6)) note = reinterpret_cast<const char*>(sqlite3_column_text(stmt_rat, 6));
            
            if (status == "DATA_MISSING") {
                if (!note.empty() && note.find("DATA_MISSING: ") != std::string::npos) {
                    std::string reason = note.substr(14);
                    r.val_str = "_[DATA MISSING] (" + reason + ")_";
                } else {
                    r.val_str = "_[DATA MISSING]_";
                }
            } else if (status == "NOT_COMPUTABLE") {
                r.val_str = "_[NOT COMPUTABLE]_";
            } else if (status == "NOT_APPLICABLE") {
                r.val_str = "_[NOT APPLICABLE]_";
            } else {
                double val = sqlite3_column_double(stmt_rat, 2);
                r.val_str = format_metric_value(r.name, val) + " *(" + r.health + ")*";
            }
            ratios.push_back(r);
        }
    }
    sqlite3_finalize(stmt_rat);

    // 4. Get Key Stats from Financial Statements
    std::string key_stats_json = "";
    std::string query_fs = "SELECT line_items FROM financial_statements WHERE ticker = '" + ticker + "' AND statement_type = 'KEY_STATS';";
    sqlite3_stmt* stmt_fs;
    if (sqlite3_prepare_v2(db, query_fs.c_str(), -1, &stmt_fs, 0) == SQLITE_OK) {
        if (sqlite3_step(stmt_fs) == SQLITE_ROW) {
            if (sqlite3_column_text(stmt_fs, 0)) key_stats_json = reinterpret_cast<const char*>(sqlite3_column_text(stmt_fs, 0));
        }
    }
    sqlite3_finalize(stmt_fs);

    // 5. Get Excerpts
    std::vector<SentimentExcerpt> news_excerpts;
    std::vector<SentimentExcerpt> transcript_excerpts;
    std::string query_exc = "SELECT segment, excerpt, label, confidence, source_url, published_at FROM sentiment_excerpts WHERE ticker = '" + ticker + "';";
    sqlite3_stmt* stmt_exc;
    if (sqlite3_prepare_v2(db, query_exc.c_str(), -1, &stmt_exc, 0) == SQLITE_OK) {
        while (sqlite3_step(stmt_exc) == SQLITE_ROW) {
            SentimentExcerpt ex;
            if (sqlite3_column_text(stmt_exc, 0)) ex.segment = reinterpret_cast<const char*>(sqlite3_column_text(stmt_exc, 0));
            if (sqlite3_column_text(stmt_exc, 1)) ex.excerpt = reinterpret_cast<const char*>(sqlite3_column_text(stmt_exc, 1));
            if (sqlite3_column_text(stmt_exc, 2)) ex.label = reinterpret_cast<const char*>(sqlite3_column_text(stmt_exc, 2));
            ex.confidence = sqlite3_column_double(stmt_exc, 3);
            if (sqlite3_column_text(stmt_exc, 4)) ex.source_url = reinterpret_cast<const char*>(sqlite3_column_text(stmt_exc, 4));
            if (sqlite3_column_text(stmt_exc, 5)) ex.published_at = reinterpret_cast<const char*>(sqlite3_column_text(stmt_exc, 5));
            
            // basic clean up of excerpt to remove newlines for markdown
            for(char& c : ex.excerpt) { if (c == '\n' || c == '\r') c = ' '; }

            std::string lower_excerpt = ex.excerpt;
            std::transform(lower_excerpt.begin(), lower_excerpt.end(), lower_excerpt.begin(), ::tolower);

            if (ex.segment == "NEWS" && lower_excerpt.find("earnings call") != std::string::npos) {
                transcript_excerpts.push_back(ex);
            } else if (ex.segment == "NEWS") {
                news_excerpts.push_back(ex);
            } else if (ex.segment.find("TRANSCRIPT") != std::string::npos) {
                transcript_excerpts.push_back(ex);
            }
        }
    }
    sqlite3_finalize(stmt_exc);

    // 6. Get Peer Benchmarks
    std::vector<PeerBenchmarkItem> peers;
    std::string query_pb = "SELECT peer_ticker, ratio_name, ticker_value, peer_value, premium_discount FROM peer_benchmarks WHERE ticker = '" + ticker + "';";
    sqlite3_stmt* stmt_pb;
    if (sqlite3_prepare_v2(db, query_pb.c_str(), -1, &stmt_pb, 0) == SQLITE_OK) {
        while (sqlite3_step(stmt_pb) == SQLITE_ROW) {
            PeerBenchmarkItem pb;
            if (sqlite3_column_text(stmt_pb, 0)) pb.peer_ticker = reinterpret_cast<const char*>(sqlite3_column_text(stmt_pb, 0));
            if (sqlite3_column_text(stmt_pb, 1)) pb.ratio_name = reinterpret_cast<const char*>(sqlite3_column_text(stmt_pb, 1));
            pb.ticker_value = sqlite3_column_double(stmt_pb, 2);
            pb.peer_value = sqlite3_column_double(stmt_pb, 3);
            pb.premium_discount = sqlite3_column_double(stmt_pb, 4);
            peers.push_back(pb);
        }
    }
    sqlite3_finalize(stmt_pb);


    // --- WRITE MARKDOWN ---
    std::string out_path = output_dir + "/" + ticker + ".md";
    std::ofstream out(out_path);
    if (!out.is_open()) {
        std::cerr << "Failed to write markdown to " << out_path << "\n";
        sqlite3_close(db);
        return;
    }

    out << "# " << ticker << " - Executive Briefing\n\n";
    out << "---\n\n";
    
    out << "## At a Glance\n\n";
    out << "* **Composite Assessment:** **" << comp_label << "** (Score: " << comp_score << "/10.0)\n";
    out << "* **Sentiment:** " << overall_sentiment << " (Score: " << sent_score << ")\n";
    out << "* **Metrics Evaluated:** " << ratios.size() << "\n";
    out << "* **News Articles Analyzed:** " << news_excerpts.size() << "\n\n";
    out << "---\n\n";
    
    out << "## Financial Snapshot\n\n";
    if (ratios.empty()) {
        out << "* *Financial ratios are pending evaluation.*\n\n";
    } else {
        out << "### Ratios\n";
        for (const auto& r : ratios) {
            out << "* **" << format_ratio_name(r.name) << "** = " << r.val_str;
            if (!r.narrative.empty()) {
                out << " - " << r.narrative;
            }
            out << "\n";
        }
        out << "\n";
    }

    if (!key_stats_json.empty()) {
        try {
            json ks = json::parse(key_stats_json);
            if (ks.is_array() && !ks.empty()) {
                out << "### Key Statistics\n";
                out << "| Metric | Value | Unit |\n";
                out << "|---|---|---|\n";
                double fwd_pe = 0, trail_pe = 0;
                bool has_fwd = false, has_trail = false;
                for (const auto& item : ks) {
                    std::string raw_name = item.contains("name") ? item["name"].get<std::string>() : "";
                    std::string name = format_ratio_name(raw_name);
                    double val = item.contains("value") ? item["value"].get<double>() : 0.0;
                    if (raw_name == "forward_pe") { fwd_pe = val; has_fwd = true; }
                    if (raw_name == "trailing_pe") { trail_pe = val; has_trail = true; }
                    std::string formatted_val = format_metric_value(raw_name, val);
                    std::string unit = "";
                    if (raw_name == "beta") unit = "coefficient";
                    else if (raw_name == "enterprise_value" || raw_name == "market_cap" || raw_name == "current_price" || raw_name == "target_price" || raw_name == "52_week_high" || raw_name == "52_week_low") unit = "INR";
                    else if (formatted_val.back() == '%') unit = "percentage";
                    else if (formatted_val.back() == 'x') unit = "multiple";
                    out << "| **" << name << "** | " << formatted_val << " | " << unit << " |\n";
                }
                out << "\n";
                if (has_fwd && has_trail && trail_pe > 0) {
                    out << "*Note: Forward P/E (" << format_metric_value("forward_pe", fwd_pe) 
                        << ") is " << (fwd_pe < trail_pe ? "lower" : "higher") << " than Trailing P/E (" 
                        << format_metric_value("trailing_pe", trail_pe) << "), suggesting the market expects earnings to " 
                        << (fwd_pe < trail_pe ? "grow" : "contract") << " over the next 12 months.*\n\n";
                }
            }
        } catch(...) {}
    }
    
    out << "---\n\n";

    out << "## News & Sentiment Analysis\n\n";
    if (news_excerpts.empty()) {
        out << "* *News analysis is unavailable.*\n\n";
    } else {
        for (size_t i = 0; i < news_excerpts.size() && i < 5; ++i) {
            const auto& ex = news_excerpts[i];
            out << "* **[" << ex.label << "]** *" << ex.excerpt << "* ([" << ex.published_at << "](" << ex.source_url << "))\n";
        }
        out << "\n";
    }

    out << "---\n\n";

    out << "## Earnings Call Analysis\n\n";
    if (transcript_excerpts.empty()) {
        out << "* *Earnings Call data is unavailable.*\n\n";
    } else {
        for (size_t i = 0; i < transcript_excerpts.size() && i < 5; ++i) {
            const auto& ex = transcript_excerpts[i];
            out << "* **[" << ex.label << "]** *" << ex.excerpt << "*\n";
        }
        out << "\n";
    }

    out << "---\n\n";

    out << "## Peer Comparison\n\n";
    if (peers.empty()) {
        out << "* *Peer benchmark data is currently unavailable.*\n\n";
    } else {
        out << "| Peer | Ratio | " << ticker << " Value | Peer Value | Prem/Disc |\n";
        out << "|---|---|---|---|---|\n";
        for (const auto& pb : peers) {
            out << "| " << pb.peer_ticker << " | " << format_ratio_name(pb.ratio_name) << " | " 
                << format_metric_value(pb.ratio_name, pb.ticker_value) << " | " 
                << format_metric_value(pb.ratio_name, pb.peer_value) 
                << " | " << format_double(pb.premium_discount, 2) << "% |\n";
        }
        out << "\n";
    }
    
    out << "---\n\n";
    out << "*Disclaimer: This research memo is generated programmatically by an AI RAG engine. Do not use this memo as the sole basis for any financial or investment decisions.*\n";
    
    out.close();
    sqlite3_close(db);
    std::cout << "[C++] Generated native Markdown memo: " << out_path << "\n";
}

#ifndef JSON_SNAPSHOT_WRITER_H
#define JSON_SNAPSHOT_WRITER_H

#include <string>

class JsonSnapshotWriter {
public:
    /**
     * Reads all analysis data from SQLite and writes a structured JSON snapshot
     * to reports/TICKER_TIMESTAMP.json.  Returns the output path.
     *
     * The JSON includes a `pdf_path` field pointing to the PDF that the Java
     * TemplateEngine will generate afterwards.
     */
    static std::string generate_snapshot(const std::string& ticker,
                                         const std::string& generation_id,
                                         const std::string& db_path,
                                         const std::string& output_dir);
};

#endif // JSON_SNAPSHOT_WRITER_H

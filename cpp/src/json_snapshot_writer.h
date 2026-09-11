#ifndef JSON_SNAPSHOT_WRITER_H
#define JSON_SNAPSHOT_WRITER_H
#include <string>
class JsonSnapshotWriter {
public:
    static std::string generate_snapshot(const std::string& ticker,
                                         const std::string& generation_id,
                                         const std::string& db_path,
                                         const std::string& output_dir);
};
#endif 

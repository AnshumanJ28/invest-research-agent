#ifndef TEMPLATE_WRITER_H
#define TEMPLATE_WRITER_H

#include <string>

class TemplateWriter {
public:
    static void generate_markdown(const std::string& ticker, const std::string& db_path, const std::string& output_dir);
};

#endif // TEMPLATE_WRITER_H

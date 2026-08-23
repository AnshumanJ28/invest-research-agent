#pragma once

#include <string>
#include <vector>

struct TranscriptUtterance {
    std::string speaker;
    std::string text;
    std::string section;
};

struct TranscriptDocument {
    bool available;
    std::string unavailable_reason;
    std::vector<TranscriptUtterance> utterances;
};

class TranscriptAgent {
public:
    TranscriptAgent() = default;
    TranscriptDocument fetch_transcript(const std::string& ticker);
};

cmake_minimum_required(VERSION 3.14)
project(InvestResearchAgentCPP)

# Allow fetching older CMake projects (like nlohmann_json) on newer CMake versions (4.0+)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "" FORCE)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Statically link everything to avoid missing DLL errors
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)

include(FetchContent)

# Fetch nlohmann_json for JSON parsing
FetchContent_Declare(json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_MakeAvailable(json)

add_library(sqlite3_lib STATIC third_party/sqlite/sqlite3.c)
target_include_directories(sqlite3_lib PUBLIC third_party/sqlite)

add_executable(invest_pipeline
    src/main.cpp
    src/news_agent.cpp
    src/yfinance_agent.cpp
    src/transcript_agent.cpp
    src/edgar_agent.cpp
    src/ratios.cpp
    src/sentiment.cpp
    src/tokenizer.cpp
    src/storage.cpp
    "../C maths/simd_math.c"
    "../C maths/fast_ratios.c"
    src/faiss_search.cpp
    src/onnx_engine.cpp
    src/template_writer.cpp
)

target_link_libraries(invest_pipeline PRIVATE nlohmann_json::nlohmann_json sqlite3_lib)
target_include_directories(invest_pipeline PRIVATE src "../C maths" third_party/onnxruntime/include)
target_link_directories(invest_pipeline PRIVATE third_party/onnxruntime/lib)
target_link_libraries(invest_pipeline PRIVATE onnxruntime)

# Copy the ONNX Runtime DLL to the output directory so the executable can find it
add_custom_command(TARGET invest_pipeline POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${CMAKE_SOURCE_DIR}/third_party/onnxruntime/lib/onnxruntime.dll"
    $<TARGET_FILE_DIR:invest_pipeline>
)

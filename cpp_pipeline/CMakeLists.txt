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
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.2
)
FetchContent_MakeAvailable(json)

# Fetch CPR for HTTP Requests
FetchContent_Declare(cpr
    GIT_REPOSITORY https://github.com/libcpr/cpr.git
    GIT_TAG 1.10.5
)
set(CPR_USE_SYSTEM_CURL OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(cpr)

FetchContent_Declare(
  sqlite
  URL https://sqlite.org/2023/sqlite-amalgamation-3430200.zip
)
FetchContent_MakeAvailable(sqlite)
add_library(sqlite3_lib STATIC ${sqlite_SOURCE_DIR}/sqlite3.c)
target_include_directories(sqlite3_lib PUBLIC ${sqlite_SOURCE_DIR})

add_executable(invest_pipeline
    src/main.cpp
    src/news_agent.cpp
    src/yfinance_agent.cpp
    src/transcript_agent.cpp
    src/edgar_agent.cpp
    src/ratios.cpp
    src/sentiment.cpp
    src/storage.cpp
)

target_link_libraries(invest_pipeline PRIVATE nlohmann_json::nlohmann_json cpr::cpr sqlite3_lib)
target_include_directories(invest_pipeline PRIVATE src)

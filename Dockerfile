# Use a lightweight Python base image
FROM python:3.10-slim

# Install system dependencies required for CMake and building C++ extensions
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libssl-dev \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Build the C++ pipeline
WORKDIR /app/cpp_pipeline
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
RUN cmake --build build --config Release

# Ensure the database doesn't get reset if mounted, but provide a default location
VOLUME ["/app/cpp_pipeline"]

# Set the entrypoint to the compiled C++ executable
ENTRYPOINT ["./build/invest_pipeline"]

# Default argument (can be overridden when running the container)
CMD ["INFY.NS"]

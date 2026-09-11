# Use Ubuntu as the base to easily get Java, Python, and C++ compilers
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    openjdk-21-jdk \
    build-essential \
    cmake \
    git \
    wget \
    libssl-dev \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Setup Python virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Download the ONNX model from GitHub Releases (so it doesn't bloat the git repo)
# NOTE: Ensure you have uploaded finbert_int8.onnx to a GitHub Release tagged v1.0
RUN mkdir -p /app/cpp/models && \
    wget -O /app/cpp/models/finbert_int8.onnx "https://github.com/AnshumanJ28/invest-research-agent/releases/download/v1.0/finbert_int8.onnx" || echo "Model download failed, update the URL!"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Build the C++ Engine
WORKDIR /app/cpp
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
RUN cmake --build build --config Release

# Move back to root
WORKDIR /app

# Compile Java Orchestrator
RUN javac -cp "java/lib/*" -d java/bin java/src/*.java

# Ensure the database doesn't get reset if mounted, but provide a default location
VOLUME ["/app/cpp"]

# Set the entrypoint to the FastAPI Web Server
# We run Uvicorn with exactly 1 worker to strictly respect the 512MB RAM limit
ENTRYPOINT ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000", "--workers", "1"]

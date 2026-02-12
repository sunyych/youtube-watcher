# Backend Dockerfile
FROM python:3.11-slim

# Install system dependencies including build tools for faster-whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    unzip \
    build-essential \
    python3-dev \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    zlib1g-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Deno (JavaScript runtime) for yt-dlp YouTube challenge solving
# yt-dlp recommends an external JS runtime for full YouTube support.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) deno_zip="deno-x86_64-unknown-linux-gnu.zip" ;; \
      arm64) deno_zip="deno-aarch64-unknown-linux-gnu.zip" ;; \
      *) echo "Unsupported architecture for Deno: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/denoland/deno/releases/latest/download/${deno_zip}" -o /tmp/deno.zip; \
    unzip -q /tmp/deno.zip -d /usr/local/bin; \
    rm -f /tmp/deno.zip; \
    deno --version

# Set working directory
WORKDIR /app

# Upgrade pip and install build tools
RUN pip install --upgrade pip setuptools wheel

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

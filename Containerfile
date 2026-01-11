# dl-video containerized TUI app
# Includes Python app + yt-dlp + ffmpeg - no local installation needed

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    # For pyperclip (clipboard) - optional, won't work in container anyway
    xclip \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (latest)
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Create downloads directory
RUN mkdir -p /downloads

# Set environment variables
ENV TERM=xterm-256color
ENV COLORTERM=truecolor
# Use local backend since yt-dlp/ffmpeg are in the container
ENV DL_VIDEO_BACKEND=local

# Default download directory inside container
ENV DL_VIDEO_OUTPUT_DIR=/downloads

# Run the app
ENTRYPOINT ["uv", "run", "python", "-m", "dl_video"]

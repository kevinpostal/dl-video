# dl-video

A terminal UI application for downloading, converting, and sharing videos. Built with [Textual](https://textual.textualize.io/).

![dl-video demo](demo.gif)

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- 🎬 Download videos from YouTube and other sites (via yt-dlp)
- 🔄 Convert to MP4 (via ffmpeg)
- ☁️ Upload to upload.beer with one click
- 📋 Auto-copy upload URLs to clipboard
- 📜 Download history with metadata
- 🖼️ Video thumbnail previews
- ⚙️ Configurable settings (cookies, download folder, etc.)
- 🌐 Web access via Tailscale Funnel
- 🐳 Container support - run without installing dependencies

## Quick Start

### Option 1: Container (Recommended)

No Python or dependencies needed - just Podman (or Docker):

```bash
# Build the container
make app-build

# Run (downloads to ~/Downloads)
make app-run
```

### Option 2: Local Installation

```bash
# Install dependencies
make install

# Run
make run
```

## Requirements

**For container mode:**
- [Podman](https://podman.io/) or Docker

**For local installation:**
- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Usage

```bash
# Terminal mode
make run

# Web browser mode (local network)
make serve

# Public access via Tailscale Funnel
make funnel
```

### Container Backend

Run the app locally but execute downloads in containers (useful if you don't want to install yt-dlp/ffmpeg):

```bash
# Pull the ffmpeg container image
make container-pull

# Run with container backend
make run-container
```

## Commands

| Command | Description |
|---------|-------------|
| `make run` | Run the app in terminal |
| `make app-build` | Build containerized app |
| `make app-run` | Run containerized app (downloads to ~/Downloads) |
| `make run-container` | Run locally with container backend |
| `make serve` | Serve via web browser |
| `make funnel` | Public access via Tailscale Funnel |
| `make test` | Run tests |
| `make install` | Install dependencies |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Start download |
| `Ctrl+Q` | Quit |
| `Ctrl+P` | Open command palette |
| `Ctrl+O` | Open download folder |

## Configuration

Settings are stored in `~/.config/dl-video/config.json`:

- **Auto-upload**: Automatically upload after download
- **Skip conversion**: Don't convert to MP4
- **Cookies**: Browser to extract cookies from (for age-restricted videos)
- **Download folder**: Where to save videos

## Development

```bash
make dev      # Install dev dependencies
make test     # Run tests
make fmt      # Format code
make lint     # Lint code
```

## License

MIT

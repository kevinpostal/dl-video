# dl-video

A terminal UI application for downloading, converting, and sharing videos. Built with [Textual](https://textual.textualize.io/).

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

## Requirements

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/) (for conversion)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dl-video.git
cd dl-video

# Install dependencies
make install
# or: uv sync
```

## Usage

```bash
# Run in terminal
make run

# Or directly
uv run python -m dl_video
```

### Web Access

Serve the app in a web browser:

```bash
# Local network only
make serve

# Public access via Tailscale Funnel
make funnel
```

## Commands

| Command | Description |
|---------|-------------|
| `make run` | Run the app in terminal |
| `make serve` | Serve via web browser (http://0.0.0.0:8000) |
| `make funnel` | Start with Tailscale Funnel (public URL) |
| `make funnel-stop` | Stop Tailscale Funnel |
| `make test` | Run tests |
| `make clean` | Clean cache files |
| `make install` | Install dependencies |
| `make dev` | Install with dev dependencies |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Start download |
| `Esc` | Quit (with confirmation) |
| `Ctrl+P` | Open command palette |
| `i` | Show video info (in history) |

## Configuration

Settings are stored in `~/.config/dl-video/config.json`:

- **Auto-upload**: Automatically upload after download
- **Skip conversion**: Don't convert to MP4
- **Cookies**: Browser to extract cookies from (for age-restricted videos)
- **Download folder**: Where to save videos

## Development

```bash
# Install dev dependencies
make dev

# Run tests
make test

# Format code
make fmt

# Lint
make lint
```

## License

MIT

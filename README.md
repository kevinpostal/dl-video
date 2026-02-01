# dl-video

A modern terminal UI application for downloading, converting, and sharing videos. Built with [Textual](https://textual.textualize.io/) for a rich, interactive experience.

![dl-video demo](demo.gif)

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg)

## ✨ Features

### Core Functionality
- 🎬 **Download videos** from YouTube and 1000+ other sites (via yt-dlp)
- 🔄 **Convert to MP4** with customizable quality (via ffmpeg)
- ☁️ **One-click upload** to upload.beer with automatic URL copying
- 📜 **Download history** with metadata and thumbnail previews
- 🖼️ **Video thumbnails** with intelligent caching

### User Experience
- 🎯 **Smart URL validation** with autocomplete suggestions
- ⚡ **Real-time progress** tracking with speed charts
- 🎛️ **Configurable settings** (cookies, download folder, quality)
- ⌨️ **Keyboard shortcuts** for power users
- 🌐 **Web interface** for remote access via Tailscale Funnel

### Technical Features
- 🐳 **Container support** - run without installing dependencies
- 🔒 **Secure execution** with isolated container environments
- 🔄 **Dual backends** - local or containerized execution
- 📱 **Responsive UI** that adapts to terminal size
- 🛡️ **Error handling** with helpful troubleshooting messages

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

### System Requirements
- **Operating System**: Linux, macOS, or Windows
- **Python**: 3.11 or higher
- **Terminal**: Modern terminal with 256-color support recommended

### For Container Mode (Recommended)
- [Podman](https://podman.io/) or Docker
- No additional dependencies needed

### For Local Installation
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloading
- [ffmpeg](https://ffmpeg.org/) - Video conversion
- [uv](https://github.com/astral-sh/uv) - Package management (recommended)

### Optional Dependencies
- **xclip** (Linux) - Clipboard support
- **Tailscale** - For Funnel web access

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

### Available Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `auto_upload` | Automatically upload after download | `false` |
| `skip_conversion` | Skip MP4 conversion | `false` |
| `cookies_browser` | Browser for cookie extraction | `null` |
| `download_folder` | Download directory | `~/Downloads` |
| `backend_type` | Execution backend (`local` or `container`) | `local` |

### Cookie Support

For age-restricted or private videos:
1. Set `cookies_browser` to your browser (`chrome`, `firefox`, `safari`, `edge`)
2. Ensure you're logged into the video site in that browser
3. The app will automatically extract and use your cookies

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DL_VIDEO_BACKEND` | Force backend type (`local` or `container`) |
| `DL_VIDEO_CONFIG_DIR` | Custom config directory |

## Development

```bash
make dev      # Install dev dependencies
make test     # Run tests
make fmt      # Format code
make lint     # Lint code
```

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md) - System design and component relationships
- [Contributing Guide](docs/CONTRIBUTING.md) - Development setup and guidelines
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

## License

MIT

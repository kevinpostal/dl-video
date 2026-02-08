# dl-video

A TUI for downloading videos. Built with [Textual](https://textual.textualize.io/).

![demo](demo.gif)

## What it does

Paste a URL, hit enter, get a video file. That's the basic idea.

- Downloads from YouTube, TikTok, Twitter, etc (anything [yt-dlp](https://github.com/yt-dlp/yt-dlp) supports)
- Converts to MP4 automatically (if you want)
- Can upload to [upload.beer](https://upload.beer) and copy the link
- Shows thumbnails and metadata
- Works in the browser too (via Tailscale Funnel)

## Quick start

**Option 1: Container (easiest)**

No Python setup needed, just Podman:

```bash
make app-build
make app-run
```

**Option 2: Local**

```bash
make install
make run
```

## Requirements

**Container mode:**
- [Podman](https://podman.io/)

**Local mode:**
- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [uv](https://github.com/astral-sh/uv) (recommended)

## Usage

```bash
make run          # Terminal UI
make serve        # Web interface (local)
make funnel       # Web interface (public via Tailscale)
```

### Using container backend

Run the app locally but do the actual downloading in a container:

```bash
make container-pull   # One-time setup
make run-container    # Run with container backend
```

Good if you don't want to install yt-dlp/ffmpeg locally.

## Controls

| Key | What it does |
|-----|--------------|
| `Enter` | Download the URL |
| `Ctrl+Q` | Quit |
| `Ctrl+P` | Command palette |
| `Ctrl+O` | Open downloads folder |

## Settings

Hit `Ctrl+P` → Settings, or edit `~/.config/dl-video/config.json`:

- **Auto-upload** - Upload immediately after download
- **Skip conversion** - Keep original format
- **Cookies** - Use browser cookies (helps with age-restricted stuff)
- **Download folder** - Where videos go

## Development

```bash
make dev     # Install dev deps
make test    # Run tests
make fmt     # Format with ruff
make lint    # Lint with ruff
```

## License

MIT

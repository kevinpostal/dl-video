# dl-video

A TUI for downloading videos. Built with [Textual](https://textual.textualize.io/).

![demo](demo.gif)

## What it does

Paste a URL, hit enter, get a video file. That's the basic idea.

- Downloads from YouTube, TikTok, Twitter, etc (anything [yt-dlp](https://github.com/yt-dlp/yt-dlp) supports)
- Converts to MP4 automatically (if you want)
- Can upload to `files.brokejokes.com` (self-hosted, `brokejokes-files/`) and copy the link
- Shows thumbnails and metadata
- Works in the browser too (on your tailnet, `make serve-tailnet`)

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
make run            # Terminal UI
make serve          # Web interface (http://127.0.0.1:8000, no auth)
make serve-tailnet  # Web interface on your tailnet only (https://<mac>.ts.net)
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
- **Upload proxy** (`upload_proxy`) - Send uploads through a proxy, e.g.
  `socks5://127.0.0.1:1080`. Needed when a network filters the upload host: the
  filter answers the TLS handshake with plaintext and the upload fails with an
  SSL error. `DL_VIDEO_UPLOAD_PROXY` overrides it for a single run.

## iPhone app

iOS can't run yt-dlp or ffmpeg, so the iPhone app (`ios/`) is a client for an
API server that runs the same pipeline on this Mac.

```bash
make serve-api-install  # keep it running (launchd) at https://<mac>.<tailnet>.ts.net:8443
make serve-api          # foreground on http://127.0.0.1:8765 (Simulator)
make serve-api-stop     # stop everything, remove the launchd agent
```

The server's bearer token is in `~/.config/dl-video/server_token`; logs go to
`~/Library/Logs/dl-video-server.log`. Enter the URL and token in the app's
Settings tab. The iPhone needs the Tailscale app on the same tailnet.

Uploads go to `files.brokejokes.com`, a small Elixir service in
`brokejokes-files/` (deploy with `make -C brokejokes-files deploy`). The upload
token lives in `~/.config/dl-video/upload_token` (or `DL_VIDEO_UPLOAD_TOKEN`).
The app saves uploaded videos from that public URL, so saving to Photos works
off the tailnet too.

Cloudflare caps proxied request bodies at 100 MB, so larger uploads fail with
HTTP 413.

Ways to send a link or file from another app (e.g. Messages):

- **Share sheet**: "Download with dl-video" in the action list, or dl-video in
  the app row. Links are queued and files (a video in Messages or Photos, an
  item in Files) are sent to the Mac, which converts/uploads them like any other
  job. It starts at once with the Mac's defaults and closes itself.
- **Copied link + one press**: copy the link, then use the "Download Copied
  Link" control (Control Center, Lock Screen, or Settings › Action Button ›
  Controls), or assign the "Download Copied Link" shortcut to Back Tap
  (Settings › Accessibility › Touch › Back Tap). It opens dl-video and queues the link.
- **Siri / Spotlight / Shortcuts**: "Download copied link with dl-video", or the
  "Download Video" action in your own shortcuts and automations.
- **In the app**: the paste button next to the link field pastes and starts in
  one tap, without the "Allow Paste" prompt.

App Intents only run from team-signed builds. Xcode's ad-hoc simulator builds
show "Unable to run App Shortcut", so test them on a device.

Build the app (Xcode signed in to the team account):

```bash
cd ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodegen generate
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project DLVideo.xcodeproj -scheme DLVideo -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/dlvideo-build -allowProvisioningUpdates build
```

Keep `-derivedDataPath` outside iCloud Drive: iCloud adds extended attributes
that make codesign fail ("resource fork, Finder information, or similar detritus").

## Development

```bash
make dev     # Install dev deps
make test    # Run tests
make ios-e2e # iOS end-to-end tests in the Simulator (needs the API server running)
make fmt     # Format with ruff
make lint    # Lint with ruff
```

`make ios-e2e` drives the real share sheet and Home Screen quick action in a
dedicated simulator (`IOS_SIM`, default "dl-video E2E", created on first run)
against the local API server and checks the resulting Mac jobs. It covers a
plain link, Messages-style link previews, and a copied link preview on the
clipboard. It turns server auto-upload off while it runs and restores it.

## License

MIT

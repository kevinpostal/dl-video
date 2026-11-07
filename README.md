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
API server that runs the same pipeline on this Mac or on an always-on box.

```bash
make serve-api-install  # keep it running (launchd) at https://<mac>.<tailnet>.ts.net:8443
make serve-api          # foreground on http://127.0.0.1:8765 (Simulator)
make serve-api-stop     # stop everything, remove the launchd agent
```

The server's bearer token is in `~/.config/dl-video/server_token`; logs go to
`~/Library/Logs/dl-video-server.log`. Enter the URL and token in the app's
Settings tab. The iPhone needs the Tailscale app on the same tailnet.

The launchd service installs a non-editable wheel into
`~/.local/share/dl-video/server-venv`, separate from the development environment.
It does not import Python source from iCloud Drive, where background reads can
fail with `Resource deadlock avoided`; development commands cannot replace its
installed package. Re-run `make serve-api-install` after changing server code.

**Away from home:** a sleeping MacBook is off the tailnet, so the phone can't
reach it. Run the same server on an always-on Linux box instead:

```bash
make pi-deploy PI_HOST=pi-gate   # docker compose on the Pi + tailscale serve :8443
make pi-cookies                  # ship Chrome cookies for Instagram/YouTube/... to the Pi
make pi-logs
make pi-stop
```

It rsyncs the sources to `/srv/dl-video/src`, builds the `Containerfile`
(yt-dlp, ffmpeg, node), keeps state in `/srv/dl-video/{config,downloads}`,
and copies this Mac's `server_token`/`upload_token` the first time, so the
app only needs the Pi's URL (`https://pi-gate.<tailnet>.ts.net:8443`).
Conversions run on the Pi's CPU (libx264, no hardware encoder), so expect
them to take several times longer than on the Mac.

The Pi has no browser, so its config uses `cookies_file` instead of
`cookies_browser`: `make pi-cookies` exports only the cookies for the sites in
`scripts/export_cookies.py` (`--domains` to change) from this Mac's Chrome and
puts them in `/srv/dl-video/config/cookies.txt`. Sites rotate login cookies, so
re-run it when Instagram or YouTube downloads start failing with login errors.

Uploads go to `files.brokejokes.com`, a small Elixir service in
`brokejokes-files/` (deploy with `make -C brokejokes-files deploy`). The upload
token lives in `~/.config/dl-video/upload_token` (or `DL_VIDEO_UPLOAD_TOKEN`).
The app copies a public **share page** URL (`/s/<name>`), not the raw MP4.
Saving to Photos or Files uses the separate original-file URL (`/f/<name>`),
so it still works off the tailnet and never downloads the HTML page as a video.

Cloudflare caps proxied request bodies at 100 MB, so larger uploads fail with
HTTP 413.

### Public sharing and previews

Share pages supply OpenGraph metadata for link unfurlers (Telegram, Discord,
WhatsApp, Messages, Facebook and others), a JPEG poster, and an HTTPS
Twitter/X player card. They also contain a native browser player and a
**Download original** button. Platform policy, preview settings and caches
still control the final card: this does not promise inline playback everywhere.
Instagram/TikTok-style native video posts still require uploading the file.

The host probes uploaded content rather than trusting its extension. Safe,
small H.264/AAC MP4s keep their original quality; other videos receive a
separate full-duration H.264/AAC, 8-bit `yuv420p`, fast-start preview. Encoded
previews fit within 1280 pixels on the long edge and **19 MiB**, below the
[independently measured Telegram 20 MiB preview boundary](https://github.com/Bl0ck154/InstaFix-Revived/blob/main/docs/telegram-reel-previews.md).
The original is never replaced by the preview. HDR sources are tone-mapped
to SDR when supported; unsupported/corrupt media fails explicitly. Extremely
long videos that cannot fit at the minimum preview bitrate are rejected,
not silently shortened. Images and audio uploads remain supported.

Uploads return `202 {status_url, name}` promptly. The client polls the
bearer-authenticated status URL on the same origin until `200` provides
`{url, download_url, preview_url, name}`. `url` is the share page; `download_url`
is the original; `preview_url` is null for non-video media. Jobs/history expose
the additive `download_url` field alongside `upload_url` (now the share page).
The client waits at most 30 minutes; failed preparation never becomes a
successful share link. Pending jobs survive server restarts; overload returns
503 with `Retry-After` rather than growing an unbounded encoding queue.

Deploy the host **before** the updated API/client, then prepare old uploads:

```bash
make -C brokejokes-files deploy
make -C brokejokes-files backfill
```

Backfill is idempotent, shares the live encoding limit, reports failures and
preserves legacy originals. Existing `/f/` links keep serving the same bytes.
Old own-host history links migrate to `/s/` for sharing while retaining `/f/`
for downloads; old messages containing raw links are not rewritten. Use the
new share URL when re-linking. Unprepared legacy pages offer the original
without advertising missing media; public GETs never start an encode.

Host `.env` controls `MEDIA_MAX_CONCURRENCY` (default 1),
`MEDIA_THREADS` (2), `MEDIA_TIMEOUT_SECONDS` (600 per preparation) and
`MAX_UPLOAD_BYTES` (524288000 at the application; Cloudflare can be lower).
`PUBLIC_URL` must be the public HTTPS origin reachable by crawlers. Persist
the entire data volume, including `.previews/` and its durable job markers.
The release image includes FFmpeg/ffprobe. Each preparation has bounded
subprocess output, threads, dimensions and wall time; failed new uploads are
removed, while backfill failures leave existing downloads intact.

Share HTML revalidates on a short cache lifetime; immutable media supports
HEAD, byte ranges, validators and cross-origin playback. Do not put login
pages, bot challenges or a `robots.txt` disallow in front of public share,
poster, preview or original URLs. If a platform cached an earlier failure,
use its preview refresh/debugger; test fresh media with a genuinely new path,
not only a query-string change.

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

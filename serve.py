#!/usr/bin/env python
"""Serve dl-video via web browser using textual-serve."""

import os
from textual_serve.server import Server

# Ensure PATH includes common locations for yt-dlp, node, etc.
env_path = os.environ.get("PATH", "")
extra_paths = [
    "/usr/local/bin",
    "/opt/homebrew/bin",
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.pyenv/shims"),
    os.path.expanduser("~/.nvm/versions/node/*/bin"),
]
for p in extra_paths:
    if p not in env_path:
        env_path = f"{p}:{env_path}"
os.environ["PATH"] = env_path

# Use uv run to ensure correct environment.
# The web TUI has no authentication: keep it on loopback (tailnet via `make serve-tailnet`).
# Behind a proxy, DL_VIDEO_SERVE_PUBLIC_URL is the URL browsers load assets/websocket from.
server = Server(
    "uv run python -m dl_video",
    host=os.environ.get("DL_VIDEO_SERVE_HOST", "127.0.0.1"),
    port=8000,
    public_url=os.environ.get("DL_VIDEO_SERVE_PUBLIC_URL") or None,
)
server.serve()

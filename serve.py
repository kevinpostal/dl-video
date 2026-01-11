#!/usr/bin/env python
"""Serve dl-video via web browser using textual-serve."""

import os
import subprocess
import sys
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

# Use uv run to ensure correct environment
server = Server(
    "uv run python -m dl_video",
    host="0.0.0.0",
    port=8000,
)
server.serve()

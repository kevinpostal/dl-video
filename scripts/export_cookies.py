#!/usr/bin/env python3
"""Export this machine's browser cookies for a few video sites as a Netscape
cookies.txt, for a dl-video server that has no browser (the Pi).

yt-dlp does the browser decryption (`--cookies-from-browser`); it writes the
whole jar when it exits, so the dump is filtered down to the requested domains
before anything leaves the machine. Usage:

    export_cookies.py --browser chrome --out cookies.txt [--domains a.com b.com]
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Sites dl-video history shows downloads from that gate content behind a login.
DEFAULT_DOMAINS = [
    "instagram.com", "facebook.com", "youtube.com", "reddit.com",
    "tiktok.com", "x.com", "twitter.com",
]
# Any URL works: the jar is saved on exit even when extraction fails.
PROBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def matches(host: str, domains: list[str]) -> bool:
    host = host.lstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--browser", default="chrome")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--domains", nargs="+", default=DEFAULT_DOMAINS)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "all.txt"
        subprocess.run(
            ["yt-dlp", "--cookies-from-browser", args.browser, "--cookies", str(dump),
             "--skip-download", "--no-warnings", "--quiet", "--print", "id", "--", PROBE_URL],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if not dump.is_file():
            print("yt-dlp did not write a cookie jar; is the browser profile readable?", file=sys.stderr)
            return 1
        kept = [
            line for line in dump.read_text().splitlines()
            if not line.startswith("#") and line.count("\t") >= 6
            and matches(line.split("\t", 1)[0], args.domains)
        ]

    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n# Exported by dl-video for: " + " ".join(args.domains) + "\n")
        f.write("\n".join(kept) + "\n")
    print(f"{len(kept)} cookies for {', '.join(args.domains)} -> {args.out}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())

.PHONY: help run serve serve-tailnet serve-tailnet-stop serve-api serve-api-tailnet serve-api-stop serve-api-install serve-api-uninstall pi-deploy pi-cookies pi-stop pi-logs test ios-e2e clean install dev container-pull container-check container-test run-container

.DEFAULT_GOAL := help

# Use bash for better compatibility
SHELL := /bin/bash

TAILSCALE := /Applications/Tailscale.app/Contents/MacOS/Tailscale

# Source uv env if available (for systems where uv is in ~/.local/bin)
UV := . $$HOME/.local/bin/env 2>/dev/null || true; uv

# Use external virtualenv (matching .envrc)
export UV_PROJECT_ENVIRONMENT := $(HOME)/.virtualenvs/dl-video

# Default container image
CONTAINER_IMAGE := linuxserver/ffmpeg:latest

# Show help
help:
	@echo "dl-video - Video downloader TUI"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  run              Run the app in terminal"
	@echo "  run-container    Run the app with container backend"
	@echo "  serve            Serve via web browser (http://127.0.0.1:8000)"
	@echo "  serve-tailnet    Serve the web TUI on the tailnet only (https://<mac>.ts.net)"
	@echo "  serve-tailnet-stop Stop the tailnet web TUI and its Tailscale serve"
	@echo "  serve-api        Run the iOS API server (http://127.0.0.1:8765)"
	@echo "  serve-api-tailnet Run the API server behind Tailscale HTTPS :8443"
	@echo "  serve-api-stop   Stop the API server and its Tailscale serve"
	@echo "  serve-api-install Run the API server at login (launchd) behind Tailscale :8443"
	@echo "  serve-api-uninstall Remove the launchd agent"
	@echo "  pi-deploy        Run the API server always-on on a Pi (PI_HOST=$(PI_HOST)) behind Tailscale :8443"
	@echo "  pi-cookies       Send this Mac's Chrome cookies for video sites to the Pi server"
	@echo "  pi-logs          Tail the Pi API server logs"
	@echo "  pi-stop          Stop the Pi API server and its Tailscale serve"
	@echo ""
	@echo "  install          Install dependencies (auto-installs uv if needed)"
	@echo "  dev              Install with dev dependencies"
	@echo "  test             Run tests"
	@echo "  test-cov         Run tests with coverage"
	@echo ""
	@echo "  app-build        Build containerized app (no local deps needed)"
	@echo "  app-run          Run containerized app (downloads to ~/Downloads)"
	@echo ""
	@echo "  container-pull   Pull the container image (for container backend)"
	@echo "  container-check  Check if Podman and image are available"
	@echo "  container-test   Test container execution (yt-dlp and ffmpeg)"
	@echo ""
	@echo "  clean            Clean cache files"
	@echo "  clean-thumbnails Clear thumbnail cache"
	@echo "  fmt              Format code with ruff"
	@echo "  lint             Lint code with ruff"

# Run the app locally in terminal
run:
	@$(UV) run python -m dl_video

# Run the app with container backend (sets env var)
run-container:
	@DL_VIDEO_BACKEND=container $(UV) run python -m dl_video

# Serve via web browser (loopback only; the web TUI has no authentication)
serve:
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@$(UV) run python serve.py

# Expose the web TUI on the tailnet (never public) over HTTPS :443, then run it
serve-tailnet:
	@$(TAILSCALE) serve --bg --https=443 http://127.0.0.1:8000
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@export DL_VIDEO_SERVE_PUBLIC_URL=https://$$($(TAILSCALE) status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'); \
		$(UV) run python serve.py

# Stop the tailnet web TUI and remove its Tailscale serve config
serve-tailnet-stop:
	@$(TAILSCALE) serve --https=443 off 2>/dev/null || true
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Run the API server for the iOS app (localhost only)
serve-api:
	@$(UV) run dl-video-server

# Expose the API server on the tailnet over HTTPS :8443, then run it
serve-api-tailnet:
	@$(TAILSCALE) serve --bg --https=8443 http://127.0.0.1:8765
	@$(UV) run dl-video-server

# Stop the API server and remove its Tailscale serve config
serve-api-stop: serve-api-uninstall
	@$(TAILSCALE) serve --https=8443 off 2>/dev/null || true
	@lsof -ti:8765 | xargs kill 2>/dev/null || true

LAUNCHD_LABEL := com.kevinpostal.dl-video-server
LAUNCHD_PLIST := $(HOME)/Library/LaunchAgents/$(LAUNCHD_LABEL).plist

# Keep the API server running across logins/crashes; the tailscale serve
# config set with --bg persists on its own.
serve-api-install:
	@$(UV) sync --inexact --quiet
	@lsof -ti:8765 | xargs kill 2>/dev/null || true
	@mkdir -p $(dir $(LAUNCHD_PLIST))
	@sed -e 's|@VENV@|$(UV_PROJECT_ENVIRONMENT)|g' -e 's|@HOME@|$(HOME)|g' scripts/dl-video-server.plist.in > $(LAUNCHD_PLIST)
	@launchctl bootout gui/$$(id -u)/$(LAUNCHD_LABEL) 2>/dev/null || true
	@chmod 600 $(HOME)/Library/Logs/dl-video-server.log 2>/dev/null || true
	@chmod 600 $(HOME)/.config/dl-video/*.json 2>/dev/null || true
	@launchctl bootstrap gui/$$(id -u) $(LAUNCHD_PLIST)
	@$(TAILSCALE) serve --bg --https=8443 http://127.0.0.1:8765
	@echo "Installed; logs in ~/Library/Logs/dl-video-server.log"

serve-api-uninstall:
	@launchctl bootout gui/$$(id -u)/$(LAUNCHD_LABEL) 2>/dev/null || true
	@rm -f $(LAUNCHD_PLIST)

# Always-on API server on a Linux box so the phone works while the Mac sleeps.
# Layout on the host: $(PI_DIR)/src (rsynced sources + compose.yml),
# $(PI_DIR)/config (tokens, config.json, cookies.txt, history), $(PI_DIR)/downloads.
PI_HOST ?= pi-gate
PI_DIR ?= /srv/dl-video
PI_CONFIG := {"download_dir": "/downloads", "auto_upload": true, "skip_conversion": false, "cookies_file": "/root/.config/dl-video/cookies.txt"}

pi-deploy:
	@ssh $(PI_HOST) 'sudo mkdir -p $(PI_DIR)/src $(PI_DIR)/config $(PI_DIR)/downloads && sudo chown -R $$USER $(PI_DIR) && chmod 700 $(PI_DIR)/config'
	@rsync -az --delete src pyproject.toml uv.lock README.md Containerfile deploy/pi/compose.yml $(PI_HOST):$(PI_DIR)/src/
	@# Same tokens as this Mac, so the phone only has to switch the server URL. Never overwritten.
	@for f in server_token upload_token; do \
		ssh $(PI_HOST) "test -s $(PI_DIR)/config/$$f" || scp -q $(HOME)/.config/dl-video/$$f $(PI_HOST):$(PI_DIR)/config/$$f; \
	done
	@ssh $(PI_HOST) 'test -s $(PI_DIR)/config/config.json || echo '"'"'$(PI_CONFIG)'"'"' > $(PI_DIR)/config/config.json; chmod 600 $(PI_DIR)/config/*'
	@# Build detached: an SSH drop mid-build (slow box) must not cancel it. tail --pid waits for it;
	@# build.rc carries the result (a still-running old container must not look like success).
	@ssh $(PI_HOST) 'cd $(PI_DIR)/src && rm -f ../build.rc && nohup sh -c "docker compose build -q && docker compose up -d --remove-orphans; echo \$$? > ../build.rc" > ../build.log 2>&1 & echo $$! > $(PI_DIR)/build.pid'
	@ssh $(PI_HOST) 'tail -f --pid=$$(cat $(PI_DIR)/build.pid) $(PI_DIR)/build.log; test "$$(cat $(PI_DIR)/build.rc 2>/dev/null)" = 0 || { echo "build failed:"; tail -20 $(PI_DIR)/build.log; exit 1; }'
	@ssh $(PI_HOST) 'sudo tailscale serve --bg --https=8443 http://127.0.0.1:8765 >/dev/null && sudo tailscale serve status'

# yt-dlp on the Pi has no browser to read cookies from; ship a filtered Netscape
# jar from this Mac's Chrome. Re-run when logins rotate (Instagram/YouTube do).
pi-cookies:
	@python3 scripts/export_cookies.py --browser chrome --out /tmp/dl-video-cookies.txt
	@scp -q /tmp/dl-video-cookies.txt $(PI_HOST):$(PI_DIR)/config/cookies.txt; rm -f /tmp/dl-video-cookies.txt
	@ssh $(PI_HOST) 'chmod 600 $(PI_DIR)/config/cookies.txt'

pi-logs:
	@ssh $(PI_HOST) 'docker logs --tail 100 -f dl-video-api'

pi-stop:
	@ssh $(PI_HOST) 'sudo tailscale serve --https=8443 off 2>/dev/null; cd $(PI_DIR)/src && docker compose down'

# Install dependencies (installs uv if missing)
install:
	@. $$HOME/.local/bin/env 2>/dev/null || true; \
	if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		. $$HOME/.local/bin/env; \
		if [ -f "$$HOME/.zshrc" ] && ! grep -q '.local/bin/env' "$$HOME/.zshrc" 2>/dev/null; then \
			echo '. "$$HOME/.local/bin/env"' >> "$$HOME/.zshrc"; \
			echo "Added uv to ~/.zshrc"; \
		elif [ -f "$$HOME/.bashrc" ] && ! grep -q '.local/bin/env' "$$HOME/.bashrc" 2>/dev/null; then \
			echo '. "$$HOME/.local/bin/env"' >> "$$HOME/.bashrc"; \
			echo "Added uv to ~/.bashrc"; \
		fi; \
	fi; \
	uv sync

# Install with dev dependencies
dev:
	@$(UV) sync --all-extras

# Run tests
test:
	@$(UV) run pytest

# iOS end-to-end tests: real share sheet / quick action in the Simulator → the
# running API server (make serve-api-install) → yt-dlp/ffmpeg. Server upload is
# switched off while it runs. Uses its own simulator so other projects' UI tests
# (which shut down / reset shared devices) can't interfere.
XCODE_DEV := /Applications/Xcode.app/Contents/Developer
IOS_SIM ?= dl-video E2E
IOS_SIM_TYPE ?= iPhone 17 Pro
IOS_DERIVED := /tmp/dlvideo-build
ios-e2e:
	@DEVELOPER_DIR=$(XCODE_DEV) xcrun simctl list devices available | grep -q "$(IOS_SIM) (" \
		|| DEVELOPER_DIR=$(XCODE_DEV) xcrun simctl create "$(IOS_SIM)" "$(IOS_SIM_TYPE)" >/dev/null
	@DEVELOPER_DIR=$(XCODE_DEV) xcrun simctl boot "$(IOS_SIM)" 2>/dev/null || true
	@cd ios && DEVELOPER_DIR=$(XCODE_DEV) /opt/homebrew/bin/xcodegen generate --quiet
	@cd ios && DEVELOPER_DIR=$(XCODE_DEV) xcodebuild -project DLVideo.xcodeproj -scheme DLVideoE2E \
		-destination 'platform=iOS Simulator,name=$(IOS_SIM)' -derivedDataPath $(IOS_DERIVED) \
		-allowProvisioningUpdates -quiet build-for-testing
	@DEVELOPER_DIR=$(XCODE_DEV) xcrun simctl install "$(IOS_SIM)" $(IOS_DERIVED)/Build/Products/Debug-iphonesimulator/DLVideo.app
	@cd ios && DEVELOPER_DIR=$(XCODE_DEV) \
		TEST_RUNNER_DLV_SERVER_URL=http://127.0.0.1:8765 \
		TEST_RUNNER_DLV_TOKEN=$$(cat $(HOME)/.config/dl-video/server_token) \
		xcodebuild -project DLVideo.xcodeproj -scheme DLVideoE2E \
		-destination 'platform=iOS Simulator,name=$(IOS_SIM)' -derivedDataPath $(IOS_DERIVED) \
		$(if $(E2E_ONLY),-only-testing:DLVideoE2ETests/ShareE2ETests/$(E2E_ONLY)) test-without-building

# Run tests with coverage
test-cov:
	@$(UV) run pytest --cov=dl_video

# Clean up cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .hypothesis .coverage htmlcov

# Clear thumbnail cache
clean-thumbnails:
	rm -rf ~/.config/dl-video/thumbnails/*.png

# Format code
fmt:
	@$(UV) run ruff format src tests

# Lint code
lint:
	@$(UV) run ruff check src tests

# Take a screenshot of the app (saves as SVG)
screenshot:
	@$(UV) run textual run --screenshot 3 dl_video.app:DLVideoApp
	@echo "Screenshot saved!"

# Record a demo GIF (requires vhs: brew install vhs)
demo:
	vhs demo.tape
	@echo "Demo GIF saved to demo.gif"

# Container-related targets

# Build the containerized app (entire app in container)
app-build:
	@echo "Building dl-video container image..."
	@podman build -t dl-video:latest -f Containerfile .

# Run the containerized app (entire app in container)
# Mounts ~/Downloads for output, runs with TTY for TUI
app-run:
	@podman run -it --rm \
		-v $(HOME)/Downloads:/downloads:z \
		-e TERM=$(TERM) \
		-e COLORTERM=$(COLORTERM) \
		dl-video:latest

# Run containerized app with custom download directory
# Usage: make app-run-dir DIR=/path/to/downloads
app-run-dir:
	@podman run -it --rm \
		-v $(DIR):/downloads:z \
		-e TERM=$(TERM) \
		-e COLORTERM=$(COLORTERM) \
		dl-video:latest

# Pull the container image
container-pull:
	@echo "Pulling $(CONTAINER_IMAGE) image..."
	@podman pull $(CONTAINER_IMAGE)

# Check if Podman and image are available
container-check:
	@echo "Checking Podman installation..."
	@podman --version || (echo "Podman not installed. Install with: brew install podman" && exit 1)
	@echo "Checking for $(CONTAINER_IMAGE) image..."
	@podman image exists $(CONTAINER_IMAGE) || (echo "Image not found. Run: make container-pull" && exit 1)
	@echo "Container environment ready!"

# Test container execution
container-test:
	@echo "Testing ffmpeg in container..."
	@podman run --rm $(CONTAINER_IMAGE) ffmpeg -version 2>&1 | head -1
	@echo "Testing ffprobe in container..."
	@podman run --rm $(CONTAINER_IMAGE) ffprobe -version 2>&1 | head -1
	@echo "Container tests passed!"

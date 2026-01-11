.PHONY: help run serve funnel funnel-stop test clean install dev container-pull container-check container-test run-container

.DEFAULT_GOAL := help

TAILSCALE := /Applications/Tailscale.app/Contents/MacOS/Tailscale

# Source uv env if available (for systems where uv is in ~/.local/bin)
UV := . $$HOME/.local/bin/env 2>/dev/null || true; uv

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
	@echo "  serve            Serve via web browser (http://0.0.0.0:8000)"
	@echo "  funnel           Start server with Tailscale Funnel (public URL)"
	@echo "  funnel-stop      Stop Tailscale Funnel"
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

# Serve via web browser (local network)
serve:
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@$(UV) run python serve.py

# Start Tailscale Funnel and serve
funnel:
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@$(TAILSCALE) funnel reset 2>/dev/null || true
	@$(TAILSCALE) funnel --bg 8000
	@echo ""
	@echo "Funnel started! Starting server..."
	@echo ""
	@$(UV) run python serve.py

# Stop Tailscale Funnel
funnel-stop:
	@$(TAILSCALE) funnel reset 2>/dev/null || true
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@echo "Funnel stopped"

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

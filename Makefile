.PHONY: help run serve funnel funnel-stop test clean install dev

.DEFAULT_GOAL := help

TAILSCALE := /Applications/Tailscale.app/Contents/MacOS/Tailscale

# Show help
help:
	@echo "dl-video - Video downloader TUI"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  run              Run the app in terminal"
	@echo "  serve            Serve via web browser (http://0.0.0.0:8000)"
	@echo "  funnel           Start server with Tailscale Funnel (public URL)"
	@echo "  funnel-stop      Stop Tailscale Funnel"
	@echo ""
	@echo "  install          Install dependencies (auto-installs uv if needed)"
	@echo "  dev              Install with dev dependencies"
	@echo "  test             Run tests"
	@echo "  test-cov         Run tests with coverage"
	@echo ""
	@echo "  clean            Clean cache files"
	@echo "  clean-thumbnails Clear thumbnail cache"
	@echo "  fmt              Format code with ruff"
	@echo "  lint             Lint code with ruff"

# Run the app locally in terminal
run:
	uv run python -m dl_video

# Serve via web browser (local network)
serve:
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	uv run python serve.py

# Start Tailscale Funnel and serve
funnel:
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@$(TAILSCALE) funnel reset 2>/dev/null || true
	@$(TAILSCALE) funnel --bg 8000
	@echo ""
	@echo "Funnel started! Starting server..."
	@echo ""
	uv run python serve.py

# Stop Tailscale Funnel
funnel-stop:
	@$(TAILSCALE) funnel reset 2>/dev/null || true
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@echo "Funnel stopped"

# Install dependencies (installs uv if missing)
install:
	@command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; . $$HOME/.local/bin/env; }
	@. $$HOME/.local/bin/env 2>/dev/null || true; uv sync

# Install with dev dependencies
dev:
	uv sync --all-extras

# Run tests
test:
	uv run pytest

# Run tests with coverage
test-cov:
	uv run pytest --cov=dl_video

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
	uv run ruff format src tests

# Lint code
lint:
	uv run ruff check src tests

# Take a screenshot of the app (saves as SVG)
screenshot:
	uv run textual run --screenshot 3 dl_video.app:DLVideoApp
	@echo "Screenshot saved!"

# Record a demo GIF (requires vhs: brew install vhs)
demo:
	vhs demo.tape
	@echo "Demo GIF saved to demo.gif"

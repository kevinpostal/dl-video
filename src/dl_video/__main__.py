"""Entry point for dl-video application."""

import sys


def main() -> None:
    """Main entry point for the dl-video application."""
    # Import here to avoid circular imports and speed up --help
    from dl_video.app import DLVideoApp

    # Support optional URL argument for non-interactive start
    url = sys.argv[1] if len(sys.argv) > 1 else None
    app = DLVideoApp(initial_url=url)
    app.run()


if __name__ == "__main__":
    main()

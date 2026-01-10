"""URL validation utility for video URLs."""

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of URL validation."""

    success: bool
    message: str


class URLValidator:
    """Validates video URLs for supported sites."""

    # Patterns for supported video sites (yt-dlp supports many more,
    # but these are the most common ones we explicitly validate)
    SUPPORTED_PATTERNS = [
        r"https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
        r"https?://youtu\.be/[\w-]+",
        r"https?://(www\.)?vimeo\.com/\d+",
        r"https?://(www\.)?twitter\.com/.+/status/\d+",
        r"https?://(www\.)?x\.com/.+/status/\d+",
        r"https?://(www\.)?twitch\.tv/.+",
        r"https?://(www\.)?dailymotion\.com/video/[\w-]+",
        r"https?://(www\.)?tiktok\.com/.+",
        r"https?://(www\.)?instagram\.com/(p|reel)/[\w-]+",
        r"https?://(www\.)?facebook\.com/.+/videos/\d+",
    ]

    def __init__(self) -> None:
        """Initialize the validator with compiled patterns."""
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.SUPPORTED_PATTERNS
        ]

    def validate(self, url: str) -> ValidationResult:
        """Validate URL format.

        Args:
            url: The URL string to validate.

        Returns:
            ValidationResult with success status and message.
        """
        if not url:
            return ValidationResult(success=False, message="URL cannot be empty")

        url = url.strip()

        if not url:
            return ValidationResult(success=False, message="URL cannot be empty")

        # Check basic URL format
        if not url.startswith(("http://", "https://")):
            return ValidationResult(
                success=False, message="URL must start with http:// or https://"
            )

        # Check against supported patterns
        for pattern in self._compiled_patterns:
            if pattern.match(url):
                return ValidationResult(success=True, message="Valid URL")

        # If no pattern matched, still allow it since yt-dlp supports many sites
        # but warn the user it's not a recognized pattern
        return ValidationResult(
            success=True,
            message="URL format not recognized, but will attempt download",
        )

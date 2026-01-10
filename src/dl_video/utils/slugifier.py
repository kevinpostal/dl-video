"""Slugifier utility for converting strings to filesystem-safe slugs."""

import re


class Slugifier:
    """Converts strings to filesystem-safe slugs."""

    def slugify(self, text: str) -> str:
        """Convert text to lowercase slug with underscores.

        - Converts to lowercase
        - Replaces non-alphanumeric characters with underscores
        - Strips leading/trailing underscores
        - Collapses multiple consecutive underscores into one

        Args:
            text: The input string to slugify.

        Returns:
            A filesystem-safe slug string.
        """
        # Convert to lowercase
        result = text.lower()

        # Replace non-alphanumeric characters with underscores
        result = re.sub(r"[^a-z0-9]", "_", result)

        # Collapse multiple consecutive underscores into one
        result = re.sub(r"_+", "_", result)

        # Strip leading and trailing underscores
        result = result.strip("_")

        return result

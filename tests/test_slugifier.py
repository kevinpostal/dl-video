"""Property-based tests for Slugifier.

Feature: dl-video-textual-overhaul
Property 2: Slugification Idempotence - slugify(slugify(x)) == slugify(x)
Property 3: Slugification Character Constraints - output contains only [a-z0-9_], no leading/trailing underscores
Validates: Requirements 2.4
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from dl_video.utils.slugifier import Slugifier


class TestSlugifierProperties:
    """Property-based tests for Slugifier."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.slugifier = Slugifier()

    @given(st.text())
    @settings(max_examples=100)
    def test_slugification_idempotence(self, text: str) -> None:
        """Property 2: Slugification Idempotence.

        For any string, applying slugify twice produces the same result
        as applying it once: slugify(slugify(x)) == slugify(x)

        **Validates: Requirements 2.4**
        """
        once = self.slugifier.slugify(text)
        twice = self.slugifier.slugify(once)
        assert once == twice, f"Idempotence failed: slugify('{text}') = '{once}', slugify('{once}') = '{twice}'"

    @given(st.text())
    @settings(max_examples=100)
    def test_slugification_character_constraints(self, text: str) -> None:
        """Property 3: Slugification Character Constraints.

        For any input string, the slugified output contains only lowercase
        letters, digits, and underscores, with no leading or trailing underscores.

        **Validates: Requirements 2.4**
        """
        result = self.slugifier.slugify(text)

        # Output should only contain [a-z0-9_]
        assert re.fullmatch(r"[a-z0-9_]*", result) is not None, (
            f"Invalid characters in slugified output: '{result}' from input '{text}'"
        )

        # No leading underscores (unless empty)
        if result:
            assert not result.startswith("_"), (
                f"Leading underscore in slugified output: '{result}' from input '{text}'"
            )

        # No trailing underscores (unless empty)
        if result:
            assert not result.endswith("_"), (
                f"Trailing underscore in slugified output: '{result}' from input '{text}'"
            )

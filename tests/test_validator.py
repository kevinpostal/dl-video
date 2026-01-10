"""Property-based tests for URLValidator.

Feature: dl-video-textual-overhaul
Property 1: URL Validation Consistency - same input always produces same result
Validates: Requirements 1.2, 1.3
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dl_video.utils.validator import URLValidator, ValidationResult


class TestURLValidatorProperties:
    """Property-based tests for URLValidator."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.validator = URLValidator()

    @given(st.text())
    @settings(max_examples=100)
    def test_url_validation_consistency(self, url: str) -> None:
        """Property 1: URL Validation Consistency.

        For any string input, the URLValidator returns a valid result,
        and the validation result is consistent across multiple calls
        with the same input.

        **Validates: Requirements 1.2, 1.3**
        """
        # Call validate multiple times with the same input
        result1 = self.validator.validate(url)
        result2 = self.validator.validate(url)
        result3 = self.validator.validate(url)

        # Results should be ValidationResult instances
        assert isinstance(result1, ValidationResult)
        assert isinstance(result2, ValidationResult)
        assert isinstance(result3, ValidationResult)

        # Results should be consistent
        assert result1.success == result2.success == result3.success, (
            f"Inconsistent success for URL '{url}': {result1.success}, {result2.success}, {result3.success}"
        )
        assert result1.message == result2.message == result3.message, (
            f"Inconsistent message for URL '{url}': {result1.message}, {result2.message}, {result3.message}"
        )

    @given(st.text())
    @settings(max_examples=100)
    def test_validation_result_has_message(self, url: str) -> None:
        """Validation result always has a non-empty message.

        **Validates: Requirements 1.2, 1.3**
        """
        result = self.validator.validate(url)

        # Message should always be a non-empty string
        assert isinstance(result.message, str)
        assert len(result.message) > 0, f"Empty message for URL '{url}'"

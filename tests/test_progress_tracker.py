"""Property-based tests for progress tracking.

**Property 6: Progress Value Bounds** - progress always 0-100, monotonically non-decreasing
**Validates: Requirements 3.1, 3.2, 4.3, 5.3**
"""

import pytest
from hypothesis import given, strategies as st, assume, settings

from dl_video.progress_tracker import (
    ProgressBoundsError,
    ProgressRegressionError,
    ProgressTracker,
)


# Strategy for valid progress values (0-100)
valid_progress = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# Strategy for invalid progress values (outside 0-100)
invalid_progress_low = st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False)
invalid_progress_high = st.floats(min_value=100.001, allow_nan=False, allow_infinity=False)


class TestProgressTrackerProperties:
    """Property-based tests for ProgressTracker."""

    @given(st.lists(valid_progress, min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_progress_bounds_always_valid(
        self, progress_values: list[float]
    ) -> None:
        """
        **Property 6: Progress Value Bounds**
        
        *For any* sequence of valid progress updates (0-100), the tracker SHALL
        accept all values that are within bounds AND monotonically non-decreasing.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        # Sort to ensure monotonicity
        sorted_values = sorted(progress_values)
        
        for value in sorted_values:
            # Should not raise for valid, monotonic values
            tracker.update(value)
            
            # Current value should be within bounds
            assert 0 <= tracker.current <= 100
            assert tracker.current == value

    @given(invalid_progress_low)
    @settings(max_examples=100)
    def test_progress_rejects_values_below_zero(self, value: float) -> None:
        """
        *For any* progress value below 0, the tracker SHALL reject it with
        ProgressBoundsError.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        with pytest.raises(ProgressBoundsError) as exc_info:
            tracker.update(value)
        
        assert exc_info.value.value == value
        # Progress should remain unchanged
        assert tracker.current == 0.0

    @given(invalid_progress_high)
    @settings(max_examples=100)
    def test_progress_rejects_values_above_hundred(self, value: float) -> None:
        """
        *For any* progress value above 100, the tracker SHALL reject it with
        ProgressBoundsError.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        with pytest.raises(ProgressBoundsError) as exc_info:
            tracker.update(value)
        
        assert exc_info.value.value == value
        # Progress should remain unchanged
        assert tracker.current == 0.0

    @given(
        st.floats(min_value=50.0, max_value=100.0, allow_nan=False),
        st.floats(min_value=0.0, max_value=49.9, allow_nan=False),
    )
    @settings(max_examples=100)
    def test_progress_rejects_regression(
        self, first_value: float, second_value: float
    ) -> None:
        """
        *For any* two progress values where the second is less than the first,
        the tracker SHALL reject the second value with ProgressRegressionError.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        assume(second_value < first_value)
        
        tracker = ProgressTracker()
        tracker.update(first_value)
        
        with pytest.raises(ProgressRegressionError) as exc_info:
            tracker.update(second_value)
        
        assert exc_info.value.previous == first_value
        assert exc_info.value.current == second_value
        # Progress should remain at first value
        assert tracker.current == first_value

    @given(valid_progress)
    @settings(max_examples=100)
    def test_progress_allows_equal_values(self, value: float) -> None:
        """
        *For any* valid progress value, updating with the same value twice
        SHALL be allowed (monotonically non-decreasing includes equal).
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        tracker.update(value)
        tracker.update(value)  # Same value should be allowed
        
        assert tracker.current == value

    @given(st.lists(valid_progress, min_size=2, max_size=20))
    @settings(max_examples=100)
    def test_history_is_monotonically_non_decreasing(
        self, progress_values: list[float]
    ) -> None:
        """
        *For any* sequence of valid progress updates, the history SHALL be
        monotonically non-decreasing.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        # Sort to ensure monotonicity
        sorted_values = sorted(progress_values)
        
        for value in sorted_values:
            tracker.update(value)
        
        history = tracker.history
        
        # Verify monotonicity
        for i in range(1, len(history)):
            assert history[i] >= history[i - 1], (
                f"History not monotonic: {history[i-1]} > {history[i]}"
            )

    @given(valid_progress)
    @settings(max_examples=100)
    def test_validate_bounds_consistency(self, value: float) -> None:
        """
        *For any* value, validate_bounds() SHALL return True if and only if
        the value is in [0, 100].
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        
        # Valid values should pass validation
        assert tracker.validate_bounds(value) is True

    @given(invalid_progress_low)
    @settings(max_examples=100)
    def test_validate_bounds_rejects_low(self, value: float) -> None:
        """
        *For any* value below 0, validate_bounds() SHALL return False.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        assert tracker.validate_bounds(value) is False

    @given(invalid_progress_high)
    @settings(max_examples=100)
    def test_validate_bounds_rejects_high(self, value: float) -> None:
        """
        *For any* value above 100, validate_bounds() SHALL return False.
        
        **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
        """
        tracker = ProgressTracker()
        assert tracker.validate_bounds(value) is False

    def test_phase_reset_allows_new_sequence(self) -> None:
        """Test that starting a new phase resets progress to 0."""
        tracker = ProgressTracker()
        
        tracker.update(50.0)
        tracker.update(75.0)
        
        # Start new phase
        tracker.start_phase("downloading")
        
        # Progress should be reset to 0
        assert tracker.current == 0.0
        assert tracker.phase == "downloading"
        
        # Should be able to update from 0 again
        tracker.update(25.0)
        assert tracker.current == 25.0

    def test_complete_phase_sets_to_hundred(self) -> None:
        """Test that complete_phase() sets progress to 100."""
        tracker = ProgressTracker()
        
        tracker.update(50.0)
        tracker.complete_phase()
        
        assert tracker.current == 100.0
        assert tracker.is_complete()

    def test_is_complete_returns_true_at_hundred(self) -> None:
        """Test is_complete() returns True when progress is 100."""
        tracker = ProgressTracker()
        
        assert not tracker.is_complete()
        
        tracker.update(99.9)
        assert not tracker.is_complete()
        
        tracker.update(100.0)
        assert tracker.is_complete()

    def test_reset_clears_all_state(self) -> None:
        """Test that reset() clears all state."""
        tracker = ProgressTracker()
        
        tracker.start_phase("downloading")
        tracker.update(75.0)
        
        tracker.reset()
        
        assert tracker.current == 0.0
        assert tracker.phase == "idle"
        assert tracker.history == [0.0]

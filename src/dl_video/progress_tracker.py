"""Progress tracking for operations."""

from dataclasses import dataclass, field


class ProgressBoundsError(Exception):
    """Exception raised when progress value is out of bounds."""

    def __init__(self, value: float) -> None:
        self.value = value
        super().__init__(f"Progress value {value} is out of bounds [0, 100]")


class ProgressRegressionError(Exception):
    """Exception raised when progress decreases (non-monotonic)."""

    def __init__(self, previous: float, current: float) -> None:
        self.previous = previous
        self.current = current
        super().__init__(f"Progress decreased from {previous} to {current}")


@dataclass
class ProgressTracker:
    """Tracks progress for an operation phase.
    
    Ensures progress values are:
    - Within bounds [0, 100]
    - Monotonically non-decreasing within a phase
    """

    _current: float = 0.0
    _history: list[float] = field(default_factory=list)
    _phase: str = "idle"

    def __post_init__(self) -> None:
        """Initialize history with starting value."""
        self._history = [0.0]

    @property
    def current(self) -> float:
        """Get the current progress value."""
        return self._current

    @property
    def phase(self) -> str:
        """Get the current phase name."""
        return self._phase

    @property
    def history(self) -> list[float]:
        """Get the progress history."""
        return self._history.copy()

    def update(self, value: float) -> None:
        """Update the progress value.

        Args:
            value: New progress value (0-100).

        Raises:
            ProgressBoundsError: If value is outside [0, 100].
            ProgressRegressionError: If value is less than current progress.
        """
        # Validate bounds
        if value < 0 or value > 100:
            raise ProgressBoundsError(value)

        # Validate monotonicity (allow equal values)
        if value < self._current:
            raise ProgressRegressionError(self._current, value)

        self._current = value
        self._history.append(value)

    def start_phase(self, phase: str) -> None:
        """Start a new phase, resetting progress to 0.

        Args:
            phase: Name of the new phase.
        """
        self._phase = phase
        self._current = 0.0
        self._history = [0.0]

    def complete_phase(self) -> None:
        """Mark the current phase as complete (progress = 100)."""
        if self._current < 100:
            self._current = 100.0
            self._history.append(100.0)

    def reset(self) -> None:
        """Reset the tracker to initial state."""
        self._current = 0.0
        self._history = [0.0]
        self._phase = "idle"

    def is_complete(self) -> bool:
        """Check if progress is at 100%.

        Returns:
            True if progress is 100%, False otherwise.
        """
        return self._current >= 100.0

    def validate_bounds(self, value: float) -> bool:
        """Check if a value is within valid bounds.

        Args:
            value: Value to check.

        Returns:
            True if value is in [0, 100], False otherwise.
        """
        return 0 <= value <= 100

    def validate_monotonic(self, value: float) -> bool:
        """Check if a value maintains monotonicity.

        Args:
            value: Value to check.

        Returns:
            True if value >= current progress, False otherwise.
        """
        return value >= self._current

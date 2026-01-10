"""State machine for operation state transitions."""

from dl_video.models import OperationState


class InvalidStateTransition(Exception):
    """Exception raised when an invalid state transition is attempted."""

    def __init__(self, from_state: OperationState, to_state: OperationState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition from {from_state.value} to {to_state.value}")


# Valid state transitions
# IDLE -> FETCHING_METADATA (start operation)
# FETCHING_METADATA -> DOWNLOADING (metadata fetched)
# DOWNLOADING -> CONVERTING (download complete)
# DOWNLOADING -> UPLOADING (skip conversion)
# DOWNLOADING -> COMPLETED (skip conversion and upload)
# CONVERTING -> UPLOADING (conversion complete)
# CONVERTING -> COMPLETED (skip upload)
# UPLOADING -> COMPLETED (upload complete)
# Any active state -> CANCELLED (user cancellation)
# Any active state -> ERROR (error occurred)
# CANCELLED -> IDLE (reset)
# ERROR -> IDLE (reset)
# COMPLETED -> IDLE (reset)

VALID_TRANSITIONS: dict[OperationState, set[OperationState]] = {
    OperationState.IDLE: {OperationState.FETCHING_METADATA},
    OperationState.FETCHING_METADATA: {
        OperationState.DOWNLOADING,
        OperationState.CANCELLED,
        OperationState.ERROR,
    },
    OperationState.DOWNLOADING: {
        OperationState.CONVERTING,
        OperationState.UPLOADING,
        OperationState.COMPLETED,
        OperationState.CANCELLED,
        OperationState.ERROR,
    },
    OperationState.CONVERTING: {
        OperationState.UPLOADING,
        OperationState.COMPLETED,
        OperationState.CANCELLED,
        OperationState.ERROR,
    },
    OperationState.UPLOADING: {
        OperationState.COMPLETED,
        OperationState.CANCELLED,
        OperationState.ERROR,
    },
    OperationState.COMPLETED: {OperationState.IDLE},
    OperationState.CANCELLED: {OperationState.IDLE},
    OperationState.ERROR: {OperationState.IDLE},
}


class OperationStateMachine:
    """State machine for managing operation state transitions."""

    def __init__(self) -> None:
        """Initialize the state machine in IDLE state."""
        self._state = OperationState.IDLE
        self._history: list[OperationState] = [OperationState.IDLE]

    @property
    def state(self) -> OperationState:
        """Get the current state."""
        return self._state

    @property
    def history(self) -> list[OperationState]:
        """Get the state transition history."""
        return self._history.copy()

    def can_transition_to(self, new_state: OperationState) -> bool:
        """Check if transition to new state is valid.

        Args:
            new_state: The state to transition to.

        Returns:
            True if transition is valid, False otherwise.
        """
        valid_next_states = VALID_TRANSITIONS.get(self._state, set())
        return new_state in valid_next_states

    def transition_to(self, new_state: OperationState) -> None:
        """Transition to a new state.

        Args:
            new_state: The state to transition to.

        Raises:
            InvalidStateTransition: If the transition is not valid.
        """
        if not self.can_transition_to(new_state):
            raise InvalidStateTransition(self._state, new_state)

        self._state = new_state
        self._history.append(new_state)

    def reset(self) -> None:
        """Reset the state machine to IDLE state."""
        if self._state in {
            OperationState.COMPLETED,
            OperationState.CANCELLED,
            OperationState.ERROR,
        }:
            self._state = OperationState.IDLE
            self._history.append(OperationState.IDLE)
        elif self._state == OperationState.IDLE:
            pass  # Already idle
        else:
            raise InvalidStateTransition(self._state, OperationState.IDLE)

    def is_active(self) -> bool:
        """Check if an operation is currently active.

        Returns:
            True if in an active state, False otherwise.
        """
        return self._state in {
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CONVERTING,
            OperationState.UPLOADING,
        }

    def is_terminal(self) -> bool:
        """Check if in a terminal state.

        Returns:
            True if in a terminal state, False otherwise.
        """
        return self._state in {
            OperationState.COMPLETED,
            OperationState.CANCELLED,
            OperationState.ERROR,
        }

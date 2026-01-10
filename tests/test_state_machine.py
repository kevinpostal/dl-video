"""Property-based tests for state machine transitions.

**Property 5: Operation State Transitions** - only valid state paths allowed
**Validates: Requirements 3.1, 4.2, 5.3, 8.2**
"""

import pytest
from hypothesis import given, strategies as st, assume, settings

from dl_video.models import OperationState
from dl_video.state_machine import (
    InvalidStateTransition,
    OperationStateMachine,
    VALID_TRANSITIONS,
)


# Strategy for generating operation states
state_strategy = st.sampled_from(list(OperationState))


class TestOperationStateMachineProperties:
    """Property-based tests for OperationStateMachine."""

    @given(st.lists(state_strategy, min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_state_transitions_only_valid_paths(
        self, state_sequence: list[OperationState]
    ) -> None:
        """
        **Property 5: Operation State Transitions**
        
        *For any* sequence of state transitions, the state machine SHALL only
        allow transitions through valid paths. Invalid transitions SHALL raise
        InvalidStateTransition.
        
        **Validates: Requirements 3.1, 4.2, 5.3, 8.2**
        """
        sm = OperationStateMachine()
        
        for target_state in state_sequence:
            current_state = sm.state
            valid_next_states = VALID_TRANSITIONS.get(current_state, set())
            
            if target_state in valid_next_states:
                # Valid transition should succeed
                sm.transition_to(target_state)
                assert sm.state == target_state
            else:
                # Invalid transition should raise exception
                with pytest.raises(InvalidStateTransition) as exc_info:
                    sm.transition_to(target_state)
                assert exc_info.value.from_state == current_state
                assert exc_info.value.to_state == target_state
                # State should remain unchanged
                assert sm.state == current_state

    @given(state_strategy)
    @settings(max_examples=100)
    def test_can_transition_to_consistency(self, target_state: OperationState) -> None:
        """
        *For any* target state, can_transition_to() SHALL return True if and only
        if transition_to() would succeed without raising an exception.
        
        **Validates: Requirements 3.1, 4.2, 5.3, 8.2**
        """
        sm = OperationStateMachine()
        
        can_transition = sm.can_transition_to(target_state)
        
        if can_transition:
            # Should not raise
            sm.transition_to(target_state)
            assert sm.state == target_state
        else:
            # Should raise
            with pytest.raises(InvalidStateTransition):
                sm.transition_to(target_state)

    def test_valid_workflow_path_download_convert_upload(self) -> None:
        """Test the complete valid workflow path: IDLE -> ... -> COMPLETED."""
        sm = OperationStateMachine()
        
        # Valid complete workflow
        assert sm.state == OperationState.IDLE
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        assert sm.state == OperationState.FETCHING_METADATA
        
        sm.transition_to(OperationState.DOWNLOADING)
        assert sm.state == OperationState.DOWNLOADING
        
        sm.transition_to(OperationState.CONVERTING)
        assert sm.state == OperationState.CONVERTING
        
        sm.transition_to(OperationState.UPLOADING)
        assert sm.state == OperationState.UPLOADING
        
        sm.transition_to(OperationState.COMPLETED)
        assert sm.state == OperationState.COMPLETED
        
        # Can reset to IDLE
        sm.reset()
        assert sm.state == OperationState.IDLE

    def test_valid_workflow_path_skip_conversion(self) -> None:
        """Test workflow path skipping conversion."""
        sm = OperationStateMachine()
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        sm.transition_to(OperationState.DOWNLOADING)
        sm.transition_to(OperationState.UPLOADING)  # Skip conversion
        sm.transition_to(OperationState.COMPLETED)
        
        assert sm.state == OperationState.COMPLETED

    def test_valid_workflow_path_skip_upload(self) -> None:
        """Test workflow path skipping upload."""
        sm = OperationStateMachine()
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        sm.transition_to(OperationState.DOWNLOADING)
        sm.transition_to(OperationState.CONVERTING)
        sm.transition_to(OperationState.COMPLETED)  # Skip upload
        
        assert sm.state == OperationState.COMPLETED

    def test_cancellation_from_any_active_state(self) -> None:
        """Test that cancellation is valid from any active state."""
        active_states = [
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CONVERTING,
            OperationState.UPLOADING,
        ]
        
        for active_state in active_states:
            sm = OperationStateMachine()
            
            # Get to the active state
            if active_state == OperationState.FETCHING_METADATA:
                sm.transition_to(OperationState.FETCHING_METADATA)
            elif active_state == OperationState.DOWNLOADING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
            elif active_state == OperationState.CONVERTING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
                sm.transition_to(OperationState.CONVERTING)
            elif active_state == OperationState.UPLOADING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
                sm.transition_to(OperationState.UPLOADING)
            
            # Should be able to cancel
            assert sm.can_transition_to(OperationState.CANCELLED)
            sm.transition_to(OperationState.CANCELLED)
            assert sm.state == OperationState.CANCELLED

    def test_error_from_any_active_state(self) -> None:
        """Test that error is valid from any active state."""
        active_states = [
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CONVERTING,
            OperationState.UPLOADING,
        ]
        
        for active_state in active_states:
            sm = OperationStateMachine()
            
            # Get to the active state
            if active_state == OperationState.FETCHING_METADATA:
                sm.transition_to(OperationState.FETCHING_METADATA)
            elif active_state == OperationState.DOWNLOADING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
            elif active_state == OperationState.CONVERTING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
                sm.transition_to(OperationState.CONVERTING)
            elif active_state == OperationState.UPLOADING:
                sm.transition_to(OperationState.FETCHING_METADATA)
                sm.transition_to(OperationState.DOWNLOADING)
                sm.transition_to(OperationState.UPLOADING)
            
            # Should be able to transition to error
            assert sm.can_transition_to(OperationState.ERROR)
            sm.transition_to(OperationState.ERROR)
            assert sm.state == OperationState.ERROR

    def test_history_tracks_all_transitions(self) -> None:
        """Test that history correctly tracks all state transitions."""
        sm = OperationStateMachine()
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        sm.transition_to(OperationState.DOWNLOADING)
        sm.transition_to(OperationState.CANCELLED)
        sm.reset()
        
        expected_history = [
            OperationState.IDLE,
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CANCELLED,
            OperationState.IDLE,
        ]
        
        assert sm.history == expected_history

    def test_is_active_returns_true_for_active_states(self) -> None:
        """Test is_active() returns True for active states."""
        sm = OperationStateMachine()
        
        assert not sm.is_active()  # IDLE is not active
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        assert sm.is_active()
        
        sm.transition_to(OperationState.DOWNLOADING)
        assert sm.is_active()
        
        sm.transition_to(OperationState.CONVERTING)
        assert sm.is_active()
        
        sm.transition_to(OperationState.UPLOADING)
        assert sm.is_active()
        
        sm.transition_to(OperationState.COMPLETED)
        assert not sm.is_active()  # COMPLETED is not active

    def test_is_terminal_returns_true_for_terminal_states(self) -> None:
        """Test is_terminal() returns True for terminal states."""
        sm = OperationStateMachine()
        
        assert not sm.is_terminal()  # IDLE is not terminal
        
        sm.transition_to(OperationState.FETCHING_METADATA)
        assert not sm.is_terminal()
        
        sm.transition_to(OperationState.CANCELLED)
        assert sm.is_terminal()
        
        sm.reset()
        sm.transition_to(OperationState.FETCHING_METADATA)
        sm.transition_to(OperationState.ERROR)
        assert sm.is_terminal()
        
        sm.reset()
        sm.transition_to(OperationState.FETCHING_METADATA)
        sm.transition_to(OperationState.DOWNLOADING)
        sm.transition_to(OperationState.COMPLETED)
        assert sm.is_terminal()

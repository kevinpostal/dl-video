"""Snapshot tests for dl-video UI components."""

import pytest
from pathlib import Path

from textual.pilot import Pilot

# Import app and components
from dl_video.app import DLVideoApp
from dl_video.models import Config


class TestAppSnapshots:
    """Snapshot tests for the main application."""

    @pytest.fixture
    def app(self) -> DLVideoApp:
        """Create app instance for testing."""
        return DLVideoApp()

    async def test_initial_state(self, snap_compare):
        """Test the initial app state renders correctly."""
        assert snap_compare(DLVideoApp())

    async def test_with_url_input(self, snap_compare):
        """Test app with a URL entered."""
        async def setup(pilot: Pilot):
            await pilot.press("tab")  # Focus URL input
            await pilot.press(*"https://youtube.com/watch?v=test")
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)

    async def test_settings_expanded(self, snap_compare):
        """Test app with settings panel expanded."""
        async def setup(pilot: Pilot):
            # Open settings via command palette
            await pilot.press("ctrl+p")
            await pilot.press(*"settings")
            await pilot.press("enter")
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)


class TestInputFormSnapshots:
    """Snapshot tests for the input form component."""

    async def test_empty_form(self, snap_compare):
        """Test empty input form."""
        assert snap_compare(DLVideoApp())

    async def test_valid_url(self, snap_compare):
        """Test form with valid URL showing success state."""
        async def setup(pilot: Pilot):
            url_input = pilot.app.query_one("#url-input")
            url_input.value = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)

    async def test_invalid_url(self, snap_compare):
        """Test form with invalid URL showing error state."""
        async def setup(pilot: Pilot):
            url_input = pilot.app.query_one("#url-input")
            url_input.value = "not-a-valid-url"
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)

    async def test_filename_field_visible(self, snap_compare):
        """Test form with custom filename field expanded."""
        async def setup(pilot: Pilot):
            toggle = pilot.app.query_one("#filename-toggle")
            await pilot.click(toggle)
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)


class TestLogHistoryPanelSnapshots:
    """Snapshot tests for the log/history panel."""

    async def test_log_tab(self, snap_compare):
        """Test log tab view."""
        async def setup(pilot: Pilot):
            log_panel = pilot.app.query_one("LogHistoryPanel")
            log_panel.log_info("Test info message")
            log_panel.log_success("Test success message")
            log_panel.log_warning("Test warning message")
            log_panel.log_error("Test error message")
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)

    async def test_history_tab(self, snap_compare):
        """Test history tab view."""
        async def setup(pilot: Pilot):
            # Switch to history tab
            tabs = pilot.app.query_one("TabbedContent")
            tabs.active = "history-tab"
            await pilot.pause()
        
        assert snap_compare(DLVideoApp(), run_before=setup)

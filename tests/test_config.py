"""Property-based tests for ConfigManager.

Feature: dl-video-textual-overhaul
Property 4: Configuration Round-Trip - save then load produces equivalent Config
Validates: Requirements 10.1, 10.2
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dl_video.models import Config
from dl_video.utils.config import ConfigManager


# Strategy for generating valid Config objects
config_strategy = st.builds(
    Config,
    download_dir=st.builds(
        Path,
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-/"),
            min_size=1,
            max_size=50,
        ).map(lambda s: f"/tmp/{s}"),
    ),
    auto_upload=st.booleans(),
    skip_conversion=st.booleans(),
)


class TestConfigManagerProperties:
    """Property-based tests for ConfigManager."""

    @given(config_strategy)
    @settings(max_examples=100)
    def test_configuration_round_trip(self, config: Config) -> None:
        """Property 4: Configuration Round-Trip.

        For any valid Config object, saving it to disk and loading it back
        produces an equivalent Config object.

        **Validates: Requirements 10.1, 10.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            manager = ConfigManager(config_path=config_path)

            # Save the config
            manager.save(config)

            # Load it back
            loaded_config = manager.load()

            # Verify equivalence
            assert loaded_config.download_dir == config.download_dir, (
                f"download_dir mismatch: expected {config.download_dir}, got {loaded_config.download_dir}"
            )
            assert loaded_config.auto_upload == config.auto_upload, (
                f"auto_upload mismatch: expected {config.auto_upload}, got {loaded_config.auto_upload}"
            )
            assert loaded_config.skip_conversion == config.skip_conversion, (
                f"skip_conversion mismatch: expected {config.skip_conversion}, got {loaded_config.skip_conversion}"
            )

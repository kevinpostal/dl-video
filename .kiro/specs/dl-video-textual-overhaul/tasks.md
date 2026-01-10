# Implementation Plan: dl-video Textual Overhaul

## Overview

This plan transforms the `dl-video` bash script into a Python TUI application using Textual. Tasks are ordered to build incrementally, with core utilities first, then services, then UI components, and finally integration.

## Tasks

- [x] 1. Set up project structure and dependencies
  - Create Python package structure with `src/dl_video/`
  - Create `pyproject.toml` with dependencies (textual, httpx, hypothesis)
  - Create entry point script
  - _Requirements: N/A (setup)_

- [x] 2. Implement utility modules
  - [x] 2.1 Implement Slugifier class
    - Create `src/dl_video/utils/slugifier.py`
    - Implement `slugify()` method: lowercase, replace non-alphanumeric with underscores, strip leading/trailing underscores
    - _Requirements: 2.4_
  - [x] 2.2 Write property tests for Slugifier
    - **Property 2: Slugification Idempotence** - slugify(slugify(x)) == slugify(x)
    - **Property 3: Slugification Character Constraints** - output contains only [a-z0-9_], no leading/trailing underscores
    - **Validates: Requirements 2.4**
  - [x] 2.3 Implement URLValidator class
    - Create `src/dl_video/utils/validator.py`
    - Implement URL pattern matching for supported sites
    - Return ValidationResult with success/failure and message
    - _Requirements: 1.2, 1.3_
  - [x] 2.4 Write property tests for URLValidator
    - **Property 1: URL Validation Consistency** - same input always produces same result
    - **Validates: Requirements 1.2, 1.3**

- [x] 3. Implement data models and configuration
  - [x] 3.1 Create data models
    - Create `src/dl_video/models.py`
    - Implement OperationState enum, VideoMetadata, Config, OperationResult dataclasses
    - _Requirements: 3.1, 4.2, 5.3, 8.2_
  - [x] 3.2 Implement ConfigManager
    - Create `src/dl_video/utils/config.py`
    - Implement load/save methods with JSON serialization
    - Handle missing config file with defaults
    - _Requirements: 10.1, 10.2_
  - [x] 3.3 Write property tests for ConfigManager
    - **Property 4: Configuration Round-Trip** - save then load produces equivalent Config
    - **Validates: Requirements 10.1, 10.2**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement service layer
  - [x] 5.1 Implement VideoDownloader service
    - Create `src/dl_video/services/downloader.py`
    - Implement `get_metadata()` using yt-dlp subprocess
    - Implement `download()` with progress parsing from yt-dlp output
    - Support cancellation via asyncio
    - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4_
  - [x] 5.2 Implement VideoConverter service
    - Create `src/dl_video/services/converter.py`
    - Implement `convert()` using ffmpeg subprocess
    - Parse ffmpeg progress output for progress reporting
    - Support cancellation
    - _Requirements: 4.2, 4.3, 4.4, 4.5_
  - [x] 5.3 Implement FileUploader service
    - Create `src/dl_video/services/uploader.py`
    - Implement `upload()` using httpx with progress callback
    - Handle upload errors and return URL
    - _Requirements: 5.3, 5.4, 5.5_
  - [x] 5.4 Write unit tests for services
    - Test VideoDownloader with mocked subprocess
    - Test VideoConverter with mocked subprocess
    - Test FileUploader with mocked HTTP responses
    - _Requirements: 3.4, 4.5, 5.5_

- [x] 6. Implement UI components
  - [ ] 6.1 Create InputForm component
    - Create `src/dl_video/components/input_form.py`
    - Implement URL input with validation feedback
    - Implement optional filename input
    - Implement download button with enabled/disabled state
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.3_
  - [ ] 6.2 Create ProgressPanel component
    - Create `src/dl_video/components/progress_panel.py`
    - Implement progress bar with percentage display
    - Implement status label for current operation
    - Implement cancel button (enabled during operations)
    - _Requirements: 3.1, 3.2, 4.3, 5.3, 8.1_
  - [ ] 6.3 Create SettingsPanel component
    - Create `src/dl_video/components/settings_panel.py`
    - Implement auto-upload toggle switch
    - Implement skip-conversion toggle switch
    - Implement download directory input
    - _Requirements: 4.1, 5.1, 10.3, 10.4_
  - [ ] 6.4 Create LogPanel component
    - Create `src/dl_video/components/log_panel.py`
    - Implement RichLog with colored message types
    - Implement log_info, log_success, log_warning, log_error methods
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement main application
  - [x] 8.1 Create main App class
    - Create `src/dl_video/app.py`
    - Compose all UI components
    - Define keybindings (Ctrl+Q, Escape, Tab navigation)
    - Implement action handlers
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 8.2 Implement download workflow worker
    - Create async worker for download → convert → upload pipeline
    - Implement progress callbacks to update UI
    - Handle state transitions (IDLE → DOWNLOADING → CONVERTING → UPLOADING → COMPLETED)
    - _Requirements: 3.1, 4.2, 5.3_
  - [x] 8.3 Write property tests for state transitions
    - **Property 5: Operation State Transitions** - only valid state paths allowed
    - **Validates: Requirements 3.1, 4.2, 5.3, 8.2**
  - [x] 8.4 Write property tests for progress bounds
    - **Property 6: Progress Value Bounds** - progress always 0-100, monotonically non-decreasing
    - **Validates: Requirements 3.1, 3.2, 4.3, 5.3**
  - [x] 8.5 Implement cancellation handling
    - Wire cancel button to worker cancellation
    - Clean up temporary files on cancel
    - Return to input state after cancel
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 8.6 Implement file overwrite dialog
    - Create confirmation modal for existing files
    - Handle confirm/cancel responses
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 9. Implement clipboard and file operations
  - [x] 9.1 Implement clipboard copy
    - Copy upload URL to clipboard on success
    - Use pyperclip or platform-specific method
    - _Requirements: 5.4_
  - [x] 9.2 Implement open folder action
    - Open download directory in file manager after completion
    - Use platform-specific open command
    - _Requirements: N/A (feature parity with original)_

- [x] 10. Create application CSS styling
  - Create `src/dl_video/app.tcss`
  - Style all components for consistent appearance
  - Ensure proper layout and spacing
  - _Requirements: 9.4_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Create entry point and packaging
  - [x] 12.1 Create CLI entry point
    - Create `src/dl_video/__main__.py`
    - Support optional URL argument for non-interactive start
    - _Requirements: N/A (usability)_
  - [x] 12.2 Update pyproject.toml scripts
    - Add `dl-video` console script entry point
    - _Requirements: N/A (packaging)_

## Notes

- All tasks are required including property-based tests
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases

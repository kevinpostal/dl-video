# Requirements Document

## Introduction

This document specifies the requirements for overhauling the `dl-video` bash script into a modern Python TUI application using the Textual framework. The new application will provide an interactive terminal user interface for downloading videos from various platforms, converting them with ffmpeg, and optionally uploading to hardfiles.org.

## Glossary

- **Application**: The dl-video TUI application built with Textual
- **Video_Downloader**: The component responsible for downloading videos using yt-dlp
- **Video_Converter**: The component responsible for converting videos using ffmpeg
- **File_Uploader**: The component responsible for uploading files to hardfiles.org
- **Progress_Display**: The UI component showing download/conversion/upload progress
- **URL_Input**: The input field for entering video URLs
- **Filename_Input**: The input field for custom filenames
- **Settings_Panel**: The UI section containing configuration options

## Requirements

### Requirement 1: URL Input and Validation

**User Story:** As a user, I want to enter a video URL and have it validated, so that I can be confident the download will work.

#### Acceptance Criteria

1. WHEN the Application starts, THE URL_Input SHALL be focused and ready for input
2. WHEN a user enters a URL and submits, THE Application SHALL validate the URL format
3. IF an invalid URL is provided, THEN THE Application SHALL display an error message and keep focus on URL_Input
4. WHEN a valid URL is entered, THE Application SHALL enable the download action

### Requirement 2: Custom Filename Support

**User Story:** As a user, I want to optionally specify a custom filename, so that I can organize my downloads with meaningful names.

#### Acceptance Criteria

1. THE Filename_Input SHALL accept an optional custom filename
2. WHEN no custom filename is provided, THE Application SHALL fetch and use the video title from metadata
3. WHEN a custom filename is provided, THE Application SHALL use it instead of the video title
4. THE Application SHALL slugify filenames by converting to lowercase and replacing non-alphanumeric characters with underscores

### Requirement 3: Video Download with Progress

**User Story:** As a user, I want to see download progress in real-time, so that I know how long the download will take.

#### Acceptance Criteria

1. WHEN a download starts, THE Progress_Display SHALL show a progress bar with percentage
2. WHILE downloading, THE Application SHALL update progress in real-time
3. WHEN download completes successfully, THE Application SHALL display a success notification
4. IF download fails, THEN THE Application SHALL display an error message with details

### Requirement 4: Video Conversion with Progress

**User Story:** As a user, I want to convert downloaded videos to a compatible MP4 format with progress indication, so that I can track the conversion process.

#### Acceptance Criteria

1. THE Settings_Panel SHALL include a toggle to skip ffmpeg conversion
2. WHEN conversion is enabled and download completes, THE Video_Converter SHALL convert the video to MP4
3. WHILE converting, THE Progress_Display SHALL show conversion progress
4. WHEN conversion completes, THE Application SHALL display the output file size
5. IF conversion fails, THEN THE Application SHALL display an error message

### Requirement 5: File Upload to hardfiles.org

**User Story:** As a user, I want to optionally upload my video to hardfiles.org and get a shareable link, so that I can easily share videos.

#### Acceptance Criteria

1. THE Settings_Panel SHALL include a toggle for auto-upload
2. WHEN auto-upload is disabled, THE Application SHALL prompt the user after processing completes
3. WHEN upload is initiated, THE Progress_Display SHALL show upload progress
4. WHEN upload completes successfully, THE Application SHALL display the URL and copy it to clipboard
5. IF upload fails, THEN THE Application SHALL display an error message

### Requirement 6: File Overwrite Handling

**User Story:** As a user, I want to be warned before overwriting existing files, so that I don't accidentally lose data.

#### Acceptance Criteria

1. WHEN the output file already exists, THE Application SHALL display a confirmation dialog
2. WHEN the user confirms overwrite, THE Application SHALL proceed with the download
3. WHEN the user cancels overwrite, THE Application SHALL return to the input state

### Requirement 7: Keyboard Navigation and Shortcuts

**User Story:** As a user, I want to navigate the application using keyboard shortcuts, so that I can work efficiently.

#### Acceptance Criteria

1. THE Application SHALL support Tab/Shift+Tab for navigating between inputs
2. THE Application SHALL support Enter to submit/confirm actions
3. THE Application SHALL support Escape to cancel operations or close dialogs
4. THE Application SHALL support Ctrl+Q to quit the application
5. THE Application SHALL display available shortcuts in a footer

### Requirement 8: Operation Cancellation

**User Story:** As a user, I want to cancel ongoing operations, so that I can stop downloads or conversions that I no longer need.

#### Acceptance Criteria

1. WHILE an operation is in progress, THE Application SHALL display a cancel button
2. WHEN the user cancels an operation, THE Application SHALL stop the current process
3. WHEN an operation is cancelled, THE Application SHALL clean up temporary files
4. WHEN an operation is cancelled, THE Application SHALL return to the input state

### Requirement 9: Status and Log Display

**User Story:** As a user, I want to see a log of operations and their status, so that I can understand what the application is doing.

#### Acceptance Criteria

1. THE Application SHALL display status messages for each operation phase
2. THE Application SHALL maintain a scrollable log of recent operations
3. WHEN an error occurs, THE Application SHALL log the error details
4. THE Application SHALL visually distinguish between info, success, warning, and error messages

### Requirement 10: Configuration Persistence

**User Story:** As a user, I want my settings to be remembered between sessions, so that I don't have to reconfigure the application each time.

#### Acceptance Criteria

1. THE Application SHALL save user preferences to a configuration file
2. WHEN the Application starts, THE Application SHALL load saved preferences
3. THE Settings_Panel SHALL allow users to modify the download directory
4. THE Settings_Panel SHALL allow users to set default values for auto-upload and skip-conversion toggles

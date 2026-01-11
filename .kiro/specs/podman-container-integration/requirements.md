# Requirements Document

## Introduction

This feature enables the dl-video TUI application to execute video processing operations (downloading via yt-dlp and conversion via ffmpeg) inside a Podman container instead of requiring local installation of these dependencies. This simplifies deployment and ensures consistent behavior across different host systems.

## Glossary

- **TUI_App**: The dl-video Textual-based terminal user interface application
- **Container_Service**: The service layer that manages Podman container lifecycle and command execution
- **Podman**: A daemonless container engine compatible with Docker
- **yt-dlp**: A command-line program to download videos from various platforms
- **ffmpeg**: A multimedia framework for video/audio conversion
- **Volume_Mount**: A directory mapping between host filesystem and container filesystem

## Requirements

### Requirement 1: Container Backend Selection

**User Story:** As a user, I want to choose between local tools or containerized execution, so that I can use whichever approach fits my system setup.

#### Acceptance Criteria

1. THE TUI_App SHALL provide a configuration option to select between "local" and "container" execution backends
2. WHEN the container backend is selected, THE Container_Service SHALL use Podman to execute yt-dlp and ffmpeg commands
3. WHEN the local backend is selected, THE TUI_App SHALL execute yt-dlp and ffmpeg directly on the host system
4. THE TUI_App SHALL persist the backend selection in the configuration file

### Requirement 2: Container Image Management

**User Story:** As a user, I want the application to automatically manage the container image, so that I don't need to manually pull or update images.

#### Acceptance Criteria

1. WHEN the container backend is first used, THE Container_Service SHALL pull the linuxserver/ffmpeg image if not present
2. THE Container_Service SHALL support configuring a custom container image name
3. IF the container image pull fails, THEN THE Container_Service SHALL display a clear error message with troubleshooting steps
4. THE TUI_App SHALL display image pull progress in the log panel

### Requirement 3: Video Download via Container

**User Story:** As a user, I want to download videos using yt-dlp running inside a container, so that I don't need to install yt-dlp locally.

#### Acceptance Criteria

1. WHEN downloading a video with container backend, THE Container_Service SHALL execute yt-dlp inside the Podman container
2. THE Container_Service SHALL mount the download directory as a volume so downloaded files are accessible on the host
3. THE Container_Service SHALL stream download progress from the container to the TUI_App in real-time
4. WHEN a download is cancelled, THE Container_Service SHALL stop the running container
5. THE Container_Service SHALL pass cookies-from-browser configuration to the container when configured

### Requirement 4: Video Conversion via Container

**User Story:** As a user, I want to convert videos using ffmpeg running inside a container, so that I don't need to install ffmpeg locally.

#### Acceptance Criteria

1. WHEN converting a video with container backend, THE Container_Service SHALL execute ffmpeg inside the Podman container
2. THE Container_Service SHALL mount input and output directories as volumes
3. THE Container_Service SHALL stream conversion progress from the container to the TUI_App in real-time
4. WHEN a conversion is cancelled, THE Container_Service SHALL stop the running container

### Requirement 5: Container Lifecycle Management

**User Story:** As a user, I want containers to be properly cleaned up after operations, so that I don't accumulate unused containers.

#### Acceptance Criteria

1. WHEN an operation completes successfully, THE Container_Service SHALL remove the container
2. WHEN an operation fails or is cancelled, THE Container_Service SHALL remove the container
3. IF a container fails to start, THEN THE Container_Service SHALL return a descriptive error including container logs
4. THE Container_Service SHALL use unique container names to prevent conflicts with concurrent operations

### Requirement 6: Error Handling and Fallback

**User Story:** As a user, I want clear error messages when container operations fail, so that I can troubleshoot issues.

#### Acceptance Criteria

1. IF Podman is not installed, THEN THE Container_Service SHALL display an error message suggesting installation steps
2. IF the container fails to start, THEN THE Container_Service SHALL include container logs in the error message
3. IF volume mounting fails, THEN THE Container_Service SHALL display a clear error about directory permissions
4. THE TUI_App SHALL allow switching to local backend if container operations consistently fail

### Requirement 7: Settings UI Integration

**User Story:** As a user, I want to configure container settings through the existing settings UI, so that I have a consistent configuration experience.

#### Acceptance Criteria

1. THE TUI_App SHALL add a "Backend" dropdown in the settings screen with options "Local" and "Container"
2. WHEN container backend is selected, THE TUI_App SHALL display additional container-specific settings
3. THE TUI_App SHALL allow configuring a custom container image name in settings
4. THE TUI_App SHALL validate that Podman is available when container backend is selected

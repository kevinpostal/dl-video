# Implementation Plan: Podman Container Integration

## Overview

This plan implements container-based execution for yt-dlp and ffmpeg operations using Podman. The implementation follows a layered approach: first creating the backend abstractions, then integrating them into existing services, and finally updating the UI.

## Tasks

- [x] 1. Create execution backend abstractions
  - [x] 1.1 Create BackendType enum and CommandResult dataclass in models.py
    - Add BackendType enum with LOCAL and CONTAINER values
    - Add CommandResult dataclass for command execution results
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Create ExecutionBackend protocol in new file services/backends.py
    - Define async execute() method signature with volume_mounts parameter
    - Define cancel() method signature
    - Define is_available() method signature
    - _Requirements: 1.2, 1.3_

  - [x] 1.3 Implement LocalBackend class
    - Implement execute() using asyncio.create_subprocess_exec
    - Implement cancel() to terminate process
    - Implement is_available() returning (True, "")
    - _Requirements: 1.3_

  - [x] 1.4 Write property test for LocalBackend execute streaming
    - **Property 5: Progress Line Streaming**
    - **Validates: Requirements 3.3, 4.3**

- [x] 2. Implement PodmanBackend
  - [x] 2.1 Implement PodmanBackend class in services/backends.py
    - Implement is_available() checking podman --version
    - Implement ensure_image() to pull image if missing
    - Implement execute() with podman run command construction
    - Implement cancel() to stop container
    - _Requirements: 2.1, 2.2, 3.1, 4.1_

  - [x] 2.2 Implement volume mount argument construction
    - Build -v arguments from volume_mounts list
    - Add :Z suffix for SELinux compatibility
    - Mark input mounts as read-only with :ro
    - _Requirements: 3.2, 4.2_

  - [x] 2.3 Implement unique container naming
    - Generate container names with dl-video prefix and job ID
    - Use --name argument in podman run
    - _Requirements: 5.4_

  - [x] 2.4 Write property tests for PodmanBackend
    - **Property 3: Custom Image Configuration**
    - **Property 4: Volume Mount Construction**
    - **Property 7: Container Auto-Removal**
    - **Property 8: Unique Container Naming**
    - **Validates: Requirements 2.2, 3.2, 4.2, 5.1, 5.2, 5.4**

- [x] 3. Create ContainerService
  - [x] 3.1 Create ContainerService class in services/container_service.py
    - Implement set_backend() and get_backend() methods
    - Implement run_yt_dlp() with appropriate volume mounts
    - Implement run_ffmpeg() with input/output volume mounts
    - Implement run_ffprobe() for duration detection
    - _Requirements: 1.2, 1.3, 3.1, 4.1_

  - [x] 3.2 Write property test for backend routing
    - **Property 2: Backend Routing Based on Configuration**
    - **Validates: Requirements 1.2, 1.3**

- [x] 4. Checkpoint - Ensure backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update Config model and persistence
  - [x] 5.1 Add container settings to Config dataclass
    - Add execution_backend field (default: "local")
    - Add container_image field (default: None)
    - _Requirements: 1.1, 1.4_

  - [x] 5.2 Update ConfigManager for new fields
    - Add serialization/deserialization for new fields
    - Handle migration from old config files without new fields
    - _Requirements: 1.4_

  - [x] 5.3 Write property test for config round-trip
    - **Property 1: Configuration Persistence Round-Trip**
    - **Validates: Requirements 1.4**

- [x] 6. Integrate ContainerService into existing services
  - [x] 6.1 Update VideoDownloader to use ContainerService
    - Accept ContainerService in constructor
    - Replace direct subprocess calls with ContainerService.run_yt_dlp()
    - Pass cookies configuration through to container
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [x] 6.2 Update VideoConverter to use ContainerService
    - Accept ContainerService in constructor
    - Replace direct subprocess calls with ContainerService.run_ffmpeg()
    - Replace ffprobe calls with ContainerService.run_ffprobe()
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 6.3 Write property test for cookies passthrough
    - **Property 6: Cookies Configuration Passthrough**
    - **Validates: Requirements 3.5**

- [x] 7. Checkpoint - Ensure service integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update Settings UI
  - [x] 8.1 Add backend selection to SettingsScreen
    - Add Select dropdown for "Local" / "Container" backend
    - Show/hide container-specific settings based on selection
    - Add Input field for custom container image
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 8.2 Add Podman availability validation
    - Check Podman availability when container backend selected
    - Display warning if Podman not installed
    - _Requirements: 6.1, 7.4_

- [x] 9. Update DLVideoApp to wire everything together
  - [x] 9.1 Initialize ContainerService in app
    - Create ContainerService with config settings
    - Pass to VideoDownloader and VideoConverter
    - Handle DL_VIDEO_BACKEND environment variable override
    - _Requirements: 1.2, 1.3_

  - [x] 9.2 Handle config changes for backend
    - Update ContainerService when settings change
    - Trigger image pull if switching to container backend
    - _Requirements: 2.1_

- [x] 10. Add error handling
  - [x] 10.1 Implement error detection and messaging
    - Detect Podman not installed error
    - Detect image pull failures
    - Detect volume mount permission errors
    - Format user-friendly error messages
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 11. Update Makefile
  - [x] 11.1 Add container-related targets
    - Add container-pull target
    - Add container-check target
    - Add container-test target
    - Add run-container target
    - _Requirements: 2.1_

- [x] 12. Final checkpoint - Full integration test
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks including property tests are required
- Property tests use Hypothesis library
- Integration tests require Podman installed and will be skipped otherwise
- The linuxserver/ffmpeg image includes both yt-dlp and ffmpeg

# dl-video Documentation

Welcome to the dl-video documentation! This directory contains comprehensive guides for users and developers.

## User Documentation

### Getting Started
- [README](../README.md) - Quick start guide and feature overview
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions

### Advanced Usage
- Configuration options and environment variables
- Container setup and security considerations
- Web interface and Tailscale Funnel setup
- Cookie management for authenticated downloads

## Developer Documentation

### Development
- [Contributing Guide](CONTRIBUTING.md) - Development setup and workflow
- [Architecture Overview](ARCHITECTURE.md) - System design and components

### Technical Details
- Component architecture and UI design
- Service layer and backend abstraction
- State management and job lifecycle
- Testing strategies and best practices

## API Reference

### Core Components
- **InputForm** - URL input and validation
- **JobsPanel** - Job management and progress tracking
- **LogHistoryPanel** - Logging and download history
- **SettingsPanel** - Configuration management

### Services
- **VideoDownloader** - Video downloading via yt-dlp
- **VideoConverter** - Video conversion via ffmpeg
- **FileUploader** - File upload to sharing services
- **ContainerService** - Container execution abstraction

### Backend System
- **LocalBackend** - Direct command execution
- **PodmanBackend** - Container-based execution
- **ExecutionBackend** - Backend interface for extensions

## Examples

### Basic Usage
```bash
# Terminal mode
make run

# Container mode (no local dependencies)
make app-run

# Web interface
make serve
```

### Configuration
```json
{
  "auto_upload": false,
  "skip_conversion": false,
  "cookies_browser": "chrome",
  "download_folder": "~/Downloads",
  "backend_type": "local"
}
```

### Environment Variables
```bash
# Force container backend
export DL_VIDEO_BACKEND=container

# Custom config directory
export DL_VIDEO_CONFIG_DIR=~/.config/my-dl-video
```

## Contributing

We welcome contributions! Please see the [Contributing Guide](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

## Support

- **Issues**: Report bugs and request features on [GitHub Issues](https://github.com/kevinpostal/dl-video/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/kevinpostal/dl-video/discussions)
- **Documentation**: Improve docs by submitting pull requests

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

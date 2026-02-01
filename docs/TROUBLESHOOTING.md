# Troubleshooting Guide

## Common Issues

### Installation Problems

#### uv not found
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or ~/.zshrc
```

#### Python version issues
```bash
# Check Python version
python --version  # Should be 3.11+

# Install Python 3.11+ if needed
# On macOS: brew install python@3.11
# On Ubuntu: sudo apt install python3.11
```

### Container Issues

#### Podman not installed
```bash
# macOS
brew install podman

# Ubuntu/Debian
sudo apt install podman

# Fedora
sudo dnf install podman
```

#### Container image pull failures
```bash
# Check network connectivity
ping registry-1.docker.io

# Try pulling manually
podman pull linuxserver/ffmpeg:latest

# Check available space
df -h
```

#### SELinux permission errors
```bash
# Add :z flag to volume mounts (done automatically)
# Or temporarily disable SELinux
sudo setenforce 0
```

### Download Issues

#### Age-restricted videos
1. Open Settings panel (Ctrl+P → Settings)
2. Set "Cookies" to your browser (chrome, firefox, etc.)
3. Ensure you're logged into YouTube in that browser

#### Network timeouts
- Check internet connection
- Try downloading smaller videos first
- Consider using container backend for isolation

#### Unsupported sites
- Check [yt-dlp supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
- Update yt-dlp: `pip install -U yt-dlp`

### Conversion Issues

#### ffmpeg not found
```bash
# Install ffmpeg locally
# macOS: brew install ffmpeg
# Ubuntu: sudo apt install ffmpeg

# Or use container backend
make run-container
```

#### Conversion failures
- Check available disk space
- Try skipping conversion in settings
- Check ffmpeg logs in terminal panel

### Upload Issues

#### Upload.beer timeouts
- Check file size (service has limits)
- Verify internet connection
- Try uploading manually to test service

#### Clipboard issues
```bash
# Install clipboard utilities
# Linux: sudo apt install xclip
# macOS: (built-in)
```

### UI Issues

#### Terminal display problems
```bash
# Set proper terminal environment
export TERM=xterm-256color
export COLORTERM=truecolor

# Try different terminal emulator
# Recommended: iTerm2, Alacritty, Windows Terminal
```

#### Keyboard shortcuts not working
- Ensure terminal supports key combinations
- Try alternative shortcuts from command palette (Ctrl+P)
- Check terminal key binding conflicts

### Performance Issues

#### Slow downloads
- Check internet speed
- Try different video quality
- Monitor system resources

#### High memory usage
- Clear thumbnail cache: `make clean-thumbnails`
- Restart application periodically
- Check for memory leaks in logs

## Debugging Steps

### Enable Verbose Logging

1. Open terminal panel in app
2. Check detailed logs during operations
3. Look for error messages and stack traces

### Container Debugging

```bash
# Test container execution
make container-test

# Run container interactively
podman run -it --rm linuxserver/ffmpeg:latest /bin/bash

# Check container logs
podman logs <container-id>
```

### File System Issues

```bash
# Check permissions
ls -la ~/Downloads

# Check disk space
df -h

# Check file system errors
dmesg | grep -i error
```

### Network Debugging

```bash
# Test connectivity
curl -I https://www.youtube.com

# Check DNS resolution
nslookup youtube.com

# Test with different DNS
# Add to /etc/resolv.conf: nameserver 8.8.8.8
```

## Getting Help

### Before Reporting Issues

1. Check this troubleshooting guide
2. Search existing GitHub issues
3. Try with latest version
4. Test with minimal configuration

### Reporting Bugs

Include:
- Operating system and version
- Python version (`python --version`)
- Application version
- Steps to reproduce
- Error messages/logs
- Screenshots if UI-related

### Performance Issues

Include:
- System specifications
- Resource usage (CPU, memory, disk)
- Network speed
- File sizes being processed

### Feature Requests

- Check existing issues first
- Describe use case clearly
- Consider implementation complexity
- Provide examples if possible

## Advanced Troubleshooting

### Log Files

```bash
# Application logs
~/.config/dl-video/logs/

# System logs
journalctl -u podman
```

### Configuration Reset

```bash
# Backup current config
cp ~/.config/dl-video/config.json ~/.config/dl-video/config.json.bak

# Reset to defaults
rm ~/.config/dl-video/config.json
```

### Clean Installation

```bash
# Remove all application data
rm -rf ~/.config/dl-video/

# Reinstall dependencies
make clean
make install
```

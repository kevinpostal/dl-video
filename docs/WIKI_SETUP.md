# GitHub Wiki Setup Guide

This document provides templates and structure for setting up the dl-video GitHub wiki.

## Recommended Wiki Structure

### Home Page
```markdown
# dl-video Wiki

Welcome to the dl-video wiki! This is your comprehensive guide to using and developing with dl-video.

## Quick Links
- [Installation Guide](Installation-Guide)
- [Configuration](Configuration)
- [Troubleshooting](Troubleshooting)
- [Architecture](Architecture)
- [Contributing](Contributing)

## What is dl-video?
A modern terminal UI application for downloading, converting, and sharing videos with support for 1000+ sites.

## Getting Help
- Check the [Troubleshooting](Troubleshooting) page
- Search [existing issues](https://github.com/kevinpostal/dl-video/issues)
- Start a [discussion](https://github.com/kevinpostal/dl-video/discussions)
```

### Installation Guide
```markdown
# Installation Guide

## Quick Start

### Option 1: Container (Recommended)
No Python or dependencies needed - just Podman or Docker:

```bash
# Build and run
make app-build
make app-run
```

### Option 2: Local Installation
```bash
# Install dependencies
make install

# Run application
make run
```

## Detailed Installation

### System Requirements
- Operating System: Linux, macOS, or Windows
- Python 3.11+ (for local installation)
- Modern terminal with 256-color support

### Container Installation
[Detailed container setup instructions...]

### Local Installation
[Detailed local setup instructions...]

### Troubleshooting Installation
[Common installation issues and solutions...]
```

### Configuration
```markdown
# Configuration Guide

## Configuration File
Settings are stored in `~/.config/dl-video/config.json`

## Available Settings
[Detailed explanation of each setting...]

## Environment Variables
[List and explanation of environment variables...]

## Cookie Setup
[Step-by-step cookie configuration for different browsers...]

## Backend Configuration
[Local vs Container backend setup...]
```

### Troubleshooting
```markdown
# Troubleshooting

## Common Issues

### Installation Problems
[Installation troubleshooting from docs/TROUBLESHOOTING.md...]

### Download Issues
[Download troubleshooting...]

### Container Issues
[Container troubleshooting...]

## Getting Help
[How to report issues and get support...]
```

### Architecture
```markdown
# Architecture Overview

## System Design
[Content from docs/ARCHITECTURE.md...]

## Component Overview
[Detailed component explanations...]

## Extension Points
[How to extend the application...]
```

### Contributing
```markdown
# Contributing Guide

## Development Setup
[Content from docs/CONTRIBUTING.md...]

## Code Guidelines
[Coding standards and practices...]

## Testing
[Testing guidelines and procedures...]
```

### API Reference
```markdown
# API Reference

## Core Components
[Detailed API documentation for components...]

## Services
[Service layer API documentation...]

## Backend System
[Backend interface documentation...]
```

## Wiki Maintenance

### Content Guidelines
- Keep content up-to-date with releases
- Use clear, concise language
- Include code examples where helpful
- Link between related pages
- Use consistent formatting

### Page Organization
- Use descriptive page titles
- Create logical navigation structure
- Include "See Also" sections
- Maintain a consistent sidebar

### Regular Updates
- Review content with each release
- Update screenshots and examples
- Check for broken links
- Gather user feedback for improvements

## Setting Up the Wiki

1. Go to your GitHub repository
2. Click on the "Wiki" tab
3. Create the Home page using the template above
4. Add additional pages using the templates
5. Configure the sidebar for easy navigation
6. Enable wiki editing permissions as needed

## Wiki Best Practices

- Use clear headings and structure
- Include code examples with syntax highlighting
- Add screenshots for UI-related content
- Cross-reference related documentation
- Keep content concise but comprehensive
- Regular review and updates

# Contributing to dl-video

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- [Podman](https://podman.io/) or Docker (for container features)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/kevinpostal/dl-video.git
cd dl-video

# Install dependencies
make dev

# Run tests
make test

# Run the application
make run
```

## Project Structure

```
dl-video/
├── src/dl_video/           # Main application code
│   ├── components/         # Textual UI components
│   ├── services/          # Business logic services
│   ├── utils/             # Utility modules
│   ├── app.py             # Main application
│   └── models.py          # Data models
├── tests/                 # Test suite
├── docs/                  # Documentation
└── Makefile              # Development commands
```

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/test_specific.py

# Run tests with verbose output
uv run pytest -v
```

### Code Quality

```bash
# Format code
make fmt

# Lint code
make lint

# Check syntax
python check_syntax.py
```

### Testing UI Components

The project uses `pytest-textual-snapshot` for UI testing:

```bash
# Update snapshots after UI changes
uv run pytest --snapshot-update

# Test specific component
uv run pytest tests/test_snapshots.py::TestAppSnapshots::test_initial_state
```

## Adding New Features

### UI Components

1. Create component in `src/dl_video/components/`
2. Inherit from appropriate Textual widget
3. Implement `compose()` method for layout
4. Add event handlers as needed
5. Write snapshot tests

Example:
```python
from textual.widgets import Static
from textual.app import ComposeResult

class MyComponent(Static):
    def compose(self) -> ComposeResult:
        yield Label("Hello World")
```

### Services

1. Create service in `src/dl_video/services/`
2. Implement async methods with progress callbacks
3. Add proper error handling
4. Support cancellation
5. Write unit tests

Example:
```python
class MyService:
    async def process(self, callback: Callable[[int], None]) -> None:
        for i in range(100):
            # Do work
            callback(i)
            await asyncio.sleep(0.1)
```

### Backend Support

1. Implement `ExecutionBackend` interface
2. Add backend detection logic
3. Handle platform-specific requirements
4. Add comprehensive tests

## Testing Guidelines

### Unit Tests
- Test business logic in isolation
- Mock external dependencies
- Use property-based testing with Hypothesis
- Aim for high coverage of critical paths

### Integration Tests
- Test component interactions
- Use real backends when possible
- Test error conditions
- Verify state transitions

### UI Tests
- Use snapshot testing for layout verification
- Test user interactions
- Verify accessibility
- Test responsive behavior

## Code Style

- Follow PEP 8
- Use type hints throughout
- Document public APIs
- Keep functions focused and small
- Use descriptive variable names

## Debugging

### Textual Development

```bash
# Run with textual console
textual console

# Run with development mode
textual run --dev dl_video.app:DLVideoApp

# Take screenshots
make screenshot
```

### Container Issues

```bash
# Test container backend
make container-test

# Check container availability
make container-check

# Debug container execution
podman run -it --rm linuxserver/ffmpeg:latest /bin/bash
```

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Create release PR
5. Tag release after merge
6. Build and publish container image

## Getting Help

- Check existing issues on GitHub
- Review documentation in `docs/`
- Ask questions in discussions
- Join development chat (if available)

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

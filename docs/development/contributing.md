# Contributing Guide

Thank you for your interest in contributing to the MiGo integration!

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git
- A Home Assistant development environment (optional but recommended)

### Setup

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ha-migo-netatmo.git
   cd ha-migo-netatmo
   ```
3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate     # Windows
   ```
4. Install development dependencies:
   ```bash
   pip install -r requirements_dev.txt
   ```
5. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Development Workflow

### Creating a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### Making Changes

1. Write your code following the project's coding style
2. Add tests for new functionality
3. Update documentation if needed
4. Run linting and tests locally

### Code Quality

Before committing, ensure your code passes all checks:

```bash
# Linting
ruff check .
ruff format --check .

# Type checking (optional)
mypy custom_components/

# Tests
pytest tests/ -v
```

### Commit Messages

Follow conventional commits format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Maintenance tasks

Example:
```
feat: add support for multiple thermostats per home
```

### Submitting a Pull Request

1. Push your branch to your fork
2. Open a Pull Request against `main`
3. Fill in the PR template
4. Wait for CI checks to pass
5. Address review feedback

## Code Style

### Python

- Use type hints for all function parameters and return values
- Follow PEP 8 guidelines (enforced by ruff)
- Use descriptive variable and function names
- Add docstrings to classes and public methods

### File Organization

```
custom_components/migo_netatmo/
├── __init__.py          # Integration setup
├── api.py               # API client
├── climate.py           # Climate entity
├── config_flow.py       # Configuration flow
├── const.py             # Constants
├── coordinator.py       # Data coordinator
├── entity.py            # Base entities
├── helpers.py           # Utility functions
├── sensor.py            # Sensor entities
├── switch.py            # Switch entities
├── select.py            # Select entities
├── number.py            # Number entities
├── binary_sensor.py     # Binary sensor entities
├── button.py            # Button entities
└── translations/        # Translation files
```

## Testing

See [Testing Guide](testing.md) for detailed testing instructions.

### Running Tests

```bash
pytest tests/ -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Use pytest fixtures from `conftest.py`
- Mock external API calls

## API Documentation

If you're working with the Netatmo API, refer to [API Reference](../api/reference.md) for documented endpoints.

## Getting Help

- Check existing issues and PRs
- Open a discussion for questions
- Join the Home Assistant community

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

# Contributing to MiGo (Netatmo) Integration

Thank you for your interest in contributing to this Home Assistant integration!

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Home Assistant development environment
- Git

### Setting Up the Development Environment

1. **Clone the repository**
   ```bash
   git clone https://github.com/tomahoax/ha-migo-netatmo.git
   cd ha-migo-netatmo
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

### Running the Integration Locally

1. Copy the `custom_components/migo_netatmo` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via the UI

## Code Style

This project follows Home Assistant coding standards:

- **Python Style**: We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- **Type Hints**: All functions must have type annotations
- **Docstrings**: Use Google-style docstrings for all public functions and classes

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality. They run automatically on `git commit`:

- Ruff (linting and formatting)
- MyPy (type checking)
- Various file checks (trailing whitespace, YAML validation, etc.)

To run hooks manually:
```bash
pre-commit run --all-files
```

## Testing

### Running Tests

```bash
pytest tests/
```

### Running Tests with Coverage

```bash
pytest tests/ --cov=custom_components/migo_netatmo --cov-report=html
```

### Writing Tests

- Place tests in the `tests/` directory
- Use `pytest` and `pytest-asyncio` for async tests
- Mock external API calls using `aiohttp` mocks
- Use fixtures from `conftest.py` for common setup

## Pull Request Process

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the code style guidelines
3. **Add tests** for any new functionality
4. **Update documentation** if needed (README, docstrings, etc.)
5. **Run the full test suite** and ensure all tests pass
6. **Run pre-commit hooks** to ensure code quality
7. **Submit a pull request** with a clear description of your changes

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Write clear commit messages
- Reference any related issues in your PR description
- Be responsive to code review feedback

## Reporting Issues

### Bug Reports

When reporting a bug, please include:

- Home Assistant version
- Integration version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant logs (with debug logging enabled)

### Feature Requests

When requesting a feature:

- Describe the use case
- Explain why this would be useful
- Provide examples if possible

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

If you have questions about contributing, feel free to:

- Open a [GitHub Discussion](https://github.com/tomahoax/ha-migo-netatmo/discussions)
- Open an issue with the "question" label

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

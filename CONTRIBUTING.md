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
   `pyproject.toml` is the source of truth for dependency constraints; CI and
   Dependabot both read it. If you use [uv](https://docs.astral.sh/uv/) locally
   (`uv run pytest`, etc.), refresh `uv.lock` after changing a dependency with
   `uv lock`. The lockfile pins exact versions for local reproducibility only,
   it is not read by CI or Dependabot.

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
├── models.py            # TypedDicts for API/coordinator data
├── sensor.py            # Sensor entities
├── switch.py            # Switch entities
├── select.py            # Select entities
├── number.py            # Number entities
├── binary_sensor.py     # Binary sensor entities
├── button.py            # Button entities
└── translations/        # Translation files
```

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality. They run automatically on `git commit`:

- Ruff (linting and formatting)
- MyPy (type checking)
- Various file checks (trailing whitespace, YAML validation, etc.)

To run hooks manually:
```bash
pre-commit run --all-files
```

The mypy hook is a local hook that runs `uv run --frozen mypy` from the project
environment, so it needs `uv sync --extra dev` to have been run first. This is
deliberate: mypy needs Home Assistant importable to check anything meaningful.
In an isolated hook environment every HA symbol resolves to `Any` and most of
the strict checks silently pass. The mypy configuration in `pyproject.toml`
mirrors the one Home Assistant core generates for integrations listed in its
`.strict-typing` file, and mypy is pinned so the hook and CI agree.

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

## Git Workflow (GitHub Flow)

This project follows [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow):

### Branch Structure

- **`main`** - Production-ready code, always stable
- **`dev`** - Development branch for ongoing work
- **Feature branches** - Created from `dev` for specific features/fixes

### Development Process

1. **Create a feature branch from `dev`**
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following the code style guidelines

3. **Commit your changes** with clear messages
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

4. **Push and create a Pull Request to `dev`**
   ```bash
   git push origin feature/my-feature
   ```

5. **After review, merge to `dev`**

6. **Releases**: When `dev` is stable, it gets merged to `main` and tagged

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `chore:` - Maintenance tasks
- `refactor:` - Code refactoring
- `test:` - Adding tests

## Pull Request Process

1. **Create your branch from `dev`** (not `main`)
2. **Make your changes** following the code style guidelines
3. **Add tests** for any new functionality
4. **Update documentation** if needed (README, docstrings, etc.)
5. **Run the full test suite** and ensure all tests pass
6. **Run pre-commit hooks** to ensure code quality
7. **Submit a pull request to `dev`** with a clear description of your changes

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Write clear commit messages following Conventional Commits
- Reference any related issues in your PR description
- Be responsive to code review feedback
- PRs must target `dev` branch (not `main`)

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

# Contributing to Nowcasting Toolbox

Thank you for your interest in contributing! This guide will help you get started.

---

## Development Setup

### Prerequisites

- Python 3.10+ (recommended: 3.12)
- Git
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Quick Start

```bash
# Clone the repository
git clone https://github.com/pengkodammaya/BM-ECB.git
cd BM-ECB

# Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev,global,yaml]"

# Run tests
python -m pytest tests/ -v

# Run the CLI
nowcast --help
```

---

## Project Structure

```
src/nowcasting_toolbox/
├── bvar/           # Bayesian VAR model
├── beq/            # Bridge Equations model
├── cli/            # Command-line interface
├── data/           # Data loading, transforms, API clients
│   └── sources/    # OpenDOSM, BNM, cache, registry
├── dfm/            # Dynamic Factor Model
├── eval/           # Metrics, backtesting, vintage builder
├── news/           # News decomposition
├── pipeline/       # Orchestrator, leaderboard
├── postprocess/    # Growth-to-level conversion
├── selection/      # Variable selection
└── utils/          # Constants, missing data, outliers
tests/              # Test files mirror src/ structure
scripts/            # Standalone scripts (daily_update.py, etc.)
docs/               # Documentation
```

---

## Code Style

### General

- Follow [PEP 8](https://peps.python.org/pep-0008/) with 100-char line limit
- Use type hints for function signatures
- Use NumPy-style docstrings for public functions
- Import order: stdlib → third-party → local (isort-compatible)

### Docstring Format

```python
def my_function(x: float, y: float) -> float:
    """Brief description of the function.

    Longer description if needed.

    Parameters
    ----------
    x : float
        Description of x.
    y : float
        Description of y.

    Returns
    -------
    float
        Description of return value.
    """
```

### Logging

- Use `logging` module, not `print()`
- Use `logger.debug()` for verbose output
- Use `logger.warning()` for recoverable errors
- Use `logger.error()` for failures that abort operations

---

## Testing

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_bvar/test_bvar.py -v

# With coverage
python -m pytest tests/ --cov=nowcasting_toolbox --cov-report=html
```

### Writing Tests

- Place tests in `tests/` mirroring the `src/` structure
- Name test files `test_*.py`
- Name test functions `test_*`
- Use fixtures for common test data
- Mock external API calls (don't hit real APIs in tests)

### Test Categories

| Directory | What to test |
|-----------|--------------|
| `test_bvar/` | BVAR model estimation |
| `test_dfm/` | DFM Kalman filter, EM |
| `test_beq/` | Bridge equations |
| `test_eval/` | Metrics, backtesting |
| `test_data/` | Data loading, transforms |
| `test_cli/` | CLI commands |

---

## Pull Request Process

### Before Submitting

1. **Run tests:** `python -m pytest tests/ -v`
2. **Check lint:** Ensure no new warnings
3. **Update docs:** If adding features, update README or relevant docs
4. **Update IMPROVEMENTS.md:** Mark completed items if applicable

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Testing
- [ ] All tests pass
- [ ] New tests added (if applicable)

## Checklist
- [ ] Code follows project style
- [ ] Docstrings added for new functions
- [ ] No secrets or API keys committed
```

### Review Process

1. All PRs require at least one review
2. CI must pass (GitHub Actions)
3. No merge conflicts
4. Squash merge preferred for clean history

---

## Adding a New Model

1. Create `src/nowcasting_toolbox/mymodel/`
2. Implement `.fit(X)` / `.predict()` API (sklearn-compatible)
3. Add `MyModelParams` to `config.py`
4. Wire into `pipeline/orchestrator.py`
5. Add tests in `tests/test_mymodel/`
6. Update leaderboard to include model

---

## Adding a New Data Source

1. Create client in `data/sources/`
2. Add metadata to `data/sources/registry.py`
3. Implement retry logic (see `opendosm.py` for example)
4. Add cache support via `DataCache`
5. Add tests with mocked HTTP responses

---

## Common Issues

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common development issues.

---

## Questions?

Open an issue at https://github.com/pengkodammaya/BM-ECB/issues

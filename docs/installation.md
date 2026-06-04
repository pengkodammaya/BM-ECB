# Installation

## Requirements

- Python 3.10+ (recommended: 3.12)
- Git

## Install from Source

```bash
# Clone the repository
git clone https://github.com/pengkodammaya/BM-ECB.git
cd BM-ECB

# Create virtual environment (recommended: uv)
uv venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install with development dependencies
uv pip install -e ".[dev]"
```

## Optional Dependencies

```bash
# For global indicators (Yahoo Finance)
uv pip install -e ".[global]"

# For YAML config support
uv pip install -e ".[yaml]"

# For documentation building
pip install mkdocs mkdocs-material mkdocstrings[python]
```

## Verify Installation

```bash
# Run tests
python -m pytest tests/ -v

# Check CLI
nowcast --help
```

## FRED API Key (Optional)

For US economic indicators (industrial production, consumer sentiment):

1. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html
2. Set as environment variable:

```bash
# Linux/Mac
export FRED_API_KEY="your_key_here"

# Windows CMD
set FRED_API_KEY=your_key_here

# Windows PowerShell
$env:FRED_API_KEY="your_key_here"
```

Or create a `.fred_key` file in the project root (not recommended for production).

# Nowcasting Toolbox — Docker image
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY data/ ./data/
COPY output/ ./output/

# Create empty dirs if they don't exist
RUN mkdir -p data/malaysia output/malaysia

# Install dependencies
RUN uv pip install --system -e ".[dev]"

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command
ENTRYPOINT ["python", "-m", "nowcasting_toolbox.cli.main"]
CMD ["--help"]

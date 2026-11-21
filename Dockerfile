FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY dashboard ./dashboard
# editable install so the package finds sql/ and dashboard/ under /app
RUN pip install -e ".[postgres]"

# Data and artifacts are mounted as volumes (see docker-compose.yml).
ENV RETAILPULSE_DATA_DIR=/app/data/raw RETAILPULSE_ARTIFACTS_DIR=/app/artifacts
EXPOSE 8000 8501
CMD ["retailpulse", "serve", "--host", "0.0.0.0", "--port", "8000"]

# Multi-stage Dockerfile for Trading System
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY state/ ./state/
COPY scripts/ ./scripts/

# Environment variables
ENV PYTHONPATH=/app
ENV APP_ENV=production
ENV DB_HOST=postgres
ENV DB_PORT=5432

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8050/health || exit 1

# Expose ports
EXPOSE 8050 5000

# Run the application
CMD ["python", "-m", "app.dashboard"]

# Development stage
FROM base as dev
ENV APP_ENV=development
RUN pip install pytest black flake8
CMD ["python", "-m", "pytest"]

# ==========================================================
# MediaCrawler Dockerfile
# Multi-stage build: builder → playwright-deps → runtime
# ==========================================================

# ---- Base stage ----
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---- Builder stage ----
FROM base AS builder

RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# ---- Playwright deps stage ----
FROM base AS playwright-deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright system dependencies
    libasound2 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libegl1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxtst6 \
    wget \
    curl \
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ---- Runtime stage ----
FROM playwright-deps AS runtime

# Copy uv and venv from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:/root/.local/bin:$PATH"

# Install Playwright browsers (Chromium only)
RUN pip install playwright && \
    python -m playwright install chromium && \
    python -m playwright install-deps chromium

# Copy application code
COPY . .

# Create data directory as volume mount point
RUN mkdir -p /app/data

EXPOSE 8080 8081

# Default command: start WebUI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8081"]

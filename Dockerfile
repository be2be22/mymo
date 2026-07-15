# ============================================================
# MyMoviz Notify Bot - Dockerfile
# Multi-stage build for smaller production image
# ============================================================

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Build wheels for all dependencies into /wheels
RUN pip install --upgrade pip wheel setuptools && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

LABEL maintainer="MyMoviz Notify Bot <noreply@example.com>"
LABEL description="Telegram bot for tracking MyMoviz.co movies and series"

# Runtime system deps for lxml + timezone data
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libffi8 \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/UTC /etc/localtime

WORKDIR /app

# Copy pre-built wheels from builder stage
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# Install from local wheels (no internet access needed at this point)
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Copy application source
COPY . .

# Create data and logs directories
RUN mkdir -p /app/data /app/logs

# Expose webhook port (Railway/production)
EXPOSE 8443

# Use a non-root user for security
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Run the bot
CMD ["python", "main.py"]

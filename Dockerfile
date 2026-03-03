# Stage 1: Build Tailwind CSS
FROM node:22-slim AS css-builder
WORKDIR /build
COPY package.json postcss.config.js tailwind.config.js ./
COPY app/static/css/input.css app/static/css/input.css
COPY app/templates/ app/templates/
RUN npm install && npm run build:css

# Stage 2: Python application
FROM python:3.13-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd --create-home --uid 1000 appuser

# Copy application code
COPY app/ app/
COPY tests/ tests/

# Copy built CSS from stage 1
COPY --from=css-builder /build/app/static/css/output.css app/static/css/output.css

# Create data directory for SQLite
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

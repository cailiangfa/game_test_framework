# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir playwright && \
    playwright install chromium

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

LABEL maintainer="your-email@example.com" \
      description="Game Shop Test Framework" \
      version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH=/home/appuser/.local/lib/python3.12/site-packages \
    PATH=/home/appuser/.local/bin:$PATH \
    GAME_DB=/tmp/test.db \
    HEADLESS=true \
    BROWSER_TYPE=chromium

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --from=builder --chown=appuser:appuser /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright

COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser tests/ ./tests/
COPY --chown=appuser:appuser .env ./
COPY --chown=appuser:appuser environment.properties ./

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

USER appuser

CMD ["pytest", "tests/", "-v", "--alluredir=allure-results", "--cov=backend", "--cov-report=term"]
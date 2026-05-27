FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

# 关键修复：把浏览器缓存复制给 appuser
RUN mkdir -p /home/appuser/.cache && \
    cp -r /root/.cache/ms-playwright /home/appuser/.cache/ && \
    chown -R appuser:appuser /home/appuser/.cache

COPY backend/ ./backend/
COPY tests/ ./tests/
RUN chown -R appuser:appuser /app

USER appuser

CMD ["pytest", "tests/", "-v", "--alluredir=allure-results"]
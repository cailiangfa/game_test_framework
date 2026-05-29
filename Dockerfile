# 游戏商城测试框架 - 精简版 Dockerfile
# 用于本地快速运行测试，不用于生产部署

FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（Playwright 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器
RUN playwright install chromium

# 复制代码
COPY backend/ ./backend/
COPY tests/ ./tests/
COPY config.py pytest.ini README.md ./

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GAME_DB=/tmp/test.db \
    HEADLESS=true

# 初始化数据库并运行测试
CMD ["sh", "-c", "python -c \"import backend.app; backend.app.init_db()\" && pytest tests/api tests/concurrency -v --cov=backend --cov-report=term"]
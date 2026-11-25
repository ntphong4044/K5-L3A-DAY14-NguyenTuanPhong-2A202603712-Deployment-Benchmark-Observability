# ============================================================
# Production Dockerfile — multi-stage, slim, non-root, < 500 MB
# Build (từ thư mục 06-lab-complete):  docker build -t agent .
# ============================================================

# ──────────────────────────────────────────────────────────
# STAGE 1: builder — cài dependencies (có build tools)
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ──────────────────────────────────────────────────────────
# STAGE 2: runtime — chỉ copy những gì cần để CHẠY
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user (security)
RUN useradd -m -r app

WORKDIR /app

# Copy packages đã cài từ builder (pip --user)
COPY --from=builder /root/.local /home/app/.local

# Copy source
COPY app ./app
COPY utils ./utils

RUN chown -R app:app /home/app /app
USER app

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Healthcheck gọi GET /health theo biến PORT
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/health')" || exit 1

# exec form qua sh -c: uvicorn thay thế sh → là PID 1 → nhận SIGTERM khi docker stop.
# Lắng nghe theo biến PORT do platform cấp (mặc định 8000).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]

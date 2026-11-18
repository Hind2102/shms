# SHMS web app + YOLO detector, CPU build (runs on any laptop / server with Docker).
# Lecture habits: slim base, pinned CPU wheels, slow-and-stable layers first, code last, non-root user,
# health check, configuration through environment variables, model weights mounted as a volume.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# libgl/libglib are needed by OpenCV, which Ultralytics imports
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# 1) heavy, rarely-changing dependencies (CPU-only PyTorch keeps the image ~2 GB instead of ~6 GB)
RUN pip install torch==2.15.0 torchvision==0.29.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install "ultralytics>=8.3" "fastapi>=0.110" "uvicorn>=0.29" "sqlalchemy>=2.0" "jinja2>=3.1" \
        "python-multipart>=0.0.9" "pillow>=10.0" "httpx>=0.27" "alembic>=1.13"

# 2) the application code (changes most often -> last, so rebuilds take seconds)
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app shms ./shms
RUN pip install --no-deps -e . && mkdir -p /data/uploads /app/models && chown -R app:app /data /app/models
USER app

ENV SHMS_DETECTOR=yolo \
    SHMS_YOLO_WEIGHTS=/app/models/sh17_yolo9e.pt \
    SHMS_YOLO_DEVICE=cpu \
    SHMS_DATABASE_URL=sqlite:////data/shms.db \
    SHMS_UPLOAD_DIR=/data/uploads \
    SHMS_INSTANCE_DIR=/data/instance \
    SHMS_MAIL_OUTBOX=/data/outbox \
    YOLO_CONFIG_DIR=/tmp/ultralytics
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "shms.asgi:app", "--host", "0.0.0.0", "--port", "8000"]

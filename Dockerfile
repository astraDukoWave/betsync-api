FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .

FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=info", "-Q", "pipeline"]
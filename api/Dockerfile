# ---------- build stage ----------
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100
WORKDIR /app
# System deps for pgvector & psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt
# ---------- runtime stage ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# copy pre-installed site-packages from builder
COPY --from=builder /install /usr/local
# copy source
COPY . .
# uvicorn entry (can be overridden in compose)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

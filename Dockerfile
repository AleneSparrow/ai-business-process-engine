FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# ${PORT:-8000} instead of a hardcoded port: hosting platforms that assign
# ports dynamically (Railway, Render, Fly.io) inject PORT and expect the
# process to bind to it; local `docker compose up` doesn't set PORT, so it
# falls back to 8000 exactly as before.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]

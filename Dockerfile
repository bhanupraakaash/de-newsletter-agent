FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Run as a non-root user; data/ holds the SQLite DB, output/ the generated newsletter.
RUN useradd --create-home app && mkdir -p data output && chown -R app:app /app
USER app
VOLUME ["/app/data", "/app/output"]

# Secrets are never baked into the image: pass them at runtime with --env-file.
ENTRYPOINT ["python", "-m", "src.main"]

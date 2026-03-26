FROM python:3.12-slim

# Non-root user for security
RUN addgroup --system app && adduser --system --group app

WORKDIR /srv/app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Data volume mount point
RUN mkdir -p /data/content && chown -R app:app /data /srv/app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

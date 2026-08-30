# BallTrend Backend for Google Cloud Run
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY data/ ./data/

# Cloud Run sets PORT env var automatically
ENV PORT=8080

# Use gunicorn for production (Cloud Run standard)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 api:app

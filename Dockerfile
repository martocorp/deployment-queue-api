FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application
COPY src/ src/

EXPOSE 8000

CMD ["uvicorn", "src.deployment_queue.main:app", "--host", "0.0.0.0", "--port", "8000"]

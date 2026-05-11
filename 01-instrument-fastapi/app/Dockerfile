FROM python:3.12-slim

WORKDIR /app

# Install curl (used by Compose health-check) + py-spy for profiling
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir py-spy==0.4.1

# Dependency install layer (cacheable)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY main.py instrumentation.py inference.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]

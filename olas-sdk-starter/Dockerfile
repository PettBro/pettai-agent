# Dockerfile for Pett Agent - Olas SDK Compliant
# Image naming convention: <author_name>/oar-<agent_name>:<agent_package_hash>

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the agent code
COPY agent/ ./agent/
COPY run.py .

# Create necessary directories
RUN mkdir -p logs

# Create placeholder for ethereum private key (will be mounted or provided)
RUN touch ethereum_private_key.txt

# Expose health check port (Olas SDK requirement)
EXPOSE 8716

# Health check (Olas SDK requirement)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8716/healthcheck || exit 1

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Make run.py executable
RUN chmod +x run.py

# ENTRYPOINT as required by Olas SDK
ENTRYPOINT ["python", "run.py"]

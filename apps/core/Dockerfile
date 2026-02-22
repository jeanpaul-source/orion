FROM python:3.10-slim

LABEL maintainer="ORION Project"
LABEL description="ORION Core - Unified AI Entity for Homelab Management"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY applications/orion-core/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY applications/orion-core/src/ ./src/
COPY applications/orion-core/web/ ./web/
COPY applications/orion-core/tests/ ./tests/

# Copy common utilities
COPY applications/orion-rag/common/ ./orion_rag/common/

# Copy and install DevOps Agent for Action subsystem
COPY applications/devops-agent/ /tmp/devops-agent/
RUN pip install --no-cache-dir /tmp/devops-agent && rm -rf /tmp/devops-agent

# Create data directory
RUN mkdir -p /data

# Expose port for web UI
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run ORION Core
# Using asyncio instead of uvloop to avoid event loop issues in Docker
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5000", "--log-level", "info", "--loop", "asyncio"]

# Orion HAL container
FROM python:3.12-slim

# System dependencies for SSH client and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user inside the container
RUN useradd -m -s /bin/bash hal

# Application directory
WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install supervisor for multi-process management
RUN pip install --no-cache-dir supervisor

# Copy application code (overridden by read-only mount in compose)
COPY . .

# SSH config for the service account
RUN mkdir -p /home/hal/.ssh && \
    printf "Host the-lab\n  HostName host.docker.internal\n  User hal-svc\n  IdentityFile /home/hal/.ssh/id_ed25519\n  StrictHostKeyChecking accept-new\n  BatchMode yes\n  ConnectTimeout 5\n" \
    > /home/hal/.ssh/config && \
    chown -R hal:hal /home/hal/.ssh && \
    chmod 700 /home/hal/.ssh && \
    chmod 600 /home/hal/.ssh/config

# State directory (overridden by mount, but create for standalone use)
RUN mkdir -p /home/hal/.orion && chown hal:hal /home/hal/.orion

USER hal

# Default: supervisord manages HTTP server + Telegram bot
CMD ["supervisord", "-c", "/app/ops/supervisord.conf"]

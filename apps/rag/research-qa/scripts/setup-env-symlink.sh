#!/bin/bash
# Setup script to recreate .env symlink after git pull
# Run this on the host after pulling changes

cd "$(git rev-parse --show-toplevel)/applications/orion-rag/research-qa" || exit 1

# Remove old .env if it's a regular file
if [ -f .env ] && [ ! -L .env ]; then
    echo "Removing old .env file..."
    rm -f .env
fi

# Create symlink if it doesn't exist or is broken
if [ ! -L .env ]; then
    echo "Creating .env symlink..."
    ln -sf ../../../.env .env
fi

# Verify
if [ -L .env ]; then
    echo "✅ .env symlink created successfully"
    ls -la .env
else
    echo "❌ Failed to create symlink"
    exit 1
fi

#!/bin/bash
# Start script for YouTube Watcher

echo "Starting YouTube Watcher..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please edit .env file with your configuration"
fi

# Start docker compose
docker compose up -d

echo "Waiting for services to start..."
sleep 5

# Show logs
docker compose logs -f

#!/usr/bin/env bash
# ==============================================================================
# TaskFlow Automated Production Deployment Script
# ==============================================================================
set -euo pipefail

echo "=========================================="
echo "🚀 Starting TaskFlow Deployment"
echo "=========================================="

# 1. Check for required environment configuration
if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ .env initialized. Please verify secret keys before public exposure."
fi

# 2. Check docker and docker compose availability
if ! command -v docker &> /dev/null; then
    echo "❌ Error: docker is not installed."
    exit 1
fi

# 3. Pull latest images and build production containers
echo "📦 Building and starting TaskFlow stack..."
docker compose down --remove-orphans
docker compose build --pull
docker compose up -d

# 4. Wait for API health check
echo "⏳ Waiting for API health check..."
MAX_RETRIES=30
RETRY_COUNT=0
HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    sleep 2
done

if [ "$HEALTHY" = true ]; then
    echo "=========================================="
    echo "✅ TaskFlow Deployed Successfully!"
    echo "🌐 API Docs:    http://localhost:8000/api/v1/docs"
    echo "🩺 Health Check: http://localhost:8000/health"
    echo "📊 Prometheus:   http://localhost:8000/metrics"
    echo "=========================================="
else
    echo "❌ Error: Health check timed out. Displaying logs..."
    docker compose logs app worker beat
    exit 1
fi

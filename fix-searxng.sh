#!/bin/bash
# Fix SearXNG - v2.0.9
# With limiter DISABLED for API access

set -e

echo "=== Stopping containers ==="
docker compose -f docker-compose.searxng.yml down -v 2>/dev/null || true
docker stop qonqrete-searxng qonqrete-redis 2>/dev/null || true
docker rm qonqrete-searxng qonqrete-redis 2>/dev/null || true

echo "=== Fixing permissions on searxng folder ==="
sudo chown -R $(id -u):$(id -g) searxng/ 2>/dev/null || true
chmod -R 755 searxng/ 2>/dev/null || true

echo "=== Starting fresh ==="
docker compose -f docker-compose.searxng.yml up -d

echo "=== Waiting for startup (10s) ==="
sleep 10

echo "=== Checking status ==="
docker ps | grep -E "searxng|redis"

echo ""
echo "=== Container logs ==="
docker logs qonqrete-searxng 2>&1 | tail -10

echo ""
echo "=== Testing web UI ==="
if curl -s http://localhost:8888/ | grep -q "SearXNG"; then
    echo "✅ Web UI working!"
else
    echo "❌ Web UI not responding"
    exit 1
fi

echo ""
echo "=== Testing JSON API (POST) ==="
RESULT=$(curl -s -X POST -d 'q=python&format=json' http://localhost:8888/search)
if echo "$RESULT" | grep -q '"results"'; then
    echo "✅ JSON API working!"
    echo "Sample: $(echo $RESULT | head -c 200)..."
else
    echo "❌ JSON API returned: $(echo $RESULT | head -c 100)"
    echo ""
    echo "If 403: Check searxng/limiter.toml exists"
fi

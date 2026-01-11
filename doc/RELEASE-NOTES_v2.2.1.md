# QonQrete v2.2.1-stable Release Notes

## 🔧 SSL FIX + DOCKER NETWORKING! 🔧

**Release Date:** January 2025  
**Type:** Critical Bug Fix

---

## The Problem

v2.2.0 had a critical bug where SearXNG connections failed with:

```
SearXNG error: ClientConnectorError: Cannot connect to host localhost:8888 ssl:default 
[Connect call failed ('127.0.0.1', 8888)]
```

**Two issues:**

1. **SSL Default** - aiohttp was using `ssl:default` which tries SSL verification on HTTP!
2. **Docker Networking** - `localhost` inside a Docker container ≠ host's `localhost`

---

## The Fix

### 1. ✅ SSL Explicitly Disabled

```python
# v2.2.1: CRITICAL - ssl=False in connector!
connector = aiohttp.TCPConnector(ssl=False)
```

### 2. ✅ Docker Networking Auto-Discovery

```python
# v2.2.1: Try multiple URLs for Docker compatibility
SEARXNG_URL_CANDIDATES = [
    'http://localhost:8888',            # Host machine
    'http://host.docker.internal:8888', # Docker Desktop
    'http://172.17.0.1:8888',           # Docker bridge
    'http://qonqrete-searxng:8888',     # Compose service
]

async def _probe_searxng_urls(self):
    """Probe all URLs to find working SearXNG."""
```

### 3. ✅ POST Request Verified

```python
# v2.2.1: POST with form data (matches curl command)
form_data = {
    'q': query,
    'format': 'json',
    'categories': 'it'
}
async with session.post(search_url, data=form_data) as response:
```

---

## v2.2.0 b3c3 Results Analysis

| Metric | Actual | vs Prediction |
|--------|--------|---------------|
| WoNQ Score | ~460/666 | Below (predicted 550-620) |
| Tool Code | 196 refs | ✅ GOOD |
| Copypasta | 36 markers | Still present |
| ConfigLoader | 0 | ✅ ELIMINATED |

**Why below prediction:** SearXNG SSL error → no web code fetched!

---

## v2.2.1 Expected Results

With SearXNG working properly:

### b3c3 Build

| Metric | v2.2.0 Actual | v2.2.1 Expected |
|--------|---------------|-----------------|
| WoNQ Score | ~460/666 | **550-620/666** |
| Web Code % | 0% | **60-80%** |
| Copypasta | 37% | **10-20%** |

### b16c6 Build

| Metric | Estimated | v2.2.1 Expected |
|--------|-----------|-----------------|
| WoNQ Score | ~500/666 | **590-650/666** |
| Web Code % | ~5% | **65-85%** |

---

## Files Changed

| File | Change |
|------|--------|
| `VERSION` | 2.2.1 |
| `worqer/mindstaq/qrawler.py` | SSL fix + Docker networking |
| `worqer/mindstaq/__init__.py` | Version update |
| `worqer/mindstaq/triple_threat.py` | Version update |
| `worqer/mindstaq/sqavenger.py` | Version update |

---

## Requirements

```bash
# Ensure SearXNG is running
docker compose -f docker-compose.searxng.yml up -d

# Verify it works
curl -X POST -d 'q=python&format=json' http://localhost:8888/search | head

# Install Python dependencies
pip install aiohttp beautifulsoup4 duckduckgo-search
```

---

## Docker Compose Network

If running QonQrete and SearXNG in Docker, ensure they're on the same network:

```yaml
# docker-compose.yml
services:
  qonqrete:
    networks:
      - qonqrete-net
  searxng:
    networks:
      - qonqrete-net

networks:
  qonqrete-net:
```

Or use `host.docker.internal:8888` on Docker Desktop.

---

*QonQrete v2.2.1-stable - "SSL? Nah fam, we HTTP gang!"* 🔥

# QonQrete v2.0.7-stable Release Notes

**Release Date:** January 8, 2026  
**Codename:** "SEARXNG POST FIX" 📬

## 🔧 Fix: SearXNG 403 Forbidden Error

Qrawler was using GET requests, but SearXNG requires POST!

### The Problem
```bash
# This returns 403 Forbidden:
curl "http://localhost:8888/search?q=python&format=json"

# SearXNG needs POST:
curl -X POST -d 'q=python&format=json' http://localhost:8888/search
```

### The Fix
Changed Qrawler from `session.get()` to `session.post()`:

```python
# Before (broken):
async with session.get(url, params=params, ...) as response:

# After (fixed):
headers = {'User-Agent': 'QonQrete/2.0.7 (Code Search)'}
async with session.post(url, data=params, headers=headers, ...) as response:
```

### Also Added
- User-Agent header to avoid bot detection
- Updated version strings throughout

### Verify It Works
```bash
# Start SearXNG (if not running)
docker run -d --name qonqrete-searxng -p 8888:8080 \
  -e SEARXNG_SECRET=qonqrete-secret-123 searxng/searxng:latest

# Run QonQrete - should now see:
# [Qrawler] Engines used: ['searxng']
./qonqrete.sh -a -b 2 -c 12 -n "test"
```

---

**SearXNG Integration Finally Complete!** 📬✅

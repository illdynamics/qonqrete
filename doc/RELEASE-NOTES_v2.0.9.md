# QonQrete v2.0.9-stable Release Notes

**Release Date:** January 8, 2026  
**Codename:** "LIMITER DISABLED" 🔓

## 🔧 Fix: SearXNG 403 Forbidden on JSON API

SearXNG has bot detection that blocks API requests. This release disables it for local use.

### The Problem
```bash
curl -X POST -d 'q=test&format=json' http://localhost:8888/search
# Returns: 403 Forbidden (bot detection)
```

### The Solution
Added `searxng/limiter.toml` that allows all IPs:
```toml
[botdetection.ip_limit]
link_token = false

[botdetection.ip_lists]
pass_ip = [
    "0.0.0.0/0",
    "::/0",
]
```

And `searxng/settings.yml` with `limiter: false`.

### Quick Start
```bash
# Fix permissions and start
./fix-searxng.sh

# Or manually:
sudo chown -R $(id -u):$(id -g) searxng/
docker compose -f docker-compose.searxng.yml down -v
docker compose -f docker-compose.searxng.yml up -d
```

### Verify
```bash
# This should now return JSON!
curl -X POST -d 'q=python&format=json' http://localhost:8888/search | head -50
```

---

**SearXNG API Now Open For Business!** 🔓✅

# QonQrete v2.2.5-stable Release Notes

## 🔧 SIMPLIFIED! Back to What Worked! 🔧

**Release Date:** January 2025  
**Type:** Network Simplification Fix

---

## The Problem

v2.2.2-v2.2.4 introduced complex Docker networking:
- Multiple URL probing
- Internal port 8080
- Docker network creation/joining
- Container service names

**This caused failures** because the SearXNG container wasn't always on the same network.

---

## The Solution

**v2.2.5: Back to basics!**

Just use `http://172.17.0.1:8888` - the Docker bridge gateway to host port 8888.

This is what worked before and it's simple + reliable!

---

## Changes

### 1. qrawler.py - SIMPLIFIED!

```python
# BEFORE (v2.2.2-v2.2.4):
SEARXNG_URL_CANDIDATES = [
    'http://qonqrete-searxng:8080',     # Container name (INTERNAL!)
    'http://searxng:8080',              # Alternative name
    'http://172.17.0.1:8888',           # Bridge gateway
    'http://host.docker.internal:8888', # Docker Desktop
    'http://localhost:8888',            # Host
]

async def _probe_searxng_urls(self):
    # Complex probing of multiple URLs...

# AFTER (v2.2.5):
# Just use the default directly!
self.searxng_url = qrawler_cfg.get('searxng_url', 'http://172.17.0.1:8888')

# No more probing! Just use the URL directly!
search_url = f"{self.searxng_url}/search"
```

### 2. qonqrete.sh - REMOVED network flag

```bash
# BEFORE (v2.2.2-v2.2.4):
docker network create qonqrete-net 2>/dev/null || true
NETWORK_FLAG="--network qonqrete-net"
docker run ... $NETWORK_FLAG ...

# AFTER (v2.2.5):
# Just run normally on default bridge network
docker run ... (no network flag)
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  HOST MACHINE                                               │
│                                                             │
│  ┌─────────────────┐                                        │
│  │   SearXNG       │◀─── Port 8888 exposed to host          │
│  │   Container     │                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ localhost:8888                                  │
│           │                                                 │
├───────────┼─────────────────────────────────────────────────┤
│           │                                                 │
│  Docker Bridge Gateway: 172.17.0.1                          │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │   QonQrete      │                                        │
│  │   Container     │───▶ http://172.17.0.1:8888/search      │
│  │                 │     (reaches host's port 8888)         │
│  └─────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**172.17.0.1** = Docker's default bridge gateway that routes to the host machine.

When QonQrete container requests `http://172.17.0.1:8888`, it reaches the host's port 8888, which is where SearXNG is exposed!

---

## Files Changed

| File | Change |
|------|--------|
| `VERSION` | 2.2.5 |
| `worqer/mindstaq/qrawler.py` | Removed URL probing, use 172.17.0.1:8888 directly |
| `worqer/mindstaq/__init__.py` | Version update |
| `worqer/mindstaq/sqavenger.py` | Version update |
| `worqer/mindstaq/triple_threat.py` | Version update |
| `qonqrete.sh` | Removed docker network creation/joining |

---

## Test It!

```bash
# Make sure SearXNG is running on host port 8888
docker compose -f docker-compose.searxng.yml up -d

# Verify SearXNG is accessible
curl -X POST -d 'q=python&format=json' http://localhost:8888/search | head

# Run QonQrete - no special network setup needed!
./qonqrete.sh qonstruqt -t worqspace/tasq.md

# In logs you should see:
# [QRAWLER INFO] Qrawler v2.2.5: SearXNG=http://172.17.0.1:8888, enabled=True
# [QRAWLER INFO] SearXNG POST to http://172.17.0.1:8888/search: ...
# [QRAWLER INFO] SearXNG response: 200
```

---

## Retains v2.2.4 Features

- ✅ WEB SEARCH FIRST priority (not templates)
- ✅ Quality assessment for web results
- ✅ SQAVENGER weight 5.0 in Triple Threat
- ✅ Enhanced copypasta penalties
- ✅ SSL=False for all connections
- ✅ DuckDuckGo fallback

---

*QonQrete v2.2.5-stable - "Simple is Better! 172.17.0.1:8888 FTW!"* 🔧

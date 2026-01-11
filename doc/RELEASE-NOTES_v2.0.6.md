# QonQrete v2.0.6-stable Release Notes

**Release Date:** January 8, 2026  
**Codename:** "SEARXNG JUST WORKS" 🎯

## 🔧 Fix: SearXNG Permission Issues

v2.0.4 and v2.0.5 had issues with custom SearXNG config:
- Volume mount caused permission denied errors
- Custom settings conflicted with SearXNG defaults
- Cached bad config kept breaking restarts

### The Solution: NO Custom Config!

v2.0.6 removes the volume mount entirely. SearXNG uses its built-in defaults which:
- Work out of the box ✅
- Have 70+ engines enabled ✅
- Don't need any custom settings ✅

### Quick Start

```bash
# If you had v2.0.4/v2.0.5 broken config:
sudo rm -rf searxng/

# Start fresh
docker compose -f docker-compose.searxng.yml up -d

# Verify
curl http://localhost:8888/
```

### What Changed

| v2.0.5 | v2.0.6 |
|--------|--------|
| `volumes: ./searxng:/etc/searxng` | NO volume mount |
| Custom settings.yml | Container defaults |
| Permission issues | Just works! |

### Files Removed
- `searxng/` folder - not needed anymore!

---

**SearXNG Finally Just Works!** 🎯✅

# QonQrete v2.0.8-stable Release Notes

**Release Date:** January 8, 2026  
**Codename:** "SEARXNG PERMISSIONS FIX" 🔐

## 🔧 Fix: SearXNG Permission Denied Error

The `cap_drop: ALL` security restriction was preventing SearXNG from creating its config file.

### The Problem
```
cp: can't create '/etc/searxng/settings.yml': Permission denied
!!! ERROR
!!! "/etc/searxng/settings.yml" is not a valid file, exiting...
```

### The Solution
- Removed `cap_drop: ALL` / `cap_add` restrictions
- Use named Docker volume `searxng-data:/etc/searxng:rw`
- Container can now write its own config on first start

### Quick Start
```bash
# Clean everything and start fresh
./fix-searxng.sh

# Or manually:
docker compose -f docker-compose.searxng.yml down -v
docker volume rm qonqrete_searxng-data 2>/dev/null
docker compose -f docker-compose.searxng.yml up -d
```

### Verify
```bash
# Check container is UP (not Restarting)
docker ps | grep searxng

# Test web UI
curl http://localhost:8888/

# Test search API
curl -X POST -d 'q=python&format=json' http://localhost:8888/search
```

---

**SearXNG Finally Working For Real!** 🔐✅

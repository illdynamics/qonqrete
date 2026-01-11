# QonQrete v2.0.5-stable Release Notes

**Release Date:** January 7, 2026  
**Codename:** "SEARXNG FIX" 🔧

## 🔧 Bug Fix: SearXNG Configuration

Fixed SearXNG crashing due to non-existent engine names in v2.0.4.

### The Problem
v2.0.4 settings.yml referenced engines that don't exist in SearXNG 2026.1:
- `stackoverflow` → REMOVED from SearXNG
- `mdn` → REMOVED from SearXNG  
- `ahmia` → REMOVED from SearXNG
- `torch` → REMOVED from SearXNG
- `searchcode` → Ambiguous shortcut conflict

### The Fix
Now using truly minimal config with `use_default_settings: true`:
- NO custom engine definitions
- Let SearXNG use its 70+ built-in working engines
- Google, DuckDuckGo, Bing, Wikipedia, GitHub all work by default!

### If You Had v2.0.4 Running (Broken)

**You MUST clean up the old cached config:**

```bash
# Run the fix script
./fix-searxng.sh

# OR manually:
docker compose -f docker-compose.searxng.yml down -v
docker stop qonqrete-searxng qonqrete-redis
docker rm qonqrete-searxng qonqrete-redis
rm -rf searxng/__pycache__
docker compose -f docker-compose.searxng.yml up -d
```

### Verify It Works

```bash
# Check container is running (not restarting)
docker ps | grep searxng
# Should show "Up X seconds" not "Restarting"

# Test the web interface
curl http://localhost:8888/
# Should return HTML, not connection refused
```

### New Files
- `fix-searxng.sh` - Cleanup script for broken SearXNG

---

**SearXNG Fixed For Real This Time!** 🔧✅

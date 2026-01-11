# QonQrete v1.9.6-stable Release Notes

**Release Date:** January 7, 2026  
**Codename:** "Logging Liberation"

## 🎯 Critical Fix: Subprocess Hang Resolved!

This release fixes the critical hang issue that was introduced in v1.9.3 when comprehensive logging was added to all mindstaQ agents.

### Root Cause Identified

The hang was caused by the **MindstaQLogger infrastructure** that was added in v1.9.3. When `MindstaQEngine.get_instance()` was called with a `struqture_dir`, it triggered `configure_logging()` which created multiple logger instances with file handles and threading locks.

This caused a deadlock scenario when:
1. Subprocess (construqtor) starts
2. Subprocess imports `worqer.mindstaq`
3. Logger infrastructure initializes with file handles
4. Something in the logger/threading code blocks
5. Subprocess hangs, qrane waits forever

### The Solution

**Disabled the logging infrastructure entirely:**

```python
# v1.9.6: Logging disabled (caused subprocess hangs)
HAS_LOGGER = False
```

With `HAS_LOGGER = False`, the `configure_logging()` and `get_logger()` calls are never executed, and the system works correctly.

## 📊 Changes Summary

### worqer/mindstaq/__init__.py
- Set `HAS_LOGGER = False` to disable logging infrastructure
- This prevents `configure_logging()` from being called during MindstaQEngine initialization

### Still Included from v1.9.5
- Python `-u` flag on all subprocess calls (unbuffered output)
- `PYTHONUNBUFFERED=1` environment variable
- `sys.stdout.reconfigure(line_buffering=True)` in all agents

## 🔬 Debugging Session Summary

The issue was traced through multiple debugging sessions:

1. **v1.9.4**: Added lazy SDK imports - didn't fix it
2. **v1.9.5**: Added unbuffered output everywhere - didn't fix it
3. **v1.9.6**: Disabled mindstaq logging - **FIXED!**

Key insight: Running construqtor **directly** always worked. Running it through qrane (as subprocess) hung. This pointed to something in the subprocess initialization, not the code logic itself.

## 🚀 Impact

| Scenario | v1.9.3-v1.9.5 | v1.9.6 |
|----------|---------------|--------|
| Local mode (mindstaQ) | HANGS | ✅ Works |
| API mode (Gemini etc) | Works | ✅ Works |
| All agents | Various hangs | ✅ Works |

## 📋 What's Temporarily Disabled

The following logging features are disabled in v1.9.6:
- `events_*.log` files for mindstaq agents
- `qonsole_*.log` entries from mindstaq agents
- Unified MindstaQLogger infrastructure

**Note:** The core qrane logging (`qonsole_construqtor.log`, `events_construqtor.log`, etc.) still works - only the internal mindstaq agent logging is disabled.

## 🔧 Future Work

The logging infrastructure can be re-enabled once the root cause is properly diagnosed. Possible fixes:
- Use multiprocessing-safe logging (e.g., `QueueHandler`)
- Lazy logger initialization (only create when first used)
- Avoid file handles during subprocess initialization
- Use environment-based logging configuration

## 📦 Upgrade Path

Simply replace your existing QonQrete installation:

```bash
mv qonqrete qonqrete_backup
unzip qonqrete_v1.9.6-stable.zip
mv qonqrete_v1.9.6-stable qonqrete
```

## 🧪 Verified Working

Tested with:
- Local provider (mindstaQ) - ✅ Working
- Multiple briqs - ✅ Processing correctly
- Full pipeline - ✅ No hangs

---

**The local-first revolution is back!** 🔥

ConstruQtor now works reliably in all modes.

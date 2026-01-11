# QonQrete v1.9.5-stable Release Notes

**Release Date:** January 7, 2026  
**Codename:** "Unbuffered Liberation"

## 🎯 Critical Fix: Subprocess Output Buffering

This release fixes a critical hang issue where construqtor (and other agents) would hang during execution due to Python's output buffering when running as subprocesses.

### The Problem

When QonQrete agents run as subprocesses (via qrane orchestrator), Python's default stdout buffering caused output to get stuck in buffers instead of being immediately available to the parent process. This manifested as:

1. **Agent appears to hang** - First line prints, then nothing
2. **Incomplete logs** - Only partial output written to qonsole_*.log
3. **Process never completes** - Even though code is running

The issue was particularly visible with construqtor:
```
--- ConstruQtor v0.9.0: Processing 6 Briqs (Interleaved) ---
(hang - no more output)
```

### The Solution: Triple Unbuffered Output (v1.9.5)

We've implemented a comprehensive fix at THREE levels:

#### 1. Python Interpreter Flag (`-u`)
```python
# qrane/qrane.py - all subprocess calls now use -u
cmd = ["python3", "-u", str(AGENT_MODULE_DIR / script)] + input_paths
```

#### 2. Environment Variable
```python
env["PYTHONUNBUFFERED"] = "1"  # Force unbuffered at OS level
```

#### 3. In-Process Configuration
```python
# All agents now configure unbuffered output at startup
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)
```

## 📊 Changes Summary

### qrane/qrane.py
- Added `-u` flag to ALL Python subprocess calls
- Added `PYTHONUNBUFFERED=1` to both `initial_env` and cycle `env`
- All 4 agent command constructions updated

### worqer/*.py (All Agents)
- Added `sys.stdout.reconfigure(line_buffering=True)` to:
  - construqtor.py
  - instruqtor.py
  - inspeqtor.py
  - qompressor.py
  - qontextor.py
  - qontrabender.py

## 🚀 Impact

| Scenario | v1.9.4 | v1.9.5 |
|----------|--------|--------|
| Subprocess output | Buffered (hangs) | Unbuffered (instant) |
| Log completeness | Partial | Complete |
| Agent reliability | Intermittent hangs | Stable |

## 🔧 Technical Details

Python's default behavior when stdout is a pipe (not a TTY):
- **Block buffering**: Output collected in 4-64KB chunks before writing
- Even `print(..., flush=True)` may not fully flush at C level
- The `-u` flag and `PYTHONUNBUFFERED` disable this at interpreter level
- `reconfigure(line_buffering=True)` ensures Python's IO layer is also unbuffered

## 📋 Full Changelog

### Fixed
- **CRITICAL:** Subprocess hanging due to stdout buffering
- All agents now output immediately when running via qrane

### Changed
- All Python subprocess calls use `-u` flag
- Environment includes `PYTHONUNBUFFERED=1`
- All agents configure line-buffered stdout at startup

## 🧪 Testing

Run any build to verify the fix:

```bash
./qonqrete.sh -a -b 3 -c 1 -n "test195"
```

Expected behavior:
- All status lines appear immediately
- No hanging between prints
- Complete logs in struqture/qonsole_*.log

## 📦 Upgrade Path

Simply replace your existing QonQrete installation with v1.9.5:

```bash
# Backup existing
mv qonqrete qonqrete_backup

# Install v1.9.5
unzip qonqrete_v1.9.5-stable.zip
mv qonqrete_v1.9.5-stable qonqrete
```

---

**No more subprocess hangs!** 🔥

The orchestrator now gets real-time output from all agents.

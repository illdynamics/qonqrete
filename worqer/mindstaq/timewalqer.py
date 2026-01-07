#!/usr/bin/env python3
"""
TimeWalQer: Git-less Snapshot/Revert System for CyQle Time Travel
Part of mindstaQ - Pure filesystem-based state serialization, NO GIT, NO CLOUD

TimeWalQer is QonQrete's "Save Game" system:
- Drops a Timestone after every successful InspeQtor pass
- Enables time travel to any previous cyQle state
- Auto-reverts on hard failures
- Uses hard links for storage efficiency (cp -al)
- Maintains graveyard.d/ for failed attempt forensics

Pipeline Position:
  InstruQtor → ConstruQtor → [Qalibrator ⟷ Qualifier] → InspeQtor → TimeWalQer
                                                              ↓
                                                    SUCCESS: Drop Timestone
                                                    FAIL: Auto-Revert

Directory Structure:
  cheqpoint.d/
  ├── 0-cyQle/          ← Golden Genesis (Factory Reset)
  ├── 1-cyQle/          ← After CyQle 1 passed
  ├── 2-cyQle/          ← After CyQle 2 passed
  ├── ...
  ├── timeline.yaml     ← Master timeline index
  └── graveyard.d/      ← Failed attempts (forensics)

CLI Usage:
  ./qonqrete.sh time              # Warp back one cyQle
  ./qonqrete.sh time -c 0         # Reset to initial state
  ./qonqrete.sh time -c 5         # Warp to cyQle 5
  ./qonqrete.sh time --list       # Show all timestones
  ./qonqrete.sh time --diff 3     # Show diff vs cyQle 3
  ./qonqrete.sh time --dry-run -c 2  # Preview warp without applying

v1.7.8-stable - Initial release with full time travel support

Usage:
    timewalqer = TimeWalQer(config={'enabled': True})
    timewalqer.drop_timestone(cyqle_num=5, tasq_name="Add Redis caching")
    timewalqer.warp_to(cyqle_num=3)
"""

import os
import sys
import shutil
import hashlib
import subprocess
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
import yaml
import json


__version__ = '1.7.2-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Directories to snapshot (relative to worqspace root)
SNAPSHOT_DIRS = [
    'qodeyard',
    'qontext.d',
    'bloq.d',
    'tasq.d',
    'reqap.d',
    'briq.d',
    'struqture',
]

# Files to snapshot (relative to worqspace root)
SNAPSHOT_FILES = [
    'config.yaml',
    'tasq.md',
]

# Directories to exclude from snapshots
EXCLUDE_PATTERNS = [
    '__pycache__',
    '*.pyc',
    '.git',
    'node_modules',
    'venv',
    '.venv',
]


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

class TimestoneStatus(Enum):
    """Status of a timestone."""
    VERIFIED = "verified"      # Passed all checks
    PARTIAL = "partial"        # Some checks passed
    RECOVERED = "recovered"    # Restored from failure
    GENESIS = "genesis"        # Initial state (cyQle 0)


@dataclass
class Timestone:
    """A snapshot of system state at a specific cyQle."""
    cyqle: int
    timestamp: str
    status: TimestoneStatus
    tasq_name: str = ""
    files_changed: int = 0
    lines_changed: int = 0
    checksum: str = ""
    notes: str = ""
    parent_cyqle: int = -1
    
    def to_dict(self) -> Dict:
        return {
            'cyqle': self.cyqle,
            'timestamp': self.timestamp,
            'status': self.status.value,
            'tasq_name': self.tasq_name,
            'files_changed': self.files_changed,
            'lines_changed': self.lines_changed,
            'checksum': self.checksum,
            'notes': self.notes,
            'parent_cyqle': self.parent_cyqle,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Timestone':
        return cls(
            cyqle=data['cyqle'],
            timestamp=data['timestamp'],
            status=TimestoneStatus(data['status']),
            tasq_name=data.get('tasq_name', ''),
            files_changed=data.get('files_changed', 0),
            lines_changed=data.get('lines_changed', 0),
            checksum=data.get('checksum', ''),
            notes=data.get('notes', ''),
            parent_cyqle=data.get('parent_cyqle', -1),
        )


@dataclass
class WarpResult:
    """Result of a time warp operation."""
    success: bool
    from_cyqle: int
    to_cyqle: int
    files_restored: int
    message: str
    dry_run: bool = False


@dataclass
class Timeline:
    """Master timeline tracking all timestones."""
    timestones: List[Timestone] = field(default_factory=list)
    current_cyqle: int = 0
    last_warp: str = ""
    total_warps: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'timestones': [t.to_dict() for t in self.timestones],
            'current_cyqle': self.current_cyqle,
            'last_warp': self.last_warp,
            'total_warps': self.total_warps,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Timeline':
        return cls(
            timestones=[Timestone.from_dict(t) for t in data.get('timestones', [])],
            current_cyqle=data.get('current_cyqle', 0),
            last_warp=data.get('last_warp', ''),
            total_warps=data.get('total_warps', 0),
        )
    
    def add_timestone(self, ts: Timestone):
        """Add a timestone to the timeline."""
        # Remove any existing timestone for this cyqle
        self.timestones = [t for t in self.timestones if t.cyqle != ts.cyqle]
        self.timestones.append(ts)
        self.timestones.sort(key=lambda t: t.cyqle)
        self.current_cyqle = ts.cyqle
    
    def get_timestone(self, cyqle: int) -> Optional[Timestone]:
        """Get a timestone by cyqle number."""
        for ts in self.timestones:
            if ts.cyqle == cyqle:
                return ts
        return None
    
    def get_latest(self) -> Optional[Timestone]:
        """Get the most recent timestone."""
        if self.timestones:
            return self.timestones[-1]
        return None
    
    def get_previous(self) -> Optional[Timestone]:
        """Get the second-to-last timestone (for revert)."""
        if len(self.timestones) >= 2:
            return self.timestones[-2]
        elif len(self.timestones) == 1:
            return self.timestones[0]
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FAILED ATTEMPT TRACKING (GRAVEYARD)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FailedAttempt:
    """Record of a failed cyQle attempt."""
    cyqle: int
    timestamp: str
    error_type: str
    error_message: str
    bloq_hash: str = ""
    diff_summary: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'cyqle': self.cyqle,
            'timestamp': self.timestamp,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'bloq_hash': self.bloq_hash,
            'diff_summary': self.diff_summary,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN TIMEWALQER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class TimeWalQer:
    """
    Git-less Snapshot/Revert System for CyQle Time Travel.
    
    Manages cheqpoint.d/ directory with timestones for each successful cyQle.
    Enables time travel to any previous state without Git complexity.
    """
    
    def __init__(self, config: dict = None, worqspace_root: str = None):
        """
        Initialize TimeWalQer.
        
        Args:
            config: Dictionary with settings:
                - enabled: Enable/disable TimeWalQer (default: True)
                - use_hardlinks: Use cp -al for storage efficiency (default: True)
                - auto_revert: Auto-revert on failures (default: True)
                - max_timestones: Max timestones to keep (default: 100, 0=unlimited)
                - graveyard_enabled: Track failed attempts (default: True)
                - snapshot_dirs: Override default snapshot directories
                - snapshot_files: Override default snapshot files
            worqspace_root: Path to worqspace root (default: current directory)
        """
        config = config or {}
        
        self.enabled = config.get('enabled', True)
        self.use_hardlinks = config.get('use_hardlinks', True)
        self.auto_revert = config.get('auto_revert', True)
        self.max_timestones = config.get('max_timestones', 100)
        self.graveyard_enabled = config.get('graveyard_enabled', True)
        
        self.snapshot_dirs = config.get('snapshot_dirs', SNAPSHOT_DIRS)
        self.snapshot_files = config.get('snapshot_files', SNAPSHOT_FILES)
        
        # Set worqspace root
        self.worqspace_root = Path(worqspace_root) if worqspace_root else Path.cwd()
        self.cheqpoint_dir = self.worqspace_root / 'cheqpoint.d'
        self.graveyard_dir = self.cheqpoint_dir / 'graveyard.d'
        self.timeline_file = self.cheqpoint_dir / 'timeline.yaml'
        
        # Initialize directories
        if self.enabled:
            self._init_directories()
        
        # Load timeline
        self.timeline = self._load_timeline()
    
    def _init_directories(self):
        """Initialize cheqpoint.d structure."""
        self.cheqpoint_dir.mkdir(parents=True, exist_ok=True)
        if self.graveyard_enabled:
            self.graveyard_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_timeline(self) -> Timeline:
        """Load timeline from disk."""
        if self.timeline_file.exists():
            try:
                with open(self.timeline_file, 'r') as f:
                    data = yaml.safe_load(f)
                    if data:
                        return Timeline.from_dict(data)
            except Exception as e:
                print(f"⚠️ TimeWalQer: Could not load timeline: {e}")
        return Timeline()
    
    def _save_timeline(self):
        """Save timeline to disk."""
        try:
            with open(self.timeline_file, 'w') as f:
                yaml.dump(self.timeline.to_dict(), f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"⚠️ TimeWalQer: Could not save timeline: {e}")
    
    def _get_cyqle_dir(self, cyqle: int) -> Path:
        """Get the directory for a specific cyQle."""
        return self.cheqpoint_dir / f"{cyqle}-cyQle"
    
    def _calculate_checksum(self, directory: Path) -> str:
        """Calculate a checksum for a directory's contents."""
        hasher = hashlib.sha256()
        
        if not directory.exists():
            return ""
        
        for root, dirs, files in os.walk(directory):
            # Skip excluded patterns
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'node_modules']]
            
            for filename in sorted(files):
                if filename.endswith('.pyc'):
                    continue
                filepath = Path(root) / filename
                try:
                    with open(filepath, 'rb') as f:
                        hasher.update(f.read())
                except Exception:
                    pass
        
        return hasher.hexdigest()[:16]
    
    def _count_changes(self, from_dir: Path, to_dir: Path) -> Tuple[int, int]:
        """Count files and lines changed between two directories."""
        files_changed = 0
        lines_changed = 0
        
        if not from_dir.exists() or not to_dir.exists():
            return 0, 0
        
        # Get all files in both directories
        from_files = set()
        to_files = set()
        
        for root, _, files in os.walk(from_dir):
            for f in files:
                rel = Path(root).relative_to(from_dir) / f
                from_files.add(str(rel))
        
        for root, _, files in os.walk(to_dir):
            for f in files:
                rel = Path(root).relative_to(to_dir) / f
                to_files.add(str(rel))
        
        # Count new/deleted files
        new_files = to_files - from_files
        deleted_files = from_files - to_files
        files_changed += len(new_files) + len(deleted_files)
        
        # Count modified files
        common_files = from_files & to_files
        for rel_path in common_files:
            from_file = from_dir / rel_path
            to_file = to_dir / rel_path
            try:
                with open(from_file, 'r') as f:
                    from_lines = f.readlines()
                with open(to_file, 'r') as f:
                    to_lines = f.readlines()
                if from_lines != to_lines:
                    files_changed += 1
                    lines_changed += abs(len(to_lines) - len(from_lines))
            except Exception:
                pass
        
        return files_changed, lines_changed
    
    def _copy_with_links(self, src: Path, dst: Path):
        """Copy directory with hard links if enabled."""
        if not src.exists():
            return
        
        dst.mkdir(parents=True, exist_ok=True)
        
        if self.use_hardlinks:
            # Try hard link copy (cp -al equivalent)
            try:
                result = subprocess.run(
                    ['cp', '-al', str(src) + '/.', str(dst) + '/'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    return
            except Exception:
                pass
        
        # Fallback to regular copy
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    
    def _copy_file(self, src: Path, dst: Path):
        """Copy a single file."""
        if not src.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    
    def ensure_genesis(self) -> bool:
        """
        Ensure cyQle 0 (Golden Genesis) exists.
        Creates it if it doesn't exist.
        
        Returns:
            True if genesis exists or was created
        """
        genesis_dir = self._get_cyqle_dir(0)
        
        if genesis_dir.exists():
            return True
        
        print("💎 TimeWalQer: Creating Golden Genesis (CyQle 0)...")
        return self.drop_timestone(
            cyqle_num=0,
            tasq_name="Genesis - Initial State",
            status=TimestoneStatus.GENESIS,
            notes="Factory reset point"
        )
    
    def drop_timestone(
        self,
        cyqle_num: int,
        tasq_name: str = "",
        status: TimestoneStatus = TimestoneStatus.VERIFIED,
        notes: str = ""
    ) -> bool:
        """
        Drop a timestone (create snapshot) for the current state.
        
        Call this AFTER successful InspeQtor pass.
        
        Args:
            cyqle_num: The cyQle number for this timestone
            tasq_name: Name of the task that was completed
            status: Status of the timestone
            notes: Optional notes about this snapshot
        
        Returns:
            True if timestone was created successfully
        """
        if not self.enabled:
            print("⚠️ TimeWalQer: Disabled, skipping timestone drop")
            return False
        
        cyqle_dir = self._get_cyqle_dir(cyqle_num)
        
        print(f"💎 TimeWalQer: Dropping Timestone for CyQle {cyqle_num}...")
        
        try:
            # Create cyQle directory
            if cyqle_dir.exists():
                shutil.rmtree(cyqle_dir)
            cyqle_dir.mkdir(parents=True)
            
            # Copy all snapshot directories
            for dir_name in self.snapshot_dirs:
                src = self.worqspace_root / dir_name
                dst = cyqle_dir / dir_name
                if src.exists():
                    self._copy_with_links(src, dst)
            
            # Copy snapshot files
            for file_name in self.snapshot_files:
                src = self.worqspace_root / file_name
                dst = cyqle_dir / file_name
                if src.exists():
                    self._copy_file(src, dst)
            
            # Calculate stats
            checksum = self._calculate_checksum(cyqle_dir)
            
            # Get previous timestone for diff
            prev_ts = self.timeline.get_latest()
            parent_cyqle = prev_ts.cyqle if prev_ts else -1
            files_changed, lines_changed = 0, 0
            
            if prev_ts and parent_cyqle >= 0:
                prev_dir = self._get_cyqle_dir(parent_cyqle)
                files_changed, lines_changed = self._count_changes(prev_dir, cyqle_dir)
            
            # Create timestone record
            timestone = Timestone(
                cyqle=cyqle_num,
                timestamp=datetime.now().isoformat(),
                status=status,
                tasq_name=tasq_name,
                files_changed=files_changed,
                lines_changed=lines_changed,
                checksum=checksum,
                notes=notes,
                parent_cyqle=parent_cyqle,
            )
            
            # Save timestone metadata
            meta_file = cyqle_dir / 'timestone.yaml'
            with open(meta_file, 'w') as f:
                yaml.dump(timestone.to_dict(), f, default_flow_style=False)
            
            # Update timeline
            self.timeline.add_timestone(timestone)
            self._save_timeline()
            
            # Cleanup old timestones if max exceeded
            if self.max_timestones > 0 and len(self.timeline.timestones) > self.max_timestones:
                self._cleanup_old_timestones()
            
            print(f"✨ TimeWalQer: Timestone {cyqle_num} created ({files_changed} files, {lines_changed} lines)")
            return True
            
        except Exception as e:
            print(f"❌ TimeWalQer: Failed to create timestone: {e}")
            return False
    
    def warp_to(self, cyqle_num: int, dry_run: bool = False) -> WarpResult:
        """
        Warp (restore) to a specific cyQle state.
        
        Args:
            cyqle_num: Target cyQle number to restore
            dry_run: If True, just show what would happen
        
        Returns:
            WarpResult with operation details
        """
        if not self.enabled:
            return WarpResult(
                success=False,
                from_cyqle=self.timeline.current_cyqle,
                to_cyqle=cyqle_num,
                files_restored=0,
                message="TimeWalQer is disabled",
                dry_run=dry_run
            )
        
        cyqle_dir = self._get_cyqle_dir(cyqle_num)
        
        if not cyqle_dir.exists():
            return WarpResult(
                success=False,
                from_cyqle=self.timeline.current_cyqle,
                to_cyqle=cyqle_num,
                files_restored=0,
                message=f"Timestone {cyqle_num} does not exist",
                dry_run=dry_run
            )
        
        from_cyqle = self.timeline.current_cyqle
        
        if dry_run:
            # Just count what would be restored
            files_count = sum(1 for _ in cyqle_dir.rglob('*') if _.is_file())
            return WarpResult(
                success=True,
                from_cyqle=from_cyqle,
                to_cyqle=cyqle_num,
                files_restored=files_count,
                message=f"Would restore {files_count} files from CyQle {cyqle_num}",
                dry_run=True
            )
        
        print(f"⏳ TimeWalQer: Warping from CyQle {from_cyqle} to CyQle {cyqle_num}...")
        
        try:
            files_restored = 0
            
            # Restore directories
            for dir_name in self.snapshot_dirs:
                src = cyqle_dir / dir_name
                dst = self.worqspace_root / dir_name
                
                if src.exists():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    files_restored += sum(1 for _ in dst.rglob('*') if _.is_file())
            
            # Restore files
            for file_name in self.snapshot_files:
                src = cyqle_dir / file_name
                dst = self.worqspace_root / file_name
                
                if src.exists():
                    shutil.copy2(src, dst)
                    files_restored += 1
            
            # Update timeline
            self.timeline.current_cyqle = cyqle_num
            self.timeline.last_warp = datetime.now().isoformat()
            self.timeline.total_warps += 1
            self._save_timeline()
            
            print(f"✨ TimeWalQer: Warped to CyQle {cyqle_num} ({files_restored} files restored)")
            
            return WarpResult(
                success=True,
                from_cyqle=from_cyqle,
                to_cyqle=cyqle_num,
                files_restored=files_restored,
                message=f"Successfully warped to CyQle {cyqle_num}",
                dry_run=False
            )
            
        except Exception as e:
            return WarpResult(
                success=False,
                from_cyqle=from_cyqle,
                to_cyqle=cyqle_num,
                files_restored=0,
                message=f"Warp failed: {e}",
                dry_run=False
            )
    
    def revert_one(self) -> WarpResult:
        """
        Revert to the previous cyQle (N-1).
        
        Returns:
            WarpResult with operation details
        """
        prev = self.timeline.get_previous()
        if prev is None:
            return WarpResult(
                success=False,
                from_cyqle=self.timeline.current_cyqle,
                to_cyqle=-1,
                files_restored=0,
                message="No previous timestone to revert to"
            )
        
        return self.warp_to(prev.cyqle)
    
    def auto_revert_on_fail(self, error_type: str = "", error_message: str = "") -> WarpResult:
        """
        Auto-revert to last good state on failure.
        Records the failure in graveyard.d for forensics.
        
        Args:
            error_type: Type of error that caused failure
            error_message: Error message details
        
        Returns:
            WarpResult with operation details
        """
        if not self.auto_revert:
            return WarpResult(
                success=False,
                from_cyqle=self.timeline.current_cyqle,
                to_cyqle=-1,
                files_restored=0,
                message="Auto-revert is disabled"
            )
        
        # Record failure in graveyard
        if self.graveyard_enabled:
            self._record_failure(error_type, error_message)
        
        # Revert to last good state
        latest = self.timeline.get_latest()
        if latest:
            print(f"🔄 TimeWalQer: Auto-reverting to last good state (CyQle {latest.cyqle})...")
            return self.warp_to(latest.cyqle)
        else:
            return WarpResult(
                success=False,
                from_cyqle=self.timeline.current_cyqle,
                to_cyqle=-1,
                files_restored=0,
                message="No timestone available for auto-revert"
            )
    
    def _record_failure(self, error_type: str, error_message: str):
        """Record a failed attempt in the graveyard."""
        if not self.graveyard_enabled:
            return
        
        current_cyqle = self.timeline.current_cyqle + 1  # Failed attempt
        
        failure = FailedAttempt(
            cyqle=current_cyqle,
            timestamp=datetime.now().isoformat(),
            error_type=error_type,
            error_message=error_message[:500],  # Truncate long messages
        )
        
        # Save to graveyard
        failure_file = self.graveyard_dir / f"failed-{current_cyqle}-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"
        try:
            with open(failure_file, 'w') as f:
                yaml.dump(failure.to_dict(), f, default_flow_style=False)
        except Exception as e:
            print(f"⚠️ TimeWalQer: Could not record failure: {e}")
    
    def _cleanup_old_timestones(self):
        """Remove old timestones when max is exceeded."""
        if self.max_timestones <= 0:
            return
        
        # Keep genesis (0) and latest ones
        while len(self.timeline.timestones) > self.max_timestones:
            oldest = self.timeline.timestones[1]  # Don't remove genesis
            cyqle_dir = self._get_cyqle_dir(oldest.cyqle)
            
            if cyqle_dir.exists():
                shutil.rmtree(cyqle_dir)
            
            self.timeline.timestones.remove(oldest)
            print(f"🗑️ TimeWalQer: Cleaned up old timestone {oldest.cyqle}")
        
        self._save_timeline()
    
    def list_timestones(self) -> List[Timestone]:
        """List all available timestones."""
        return self.timeline.timestones
    
    def get_diff(self, cyqle_num: int) -> str:
        """
        Get a diff summary between current state and a specific cyQle.
        
        Args:
            cyqle_num: CyQle to compare against
        
        Returns:
            Diff summary string
        """
        cyqle_dir = self._get_cyqle_dir(cyqle_num)
        
        if not cyqle_dir.exists():
            return f"Timestone {cyqle_num} does not exist"
        
        lines = [f"Diff vs CyQle {cyqle_num}:", "=" * 40]
        
        for dir_name in self.snapshot_dirs:
            src = cyqle_dir / dir_name
            dst = self.worqspace_root / dir_name
            
            if src.exists() and dst.exists():
                files_changed, lines_changed = self._count_changes(src, dst)
                if files_changed > 0:
                    lines.append(f"  {dir_name}/: {files_changed} files, ~{lines_changed} lines")
            elif src.exists():
                lines.append(f"  {dir_name}/: DELETED")
            elif dst.exists():
                lines.append(f"  {dir_name}/: NEW")
        
        return "\n".join(lines)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current TimeWalQer status."""
        return {
            'enabled': self.enabled,
            'current_cyqle': self.timeline.current_cyqle,
            'total_timestones': len(self.timeline.timestones),
            'total_warps': self.timeline.total_warps,
            'last_warp': self.timeline.last_warp,
            'cheqpoint_dir': str(self.cheqpoint_dir),
            'use_hardlinks': self.use_hardlinks,
            'auto_revert': self.auto_revert,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI interface for TimeWalQer."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="TimeWalQer - CyQle Time Travel System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Revert one cyQle back
  %(prog)s -c 0               # Reset to initial state (genesis)
  %(prog)s -c 5               # Warp to cyQle 5
  %(prog)s --list             # Show all timestones
  %(prog)s --diff 3           # Show diff vs cyQle 3
  %(prog)s -c 2 --dry-run     # Preview warp without applying
  %(prog)s --status           # Show TimeWalQer status
  %(prog)s --genesis          # Ensure genesis (cyQle 0) exists
        """
    )
    
    parser.add_argument('-c', '--cyqle', type=int, help='Target cyQle number to warp to')
    parser.add_argument('--list', action='store_true', help='List all timestones')
    parser.add_argument('--diff', type=int, metavar='N', help='Show diff vs cyQle N')
    parser.add_argument('--dry-run', action='store_true', help='Preview without applying')
    parser.add_argument('--status', action='store_true', help='Show TimeWalQer status')
    parser.add_argument('--genesis', action='store_true', help='Ensure genesis exists')
    parser.add_argument('--drop', type=int, metavar='N', help='Drop timestone for cyQle N')
    parser.add_argument('--tasq', default='', help='Task name for --drop')
    
    args = parser.parse_args()
    
    # Initialize TimeWalQer
    tw = TimeWalQer()
    
    if args.status:
        status = tw.get_status()
        print("⏳ TimeWalQer Status")
        print("=" * 40)
        for key, value in status.items():
            print(f"  {key}: {value}")
        return
    
    if args.list:
        timestones = tw.list_timestones()
        if not timestones:
            print("No timestones found.")
            return
        print("⏳ Available Timestones:")
        print("=" * 60)
        for ts in timestones:
            status_icon = "💎" if ts.status == TimestoneStatus.GENESIS else "✅"
            print(f"  {status_icon} CyQle {ts.cyqle}: {ts.tasq_name or '(unnamed)'}")
            print(f"      {ts.timestamp} | {ts.files_changed} files | {ts.status.value}")
        return
    
    if args.diff is not None:
        print(tw.get_diff(args.diff))
        return
    
    if args.genesis:
        tw.ensure_genesis()
        return
    
    if args.drop is not None:
        success = tw.drop_timestone(args.drop, tasq_name=args.tasq)
        if success:
            print(f"✅ Dropped timestone for CyQle {args.drop}")
        else:
            print(f"❌ Failed to drop timestone")
            sys.exit(1)
        return
    
    if args.cyqle is not None:
        result = tw.warp_to(args.cyqle, dry_run=args.dry_run)
    else:
        # No args = revert one
        result = tw.revert_one()
    
    if result.success:
        if result.dry_run:
            print(f"🔍 [DRY RUN] {result.message}")
        else:
            print(f"✅ {result.message}")
    else:
        print(f"❌ {result.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()

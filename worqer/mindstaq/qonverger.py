#!/usr/bin/env python3
"""
Qonverger: The Convergence Agent - Detects gaps and generates creation briqs for cycle 2+

Part of QonQrete v2.1.5 - The "Evolving InstruQtor" feature!

WHAT IT DOES:
- Runs AFTER InspeQtor at end of each cycle
- Compares original tasq.md requirements vs qodeyard output
- Finds MISSING files/modules that weren't created
- Generates "CREATE" briqs that get added to next cycle's tasq
- Ensures convergence toward complete implementation!

PIPELINE POSITION:
  Cycle N: InstruQtor → ConstruQtor → InspeQtor → **Qonverger** → Cycle N+1 tasq

WHY "QONVERGER":
- Converges the implementation toward the specification
- Each cycle gets closer to 100% coverage
- Gap analysis + briq generation = convergence!

Usage:
    qonverger = Qonverger(tasq_content, qodeyard_path)
    gaps = qonverger.find_gaps()
    briqs = qonverger.generate_creation_briqs(gaps)
    suggestions = qonverger.format_for_next_cycle()
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum


__version__ = '1.0.0'
__agent_name__ = 'Qonverger'


# ═══════════════════════════════════════════════════════════════════════════════
# GAP TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class GapType(Enum):
    MISSING_FILE = "missing_file"       # File mentioned in tasq but not created
    MISSING_CLASS = "missing_class"     # Class mentioned but not implemented
    MISSING_FUNCTION = "missing_func"   # Function mentioned but not implemented
    MISSING_MODULE = "missing_module"   # Entire module/directory missing
    INCOMPLETE_FILE = "incomplete"      # File exists but missing key components


@dataclass
class Gap:
    """Represents a single gap between requirements and implementation."""
    gap_type: GapType
    name: str                           # File/class/function name
    path: str                           # Expected path
    description: str                    # What's missing
    priority: int = 5                   # 1-10, higher = more important
    dependencies: List[str] = field(default_factory=list)
    layer: int = 0                      # From dependency graph (0-9)
    
    def to_briq_content(self) -> str:
        """Generate briq markdown content for this gap."""
        return f"""# CREATE: {self.name}

## Priority: {self.priority}/10
## Layer: {self.layer}

## Description
{self.description}

## Expected Path
`{self.path}`

## Dependencies
{chr(10).join(f'- `{d}`' for d in self.dependencies) if self.dependencies else '- None'}

## Requirements
- CREATE this file from scratch (not modify existing)
- Implement full functionality as described in original tasq
- Follow established patterns from existing codebase
- Include proper imports, type hints, and docstrings

## Implementation Notes
This is a GAP-FILL briq - the file was missing from Cycle 1 and must be created now.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# FILE PATTERNS TO EXTRACT FROM TASQ
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns to find file references in tasq.md
FILE_PATTERNS = [
    # Python files: shared/constants.py, src/safety/geofencing.py
    r'(?:^|\s|[`\'"])([a-z_]+(?:/[a-z_]+)*\.py)(?:[`\'"\s]|$)',
    # Directory/module references: LAYER 0, shared/*, safety/*
    r'(?:^|\s)([a-z_]+)/\*',
    # Explicit file mentions: Create file X, Implement X.py
    r'(?:create|implement|write|build)\s+(?:file\s+)?[`\'"]?([a-z_/]+\.py)[`\'"]?',
]

# Patterns to find class definitions mentioned
CLASS_PATTERNS = [
    r'class\s+([A-Z][A-Za-z0-9_]+)',
    r'(?:^|\s)([A-Z][A-Za-z0-9_]+)(?:\s*\(|:|\s+class)',
]

# Layer extraction pattern
LAYER_PATTERN = r'LAYER\s+(\d+)[^:]*:([^\n]+(?:\n[├└│─\s]+[^\n]+)*)'


# ═══════════════════════════════════════════════════════════════════════════════
# GAP ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class Qonverger:
    """
    Analyzes gaps between tasq requirements and actual qodeyard output.
    Generates creation briqs for cycle 2+ to fill these gaps.
    """
    
    def __init__(self, tasq_content: str, qodeyard_path: Path):
        """
        Initialize the gap analyzer.
        
        Args:
            tasq_content: The full tasq.md content
            qodeyard_path: Path to qodeyard directory
        """
        self.tasq_content = tasq_content
        self.qodeyard_path = Path(qodeyard_path)
        
        # Parse tasq to extract requirements
        self.required_files: Dict[str, int] = {}  # path -> layer
        self.required_classes: Set[str] = set()
        self.layer_descriptions: Dict[int, str] = {}
        
        self._parse_tasq()
        
    def _parse_tasq(self):
        """Parse tasq.md to extract all required files and components."""
        # Extract layer structure
        for match in re.finditer(LAYER_PATTERN, self.tasq_content, re.MULTILINE):
            layer_num = int(match.group(1))
            layer_content = match.group(2)
            self.layer_descriptions[layer_num] = layer_content.strip()
            
            # Extract files from this layer
            for file_match in re.finditer(r'([a-z_]+(?:/[a-z_]+)*\.py)', layer_content):
                filepath = file_match.group(1)
                # Normalize path (add src/ prefix if needed)
                if not filepath.startswith('src/') and '/' in filepath:
                    filepath = f"src/{filepath}"
                elif '/' not in filepath:
                    filepath = f"src/{filepath}"
                self.required_files[filepath] = layer_num
        
        # Also extract files mentioned anywhere in tasq
        for pattern in FILE_PATTERNS:
            for match in re.finditer(pattern, self.tasq_content, re.IGNORECASE | re.MULTILINE):
                filepath = match.group(1)
                if filepath not in self.required_files:
                    # Try to guess layer based on path
                    layer = self._guess_layer(filepath)
                    self.required_files[filepath] = layer
        
        # Extract class names
        for pattern in CLASS_PATTERNS:
            for match in re.finditer(pattern, self.tasq_content):
                self.required_classes.add(match.group(1))
                
    def _guess_layer(self, filepath: str) -> int:
        """Guess the layer for a file based on its path."""
        path_lower = filepath.lower()
        if 'shared' in path_lower or 'constants' in path_lower or 'types' in path_lower:
            return 0
        elif 'config' in path_lower:
            return 1
        elif 'safety' in path_lower or 'security' in path_lower:
            return 2
        elif 'ai' in path_lower:
            return 3
        elif 'traffic' in path_lower:
            return 4
        elif 'c2' in path_lower:
            return 5
        elif 'tool' in path_lower:
            return 6
        elif 'intel' in path_lower:
            return 7
        elif 'factory' in path_lower:
            return 8
        elif 'orchestr' in path_lower:
            return 9
        return 5  # Default to middle layer
        
    def get_existing_files(self) -> Set[str]:
        """Get all files that exist in qodeyard."""
        existing = set()
        if self.qodeyard_path.exists():
            for f in self.qodeyard_path.rglob('*'):
                if f.is_file():
                    rel_path = str(f.relative_to(self.qodeyard_path))
                    existing.add(rel_path)
                    # Also add normalized versions
                    if rel_path.startswith('src/'):
                        existing.add(rel_path[4:])
                    else:
                        existing.add(f"src/{rel_path}")
        return existing
        
    def find_gaps(self) -> List[Gap]:
        """
        Find all gaps between requirements and implementation.
        
        Returns:
            List of Gap objects representing missing components
        """
        gaps = []
        existing_files = self.get_existing_files()
        
        # Check each required file
        for filepath, layer in sorted(self.required_files.items(), key=lambda x: (x[1], x[0])):
            # Normalize for comparison
            normalized = filepath.replace('src/', '')
            
            # Check if file exists (with various path variations)
            file_exists = any([
                filepath in existing_files,
                normalized in existing_files,
                f"src/{normalized}" in existing_files,
                filepath.lstrip('./') in existing_files,
            ])
            
            if not file_exists:
                # Extract description from tasq if available
                description = self._extract_description(filepath)
                dependencies = self._extract_dependencies(filepath, layer)
                
                gap = Gap(
                    gap_type=GapType.MISSING_FILE,
                    name=Path(filepath).name,
                    path=filepath,
                    description=description,
                    priority=10 - layer,  # Lower layers = higher priority
                    dependencies=dependencies,
                    layer=layer
                )
                gaps.append(gap)
        
        # Sort by priority (layer order matters for dependencies)
        gaps.sort(key=lambda g: (g.layer, -g.priority, g.name))
        
        return gaps
        
    def _extract_description(self, filepath: str) -> str:
        """Extract description for a file from tasq content."""
        filename = Path(filepath).stem
        
        # Look for description patterns
        patterns = [
            rf'{filename}[^:]*:\s*([^\n]+)',
            rf'`{filename}`[^:]*:\s*([^\n]+)',
            rf'{filename}\.py[^:]*→\s*([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.tasq_content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Generic description based on filename
        return f"Implement {filename} module as specified in the tasq requirements."
        
    def _extract_dependencies(self, filepath: str, layer: int) -> List[str]:
        """Extract dependencies for a file based on layer and tasq content."""
        deps = []
        
        # Files in higher layers depend on lower layers
        if layer > 0:
            deps.append(f"Layer {layer-1} modules")
        
        # Look for explicit dependencies in tasq
        filename = Path(filepath).stem
        dep_pattern = rf'{filename}[^:]*(?:depends|requires|imports)[^:]*:\s*([^\n]+)'
        match = re.search(dep_pattern, self.tasq_content, re.IGNORECASE)
        if match:
            dep_text = match.group(1)
            # Extract module names
            for mod in re.findall(r'([a-z_]+(?:/[a-z_]+)*)', dep_text):
                deps.append(mod)
                
        return deps
        
    def generate_creation_briqs(self, gaps: List[Gap], max_briqs: int = 50) -> List[Dict]:
        """
        Generate briq specifications for creating missing files.
        
        Args:
            gaps: List of gaps to fill
            max_briqs: Maximum number of briqs to generate
            
        Returns:
            List of briq dictionaries with title and content
        """
        briqs = []
        
        # Group gaps by layer to ensure dependency order
        by_layer = {}
        for gap in gaps:
            by_layer.setdefault(gap.layer, []).append(gap)
        
        briq_count = 0
        for layer in sorted(by_layer.keys()):
            for gap in by_layer[layer]:
                if briq_count >= max_briqs:
                    break
                    
                briq = {
                    'title': f"CREATE_{gap.name.replace('.py', '').upper()}",
                    'content': gap.to_briq_content(),
                    'is_creation': True,  # Flag for instruqtor
                    'layer': gap.layer,
                    'priority': gap.priority,
                }
                briqs.append(briq)
                briq_count += 1
                
        return briqs
        
    def generate_gap_report(self) -> str:
        """Generate a markdown report of all gaps found."""
        gaps = self.find_gaps()
        existing = self.get_existing_files()
        
        lines = [
            "# Qonvergence Analysis Report",
            "",
            f"**Tasq Requirements:** {len(self.required_files)} files",
            f"**Existing Files:** {len(existing)} files",
            f"**Missing Files:** {len(gaps)} files",
            f"**Coverage:** {100 * (1 - len(gaps)/max(len(self.required_files), 1)):.1f}%",
            "",
            "## Missing Files by Layer",
            ""
        ]
        
        by_layer = {}
        for gap in gaps:
            by_layer.setdefault(gap.layer, []).append(gap)
            
        for layer in sorted(by_layer.keys()):
            layer_gaps = by_layer[layer]
            lines.append(f"### Layer {layer} ({len(layer_gaps)} missing)")
            for gap in layer_gaps:
                lines.append(f"- [ ] `{gap.path}` - {gap.description[:60]}...")
            lines.append("")
            
        lines.extend([
            "## Existing Files",
            ""
        ])
        for f in sorted(existing):
            if f.endswith('.py'):
                lines.append(f"- [x] `{f}`")
                
        lines.extend([
            "",
            "---",
            "*Generated by Qonverger v1.0.0*"
        ])
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTION FOR INSPEQTOR
# ═══════════════════════════════════════════════════════════════════════════════

def qonverge(
    tasq_path: Path,
    qodeyard_path: Path,
    max_suggestions: int = 30
) -> Tuple[List[Gap], str]:
    """
    Main integration function - analyze gaps and generate suggestions.
    
    Args:
        tasq_path: Path to original tasq.md
        qodeyard_path: Path to qodeyard directory
        max_suggestions: Maximum gap suggestions to return
        
    Returns:
        Tuple of (list of gaps, formatted suggestions string)
    """
    try:
        with open(tasq_path, 'r', encoding='utf-8') as f:
            tasq_content = f.read()
    except Exception as e:
        return [], f"[Error reading tasq: {e}]"
        
    analyzer = Qonverger(tasq_content, qodeyard_path)
    gaps = analyzer.find_gaps()
    
    if not gaps:
        return [], "## ✅ No Gaps Found\nAll required files from tasq.md have been created."
    
    # Format suggestions for inspeqtor output
    lines = [
        "## 🔴 QONVERGENCE ANALYSIS - MISSING FILES DETECTED",
        "",
        f"**{len(gaps)} files** from the original tasq.md were NOT created in Cycle 1.",
        "The following files MUST be CREATED (not refactored) in the next cycle:",
        ""
    ]
    
    for i, gap in enumerate(gaps[:max_suggestions]):
        lines.append(f"### Gap {i+1}: CREATE `{gap.path}`")
        lines.append(f"- **Layer:** {gap.layer}")
        lines.append(f"- **Priority:** {gap.priority}/10")
        lines.append(f"- **Description:** {gap.description}")
        if gap.dependencies:
            lines.append(f"- **Dependencies:** {', '.join(gap.dependencies)}")
        lines.append("")
    
    if len(gaps) > max_suggestions:
        lines.append(f"*...and {len(gaps) - max_suggestions} more missing files*")
        lines.append("")
    
    lines.extend([
        "---",
        "**CRITICAL:** These are CREATE briqs, not REFACTOR briqs!",
        "The construqtor must generate NEW files for each gap.",
    ])
    
    return gaps, "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI FOR TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python qonverger.py <tasq.md> <qodeyard_path>")
        sys.exit(1)
        
    tasq_path = Path(sys.argv[1])
    qodeyard_path = Path(sys.argv[2])
    
    with open(tasq_path, 'r') as f:
        tasq_content = f.read()
        
    analyzer = Qonverger(tasq_content, qodeyard_path)
    print(analyzer.generate_gap_report())

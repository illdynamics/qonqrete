#!/usr/bin/env python3
"""
LocalTasqLeveler: Zero-Cost Task Enhancement Agent
Part of mindstaQ - Pattern-based task enhancement, NO LLM, NO API COST

Enhances tasq.md with:
- Dependency ordering based on file mentions
- Basic success criteria templates  
- Build order guidance
- Phase structure validation

Only triggers on tasks above a threshold size to avoid over-processing simple tasks.

v1.2.0
"""

import re
import os
import sys
import shutil
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
from datetime import datetime


__version__ = '1.3.1'


# ═══════════════════════════════════════════════════════════════════════════════
# THRESHOLD CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    'min_chars': 100,           # Minimum characters to trigger enhancement
    'min_lines': 5,             # Minimum lines to trigger enhancement
    'min_sections': 2,          # Minimum section headers to trigger enhancement
    'min_bullets': 3,           # Minimum bullet points to trigger enhancement
    'skip_single_file': True,   # Skip if only one file mentioned
}


# ═══════════════════════════════════════════════════════════════════════════════
# FILE PATTERN DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Common file patterns to detect
FILE_PATTERNS = [
    r'`([a-zA-Z0-9_\-\.\/]+\.(py|js|ts|go|rs|java|rb|php|sh|yaml|yml|json|md|txt|toml|cfg|ini|env))`',
    r'([a-zA-Z0-9_]+\.py)',
    r'([a-zA-Z0-9_]+\.js)',
    r'Dockerfile',
    r'docker-compose\.ya?ml',
    r'requirements\.txt',
    r'package\.json',
    r'Makefile',
    r'\.env',
]

# Dependency keywords
DEPENDENCY_KEYWORDS = {
    'imports': ['import', 'from', 'require', 'include'],
    'uses': ['uses', 'depends on', 'requires', 'needs'],
    'creates': ['creates', 'generates', 'outputs', 'writes'],
}

# Build order heuristics
BUILD_ORDER_HINTS = {
    'config': 1,
    'constants': 1,
    'types': 1,
    'models': 2,
    'utils': 2,
    'helpers': 2,
    'services': 3,
    'api': 4,
    'routes': 4,
    'handlers': 4,
    'main': 5,
    'app': 5,
    'server': 5,
    'test': 6,
    'tests': 6,
}


@dataclass
class TasqAnalysis:
    """Analysis results for a tasq."""
    char_count: int = 0
    line_count: int = 0
    section_count: int = 0
    bullet_count: int = 0
    files_mentioned: List[str] = field(default_factory=list)
    has_dockerfile: bool = False
    has_requirements: bool = False
    has_tests: bool = False
    should_enhance: bool = False
    reason: str = ""


class LocalTasqLeveler:
    """
    Zero-cost task enhancement using pattern-based analysis.
    Only enhances tasks above a configurable threshold.
    """
    
    def __init__(self, config: dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
    
    def analyze(self, content: str) -> TasqAnalysis:
        """Analyze tasq content to determine if enhancement is needed."""
        analysis = TasqAnalysis()
        
        # Basic metrics
        analysis.char_count = len(content)
        analysis.line_count = len(content.split('\n'))
        
        # Count sections (markdown headers)
        analysis.section_count = len(re.findall(r'^#{1,6}\s+', content, re.MULTILINE))
        
        # Count bullets
        analysis.bullet_count = len(re.findall(r'^\s*[-*•]\s+', content, re.MULTILINE))
        analysis.bullet_count += len(re.findall(r'^\s*\d+[.)]\s+', content, re.MULTILINE))
        
        # Detect files mentioned
        files = set()
        for pattern in FILE_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    files.add(match[0])
                else:
                    files.add(match)
        
        analysis.files_mentioned = sorted(files)
        analysis.has_dockerfile = bool(re.search(r'dockerfile', content, re.IGNORECASE))
        analysis.has_requirements = bool(re.search(r'requirements\.txt|package\.json|Cargo\.toml', content, re.IGNORECASE))
        analysis.has_tests = bool(re.search(r'\btest|\bspec|\bjest|\bpytest', content, re.IGNORECASE))
        
        # Determine if enhancement is needed
        reasons = []
        
        if analysis.char_count < self.config['min_chars']:
            reasons.append(f"Too short ({analysis.char_count} < {self.config['min_chars']} chars)")
        
        if analysis.line_count < self.config['min_lines']:
            reasons.append(f"Too few lines ({analysis.line_count} < {self.config['min_lines']})")
        
        if analysis.section_count < self.config['min_sections'] and analysis.bullet_count < self.config['min_bullets']:
            reasons.append(f"Not structured enough ({analysis.section_count} sections, {analysis.bullet_count} bullets)")
        
        if self.config['skip_single_file'] and len(analysis.files_mentioned) <= 1:
            reasons.append(f"Single file project")
        
        if reasons:
            analysis.should_enhance = False
            analysis.reason = "; ".join(reasons)
        else:
            analysis.should_enhance = True
            analysis.reason = "Task meets complexity threshold"
        
        return analysis
    
    def enhance(self, content: str, analysis: TasqAnalysis = None) -> Tuple[str, bool]:
        """
        Enhance tasq content with structure and guidance.
        Returns (enhanced_content, was_modified).
        """
        if analysis is None:
            analysis = self.analyze(content)
        
        if not analysis.should_enhance:
            return content, False
        
        enhancements = []
        
        # Add build order guidance if multiple files detected
        if len(analysis.files_mentioned) > 1:
            build_order = self._generate_build_order(analysis.files_mentioned)
            if build_order:
                enhancements.append(build_order)
        
        # Add success criteria template
        success_criteria = self._generate_success_criteria(analysis)
        if success_criteria:
            enhancements.append(success_criteria)
        
        # Add containerization notes if Dockerfile detected
        if analysis.has_dockerfile:
            enhancements.append(self._generate_docker_notes())
        
        if not enhancements:
            return content, False
        
        # Find where to insert (after first header or at top)
        lines = content.split('\n')
        insert_idx = 0
        
        for i, line in enumerate(lines):
            if line.startswith('#'):
                insert_idx = i + 1
                # Skip blank lines after header
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
        
        # Build enhanced content
        enhancement_block = "\n\n---\n\n## 📋 LocalTasqLeveler Enhancements\n\n"
        enhancement_block += "\n\n".join(enhancements)
        enhancement_block += "\n\n---\n\n"
        
        # Insert enhancement
        enhanced_lines = lines[:insert_idx] + [enhancement_block] + lines[insert_idx:]
        enhanced_content = '\n'.join(enhanced_lines)
        
        return enhanced_content, True
    
    def _generate_build_order(self, files: List[str]) -> str:
        """Generate build order guidance based on file names."""
        if not files:
            return ""
        
        # Score files by build order
        scored = []
        for f in files:
            name = Path(f).stem.lower()
            score = 5  # Default middle priority
            for keyword, priority in BUILD_ORDER_HINTS.items():
                if keyword in name:
                    score = priority
                    break
            scored.append((score, f))
        
        scored.sort(key=lambda x: x[0])
        
        lines = ["### 🔧 Suggested Build Order\n"]
        lines.append("Build files in this order to minimize dependency issues:\n")
        
        for i, (score, f) in enumerate(scored, 1):
            lines.append(f"{i}. `{f}`")
        
        return "\n".join(lines)
    
    def _generate_success_criteria(self, analysis: TasqAnalysis) -> str:
        """Generate basic success criteria template."""
        lines = ["### ✅ Success Criteria\n"]
        lines.append("Before marking this task complete, verify:\n")
        
        # Python-specific
        if any(f.endswith('.py') for f in analysis.files_mentioned):
            lines.append("- [ ] All Python files pass `python -m py_compile <file>`")
            lines.append("- [ ] No import errors when running main module")
        
        # JS/TS-specific
        if any(f.endswith(('.js', '.ts')) for f in analysis.files_mentioned):
            lines.append("- [ ] No syntax errors (`node --check` or `tsc --noEmit`)")
        
        # Docker-specific
        if analysis.has_dockerfile:
            lines.append("- [ ] Dockerfile builds successfully")
            lines.append("- [ ] Container starts without errors")
        
        # Tests
        if analysis.has_tests:
            lines.append("- [ ] All tests pass")
        
        # Generic
        lines.append("- [ ] Core functionality works as described")
        
        return "\n".join(lines)
    
    def _generate_docker_notes(self) -> str:
        """Generate Docker-related guidance."""
        return """### 🐳 Container Notes

When building the Dockerfile:
1. Use multi-stage builds if possible
2. Install dependencies before copying source
3. Use `.dockerignore` to exclude unnecessary files
4. Set a non-root user for security"""
    
    def process_file(self, input_path: str, output_path: str = None, backup: bool = True) -> bool:
        """
        Process a tasq file and optionally enhance it.
        
        Args:
            input_path: Path to tasq.md
            output_path: Path to write enhanced tasq (defaults to input_path)
            backup: Whether to backup original file
        
        Returns:
            True if file was enhanced, False otherwise
        """
        input_path = Path(input_path)
        output_path = Path(output_path) if output_path else input_path
        
        if not input_path.exists():
            print(f"[LocalTasqLeveler] File not found: {input_path}", file=sys.stderr)
            return False
        
        # Read content
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Analyze
        analysis = self.analyze(content)
        
        print(f"[LocalTasqLeveler] Analysis:", file=sys.stderr)
        print(f"  Chars: {analysis.char_count}, Lines: {analysis.line_count}", file=sys.stderr)
        print(f"  Sections: {analysis.section_count}, Bullets: {analysis.bullet_count}", file=sys.stderr)
        print(f"  Files mentioned: {len(analysis.files_mentioned)}", file=sys.stderr)
        print(f"  Should enhance: {analysis.should_enhance} ({analysis.reason})", file=sys.stderr)
        
        if not analysis.should_enhance:
            print(f"[LocalTasqLeveler] Skipping enhancement: {analysis.reason}", file=sys.stderr)
            return False
        
        # Enhance
        enhanced, was_modified = self.enhance(content, analysis)
        
        if not was_modified:
            print(f"[LocalTasqLeveler] No enhancements needed", file=sys.stderr)
            return False
        
        # Backup original
        if backup and input_path == output_path:
            backup_path = input_path.with_suffix('.md.original')
            shutil.copy2(input_path, backup_path)
            print(f"[LocalTasqLeveler] Backed up to: {backup_path}", file=sys.stderr)
        
        # Write enhanced
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(enhanced)
        
        print(f"[LocalTasqLeveler] Enhanced tasq written to: {output_path}", file=sys.stderr)
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / Agent Interface
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI entry point for LocalTasqLeveler."""
    if len(sys.argv) < 2:
        print("Usage: local_tasqleveler.py <input_tasq.md> [output_tasq.md]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path
    
    print(f"--- LocalTasqLeveler v{__version__} ---", flush=True)
    
    # Load config if available
    config = {}
    try:
        import yaml
        config_path = Path.cwd() / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
                config = cfg.get('mindstaq', {}).get('tasqleveler', {})
    except:
        pass
    
    leveler = LocalTasqLeveler(config)
    success = leveler.process_file(input_path, output_path)
    
    if success:
        print(f"[LocalTasqLeveler] Enhancement complete!", flush=True)
    else:
        print(f"[LocalTasqLeveler] No enhancement needed (task below threshold)", flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
LocalInstruQtor: Zero-Cost Task Decomposition Agent
Part of mindstaQ - Pure symbolic task splitting, NO LLM, NO API COST

Splits tasks into BRIQs based on:
- Paragraphs (double newlines)
- Bullet points (- * •)
- Numbered lists (1. 2. 3.)
- Sections (# ## ### headers)
- Logical conjunctions (and, then, also, as well as)
- Technical patterns (containerize, deploy, create X and Y)

v1.1.2
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple
from enum import Enum


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# BRIQ SENSITIVITY RANGES (Matching instruqtor.py)
# ═══════════════════════════════════════════════════════════════════════════════

BRIQ_RANGES = {
    # v2.1.5: INVERTED SCALE - Higher number = More briqs!
    0: (1, 1, 1),        # Monolithic: exactly 1 briq
    1: (2, 3, 2),        # Very Broad: 2-3 briqs
    2: (3, 5, 4),        # Broad: 3-5 briqs
    3: (5, 8, 6),        # Feature-level: 5-8 briqs
    4: (8, 12, 10),      # Component-level: 8-12 briqs
    5: (10, 15, 12),     # Balanced: 10-15 briqs (RECOMMENDED DEFAULT)
    6: (15, 20, 18),     # Standard: 15-20 briqs
    7: (20, 30, 25),     # High Granularity: 20-30 briqs
    8: (30, 40, 35),     # Very High: 30-40 briqs
    9: (40, 60, 50),     # Atomic: 40-60 briqs
    # v2.1.5: Extended range for mega-projects
    10: (50, 75, 60),    # Ultra: 50-75 briqs
    11: (60, 90, 75),    # Mega: 60-90 briqs
    12: (75, 110, 90),   # Hyper: 75-110 briqs
    13: (90, 130, 110),  # Extreme: 90-130 briqs
    14: (110, 160, 135), # Maximum: 110-160 briqs
    15: (130, 200, 165), # Insane: 130-200 briqs
    16: (160, 250, 200), # QONQRETE MAX: 160-250 briqs
}


# ═══════════════════════════════════════════════════════════════════════════════
# SPLIT PATTERNS - Keywords that indicate logical task boundaries
# ═══════════════════════════════════════════════════════════════════════════════

# Conjunctions that split compound tasks
SPLIT_CONJUNCTIONS: Set[str] = {
    ' and ', ' then ', ' also ', ' plus ', ' as well as ',
    ' additionally ', ' furthermore ', ' moreover ', ' besides ',
    ' along with ', ' together with ', ' in addition to ',
}

# Action verbs that often start new tasks
ACTION_VERBS: Set[str] = {
    'create', 'build', 'implement', 'add', 'setup', 'configure', 'deploy',
    'write', 'develop', 'design', 'make', 'generate', 'install', 'initialize',
    'update', 'modify', 'fix', 'refactor', 'optimize', 'test', 'validate',
    'integrate', 'connect', 'migrate', 'containerize', 'dockerize',
}

# Technical compound patterns: "X and Y" where X and Y are separate tasks
COMPOUND_PATTERNS = [
    # Container patterns
    (r'(?:create|build|write)\s+(?:the\s+)?(\w+)\s+(?:and|with)\s+(?:a\s+)?(?:docker(?:file)?|container)',
     lambda m: [f"Create {m.group(1)}", "Create Dockerfile"]),
    
    # Frontend + Backend
    (r'(?:create|build)\s+(?:a\s+)?(?:full[- ]?stack|complete)\s+(\w+)',
     lambda m: [f"Create {m.group(1)} backend", f"Create {m.group(1)} frontend"]),
    
    # API + Database
    (r'(?:create|build)\s+(?:an?\s+)?(\w+)\s+(?:api|service)\s+with\s+(\w+)\s+database',
     lambda m: [f"Create {m.group(1)} API", f"Setup {m.group(2)} database"]),
    
    # Server + Client
    (r'(?:create|build)\s+(?:a\s+)?server\s+and\s+client',
     lambda m: ["Create server", "Create client"]),
    
    # Tests pattern
    (r'(?:create|write|add)\s+(?:unit\s+)?tests?\s+(?:and|for)\s+(\w+)',
     lambda m: [f"Create tests for {m.group(1)}"]),
]

# Section header patterns
HEADER_PATTERNS = [
    r'^#{1,6}\s+(.+)$',           # Markdown headers: # ## ### etc.
    r'^([A-Z][^.!?\n]{3,50}):$',  # Title with colon: "Authentication:"
    r'^(\d+\.)\s+(.+)$',          # Numbered: "1. First task"
    r'^([A-Z][A-Z0-9\s_-]{2,30})$',  # ALL CAPS titles
]

# Bullet patterns
BULLET_PATTERNS = [
    r'^\s*[-*•]\s+(.+)$',         # Dash, asterisk, bullet
    r'^\s*\d+[.)]\s+(.+)$',       # Numbered lists
    r'^\s*[a-z][.)]\s+(.+)$',     # Lettered lists
]


@dataclass
class Briq:
    """A single task unit."""
    title: str
    content: str
    source: str = "paragraph"  # paragraph, bullet, section, logical, compound


@dataclass
class SplitResult:
    """Result of task splitting."""
    briqs: List[Briq] = field(default_factory=list)
    sensitivity: int = 7
    min_briqs: int = 3
    max_briqs: int = 5
    target_briqs: int = 4


class LocalInstruQtor:
    """
    Zero-cost task decomposition using pattern-based splitting.
    No LLM calls, just pure symbolic text analysis.
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        instruqtor_cfg = self.config.get('instruqtor', {})
        self.sensitivity = instruqtor_cfg.get('default_sensitivity', 5)  # v2.1.3: Default 5 (Balanced)
        self.min_title_words = instruqtor_cfg.get('min_title_words', 2)
        self.max_title_words = instruqtor_cfg.get('max_title_words', 8)
    
    def split(self, task_content: str, sensitivity: int = None) -> SplitResult:
        """
        Split a task into BRIQs based on sensitivity level.
        
        Args:
            task_content: The task text to split
            sensitivity: 0-16 (0=monolithic/1 briq, 9=atomic/40-60, 16=max/160-250)
        
        Returns:
            SplitResult with list of Briqs
        """
        if sensitivity is None:
            sensitivity = self.sensitivity
        
        # v2.1.5: Clamp sensitivity to extended range 0-16
        sensitivity = max(0, min(16, sensitivity))
        min_briqs, max_briqs, target_briqs = BRIQ_RANGES.get(sensitivity, BRIQ_RANGES[5])  # v2.1.5: Default 5 (Balanced)
        
        result = SplitResult(
            sensitivity=sensitivity,
            min_briqs=min_briqs,
            max_briqs=max_briqs,
            target_briqs=target_briqs
        )
        
        # Clean input
        task_content = self._clean_input(task_content)
        
        if not task_content.strip():
            result.briqs = [Briq(title="Empty_Task", content="No content provided")]
            return result
        
        # ═══════════════════════════════════════════════════════════════════════════
        # v2.1.5 FIX: Short-circuit for LOW sensitivity (0-1) = MONOLITHIC
        # INVERTED SCALE: 0 = monolithic, 16 = maximum briqs
        # ═══════════════════════════════════════════════════════════════════════════
        if sensitivity <= 1:
            # Extract a good title from the first meaningful line
            title = self._generate_title(task_content)
            
            # For sens=0: exactly 1 briq with FULL content
            if sensitivity == 0:
                result.briqs = [Briq(
                    title=title,
                    content=task_content,
                    source="monolithic"
                )]
                return result
            
            # For sens=1: 2-3 briqs, split by major sections only (# headers)
            major_sections = self._split_by_major_sections_only(task_content)
            if len(major_sections) >= 2:
                result.briqs = major_sections[:max_briqs]
                return result
            else:
                result.briqs = [Briq(
                    title=title,
                    content=task_content,
                    source="broad"
                )]
                return result
        
        # Step 1: Extract all potential briqs using multiple strategies
        all_briqs: List[Briq] = []
        
        # Strategy 1: Section-based splitting (headers)
        section_briqs = self._split_by_sections(task_content)
        all_briqs.extend(section_briqs)
        
        # Strategy 2: Bullet/list-based splitting
        bullet_briqs = self._split_by_bullets(task_content)
        all_briqs.extend(bullet_briqs)
        
        # Strategy 3: Paragraph-based splitting
        para_briqs = self._split_by_paragraphs(task_content)
        all_briqs.extend(para_briqs)
        
        # Strategy 4: Logical conjunction splitting
        logical_briqs = self._split_by_logic(task_content)
        all_briqs.extend(logical_briqs)
        
        # Strategy 5: Compound pattern splitting
        compound_briqs = self._split_by_compounds(task_content)
        all_briqs.extend(compound_briqs)
        
        # Remove duplicates and empty briqs
        all_briqs = self._deduplicate_briqs(all_briqs)
        
        # Adjust to sensitivity range
        if len(all_briqs) == 0:
            # Fallback: single briq with entire content
            fallback_title = self._generate_title(task_content)
            # v1.7.8: Don't create garbage fallback briqs
            if not self._is_garbage_title(fallback_title):
                all_briqs = [Briq(
                    title=fallback_title,
                    content=task_content,
                    source="fallback"
                )]
            else:
                # Content is pure garbage, return empty result
                all_briqs = []
        
        # Apply sensitivity: merge or split as needed
        final_briqs = self._apply_sensitivity(all_briqs, min_briqs, max_briqs, target_briqs, task_content)
        
        result.briqs = final_briqs
        return result
    
    def _split_by_major_sections_only(self, content: str) -> List[Briq]:
        """Split by top-level # headers only (for sens=8)."""
        briqs = []
        lines = content.split('\n')
        
        current_section = []
        current_title = None
        
        for line in lines:
            # Only match top-level headers (# not ##)
            match = re.match(r'^#\s+(.+)$', line)
            if match and not line.startswith('##'):
                # Save previous section
                if current_section and current_title:
                    briqs.append(Briq(
                        title=self._clean_title(current_title),
                        content='\n'.join(current_section).strip(),
                        source="major_section"
                    ))
                current_title = match.group(1).strip()
                current_section = [line]
            else:
                current_section.append(line)
        
        # Save last section
        if current_section:
            if current_title:
                briqs.append(Briq(
                    title=self._clean_title(current_title),
                    content='\n'.join(current_section).strip(),
                    source="major_section"
                ))
            elif not briqs:
                # No headers found, return whole content
                briqs.append(Briq(
                    title=self._generate_title(content),
                    content=content,
                    source="no_sections"
                ))
        
        return briqs
    
    def _clean_input(self, text: str) -> str:
        """Clean input text."""
        text = text.replace('\u200b', '').replace('\ufeff', '')
        text = text.replace('\xa0', ' ')
        text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
        return text.strip()
    
    def _split_by_sections(self, text: str) -> List[Briq]:
        """Split by markdown headers and section titles."""
        briqs = []
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            is_header = False
            header_text = None
            
            # Check for markdown headers
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                is_header = True
                header_text = header_match.group(2).strip()
            
            # Check for ALL CAPS titles
            if not is_header and re.match(r'^[A-Z][A-Z0-9\s_-]{2,40}$', line.strip()):
                is_header = True
                header_text = line.strip()
            
            # Check for "Title:" format
            if not is_header:
                colon_match = re.match(r'^([A-Z][^.!?\n]{3,50}):$', line.strip())
                if colon_match:
                    is_header = True
                    header_text = colon_match.group(1).strip()
            
            if is_header:
                # Save previous section
                if current_section and current_content:
                    content = '\n'.join(current_content).strip()
                    if content:
                        briqs.append(Briq(
                            title=current_section,
                            content=content,
                            source="section"
                        ))
                current_section = header_text
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_section and current_content:
            content = '\n'.join(current_content).strip()
            if content:
                briqs.append(Briq(
                    title=current_section,
                    content=content,
                    source="section"
                ))
        
        return briqs
    
    def _split_by_bullets(self, text: str) -> List[Briq]:
        """Split by bullet points and numbered lists.
        
        v1.6.3 FIX: Require MEANINGFUL content, not just keywords.
        v1.7.8 FIX: Actually check for action verbs as documented.
        A bullet point must have:
        - At least 30 chars (a sentence, not a word)
        - OR contain an action verb (indicating an actual task)
        - OR contain a file path (indicating a specific file to work on)
        """
        briqs = []
        lines = text.split('\n')
        
        # Keywords that are NOT tasks by themselves
        non_task_keywords = {
            'exploit', 'persistence', 'exfiltration', 'post_exploit',
            'localhost', 'recon', 'scan', 'attack', 'defense',
            'true', 'false', 'yes', 'no', 'none', 'null',
        }
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check bullet patterns
            for pattern in BULLET_PATTERNS:
                match = re.match(pattern, line)
                if match:
                    content = match.group(1) if match.lastindex else line
                    content = content.strip()
                    
                    # v1.6.3: Much stricter content validation
                    # Skip if content is just a keyword or too short
                    content_lower = content.lower().strip('`"\'[]')
                    
                    # Skip single keywords that aren't tasks
                    if content_lower in non_task_keywords:
                        break
                    
                    # v1.7.8 FIX: Check if starts with action verb
                    words = content.split()
                    has_action_verb = words and words[0].lower() in ACTION_VERBS
                    
                    # Skip very short content UNLESS it has an action verb
                    word_count = len(words)
                    if word_count < 3 and len(content) < 30 and not has_action_verb:
                        # Exception: file paths are okay
                        if not ('/' in content or content.endswith('.py') or 
                                content.endswith('.sh') or content.endswith('.yaml')):
                            break
                    
                    # Skip checkbox items without actual content
                    if re.match(r'^\[[ x]\]\s*\w+$', content):
                        break
                    
                    # Must have at least 10 chars to be meaningful (reduced from 15)
                    # v1.7.8: Reduced threshold since action verbs indicate intent
                    if len(content) < 10:
                        break
                    
                    title = self._generate_title(content)
                    briqs.append(Briq(
                        title=title,
                        content=content,
                        source="bullet"
                    ))
                    break
        
        return briqs
    
    def _split_by_paragraphs(self, text: str) -> List[Briq]:
        """Split by double newlines (paragraphs).
        
        v1.7.8 FIX: Filter paragraphs that are just lists of garbage keywords.
        """
        briqs = []
        
        # Keywords that are NOT tasks by themselves
        non_task_keywords = {
            'exploit', 'persistence', 'exfiltration', 'post_exploit',
            'localhost', 'recon', 'scan', 'attack', 'defense',
            'true', 'false', 'yes', 'no', 'none', 'null',
        }
        
        # Split by double newlines
        paragraphs = re.split(r'\n\s*\n', text)
        
        for para in paragraphs:
            para = para.strip()
            if len(para) < 20:  # Skip very short paragraphs
                continue
            
            # Skip if it's just a header
            if re.match(r'^#{1,6}\s+.+$', para) or re.match(r'^[A-Z][A-Z\s]{2,30}$', para):
                continue
            
            # v1.7.8: Skip if paragraph is just bullet points of garbage keywords
            lines = [l.strip().lstrip('-*•').strip().lower() for l in para.split('\n') if l.strip()]
            if lines and all(line in non_task_keywords for line in lines if line):
                continue
            
            # v1.7.8: Skip if the "meaningful" words are all garbage
            words = re.findall(r'\b(\w{3,})\b', para.lower())
            words = [w for w in words if w not in {'the', 'and', 'for', 'that', 'this', 'with'}]
            if words and all(w in non_task_keywords for w in words):
                continue
            
            title = self._generate_title(para)
            briqs.append(Briq(
                title=title,
                content=para,
                source="paragraph"
            ))
        
        return briqs
    
    def _split_by_logic(self, text: str) -> List[Briq]:
        """Split by logical conjunctions like 'and', 'then', 'also'."""
        briqs = []
        
        # Find sentences with conjunctions
        sentences = re.split(r'[.!?]\s+', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            
            # Check for split conjunctions
            for conj in SPLIT_CONJUNCTIONS:
                if conj in sentence.lower():
                    parts = re.split(re.escape(conj), sentence, flags=re.IGNORECASE)
                    for part in parts:
                        part = part.strip()
                        if len(part) > 10:
                            # Check if part starts with action verb
                            words = part.lower().split()
                            if words and words[0] in ACTION_VERBS:
                                title = self._generate_title(part)
                                briqs.append(Briq(
                                    title=title,
                                    content=part,
                                    source="logical"
                                ))
                    break
        
        return briqs
    
    def _split_by_compounds(self, text: str) -> List[Briq]:
        """Split compound technical patterns."""
        briqs = []
        
        text_lower = text.lower()
        
        for pattern, splitter in COMPOUND_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                try:
                    titles = splitter(match)
                    for title in titles:
                        briqs.append(Briq(
                            title=self._clean_title(title),
                            content=match.group(0),
                            source="compound"
                        ))
                except:
                    continue
        
        return briqs
    
    def _generate_title(self, content: str) -> str:
        """Generate a distinctive title from content.
        
        Uses keyword extraction to create unique titles even when
        content starts with similar phrases. Looks at both head and
        tail of content for distinctive terms.
        """
        # Remove markdown formatting
        content = re.sub(r'[#*_`\[\]]', '', content)
        
        if not content.strip():
            return "Task"
        
        # Get first sentence
        first_line = content.split('\n')[0].strip()
        first_sentence = re.split(r'[.!?]', first_line)[0].strip()
        
        words = first_sentence.split()
        
        # Skip common filler words
        skip_words = {'a', 'an', 'the', 'that', 'which', 'this', 'with', 
                      'for', 'and', 'or', 'on', 'in', 'to', 'is', 'are',
                      'be', 'it', 'of', 'as', 'by', 'at', 'from', 'all',
                      'should', 'simple', 'basic'}
        
        # Extract action verb if present at start
        action_verb = None
        for i, word in enumerate(words[:3]):
            if word.lower() in ACTION_VERBS:
                action_verb = word.lower()
                break
        
        # Get ALL meaningful words, not just first few
        key_words = [w for w in words if w.lower() not in skip_words and len(w) > 2]
        
        # Build title with: Action + first key word + LAST key words (for distinctiveness)
        title_words = []
        
        if action_verb:
            title_words.append(action_verb.capitalize())
            key_words = [w for w in key_words if w.lower() != action_verb]
        
        if len(key_words) >= 4:
            # Include first 2 + last 2 key words for distinctiveness
            title_words.extend(key_words[:2])
            title_words.extend(key_words[-2:])
        elif len(key_words) >= 2:
            # Include first + last
            title_words.append(key_words[0])
            if key_words[-1] != key_words[0]:
                title_words.append(key_words[-1])
        elif key_words:
            title_words.extend(key_words)
        
        # Deduplicate while preserving order
        seen = set()
        title_words = [w for w in title_words if not (w.lower() in seen or seen.add(w.lower()))]
        
        # If still generic, look for distinctive terms deeper in content
        if len(title_words) < 3 and len(content) > 80:
            later_content = content[40:200]
            later_words = re.findall(r'\b([A-Za-z]{4,})\b', later_content)
            distinctive = [w for w in later_words if w.lower() not in skip_words and w.lower() not in seen][:2]
            title_words.extend(distinctive)
        
        title = ' '.join(title_words[:self.max_title_words])
        return self._clean_title(title)
    
    def _clean_title(self, title: str) -> str:
        """Clean and format title for filename compatibility."""
        # Remove special characters
        title = re.sub(r'[^\w\s-]', '', title)
        # Replace spaces with underscores
        title = re.sub(r'\s+', '_', title.strip())
        # Remove multiple underscores
        title = re.sub(r'_+', '_', title)
        # Capitalize words
        title = '_'.join(word.capitalize() for word in title.split('_') if word)
        # Limit length
        return title[:60] if title else "Task"
    
    def _deduplicate_briqs(self, briqs: List[Briq]) -> List[Briq]:
        """Remove duplicate briqs based on content similarity.
        
        Strategy: Prefer more specific (shorter) briqs over generic (longer) ones.
        When bullet/section items are subsets of a larger paragraph, keep the bullets/sections.
        
        v1.7.8 FIX: Also filter out briqs with garbage keyword titles.
        """
        if not briqs:
            return []
        
        # Sort by source priority (bullet/section > logical > compound > paragraph)
        # and by content length (shorter = more specific)
        source_priority = {'bullet': 0, 'section': 1, 'logical': 2, 'compound': 3, 'paragraph': 4, 'merged': 5, 'fallback': 6, 'sentence': 2}
        
        sorted_briqs = sorted(briqs, key=lambda b: (source_priority.get(b.source, 5), len(b.content)))
        
        unique_briqs = []
        seen_content = set()
        
        for briq in sorted_briqs:
            # v1.7.8: Skip briqs with garbage titles
            if self._is_garbage_title(briq.title):
                continue
            
            # Normalize content for comparison
            normalized = re.sub(r'\s+', ' ', briq.content.lower().strip())
            
            # Skip empty or very short content
            if len(normalized) < 5:
                continue
            
            # Check if this briq's content is already substantially covered
            is_duplicate = False
            for seen in seen_content:
                # Only mark as duplicate if the EXACT content was already added
                if normalized == seen:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_content.add(normalized)
                unique_briqs.append(briq)
        
        return unique_briqs
    
    def _apply_sensitivity(
        self,
        briqs: List[Briq],
        min_briqs: int,
        max_briqs: int,
        target_briqs: int,
        original_content: str
    ) -> List[Briq]:
        """Adjust briq count to match sensitivity range.
        
        v1.7.8 FIX: Don't create garbage fallback briqs.
        """
        current_count = len(briqs)
        
        # If within range, return as-is
        if min_briqs <= current_count <= max_briqs:
            return briqs
        
        # Too many briqs - merge them
        if current_count > max_briqs:
            return self._merge_briqs(briqs, target_briqs)
        
        # Too few briqs - try to split more or create from content
        if current_count < min_briqs:
            # Try deeper splitting
            more_briqs = self._split_deeper(briqs, original_content, min_briqs)
            if len(more_briqs) >= min_briqs:
                return more_briqs[:max_briqs]
            
            # Still not enough - just return what we have
            if briqs:
                return briqs
            
            # v1.7.8: Only create fallback if title is not garbage
            fallback_title = self._generate_title(original_content)
            if not self._is_garbage_title(fallback_title):
                return [Briq(
                    title=fallback_title,
                    content=original_content,
                    source="fallback"
                )]
            else:
                # Content is garbage, return empty
                return []
        
        return briqs
    
    def _is_garbage_title(self, title: str) -> bool:
        """Check if a title is pure garbage keywords.
        
        v1.7.8: Detects both single garbage words AND combinations of garbage words.
        """
        garbage_titles = {
            'true', 'false', 'yes', 'no', 'none', 'null', 'task',
            'localhost', 'recon', 'scan', 'attack', 'defense',
            'exploit', 'persistence', 'exfiltration', 'post_exploit',
        }
        
        # Split title into words
        title_words = [w.lower() for w in title.replace('_', ' ').split() if w]
        
        if not title_words:
            return True  # Empty title is garbage
        
        # If ALL words are garbage, the title is garbage
        if all(w in garbage_titles for w in title_words):
            return True
        
        # If single word and it's garbage
        if len(title_words) == 1 and title_words[0] in garbage_titles:
            return True
        
        return False
    
    def _merge_briqs(self, briqs: List[Briq], target_count: int) -> List[Briq]:
        """Merge briqs to reduce count."""
        if len(briqs) <= target_count:
            return briqs
        
        import math
        merge_factor = math.ceil(len(briqs) / target_count)
        merged = []
        
        for i in range(0, len(briqs), merge_factor):
            chunk = briqs[i:i + merge_factor]
            if len(chunk) == 1:
                merged.append(chunk[0])
            else:
                # Combine titles and content
                combined_title = "_And_".join([b.title[:20] for b in chunk[:3]])
                combined_content = "\n\n---\n\n".join([
                    f"## {b.title}\n{b.content}" for b in chunk
                ])
                merged.append(Briq(
                    title=combined_title[:60],
                    content=combined_content,
                    source="merged"
                ))
        
        return merged[:target_count]
    
    def _split_deeper(
        self,
        existing_briqs: List[Briq],
        original_content: str,
        target_min: int
    ) -> List[Briq]:
        """Try to split content more aggressively."""
        new_briqs = list(existing_briqs)
        
        # Try splitting each sentence as a task
        sentences = re.split(r'[.!?]\s+', original_content)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            
            # Check if this sentence starts with an action verb
            words = sentence.lower().split()
            if words and words[0] in ACTION_VERBS:
                title = self._generate_title(sentence)
                briq = Briq(title=title, content=sentence, source="sentence")
                
                # Check if not already covered
                is_new = True
                for existing in new_briqs:
                    if sentence.lower() in existing.content.lower():
                        is_new = False
                        break
                
                if is_new:
                    new_briqs.append(briq)
            
            if len(new_briqs) >= target_min:
                break
        
        return self._deduplicate_briqs(new_briqs)
    
    def explain(self, task_content: str, sensitivity: int = None) -> str:
        """Return human-readable split analysis."""
        result = self.split(task_content, sensitivity)
        
        output = [
            "LocalInstruQtor Analysis",
            "═" * 50,
            f"Sensitivity: {result.sensitivity}",
            f"Target Range: {result.min_briqs}-{result.max_briqs} (target: {result.target_briqs})",
            f"Generated: {len(result.briqs)} BRIQs",
            "═" * 50,
        ]
        
        for i, briq in enumerate(result.briqs, 1):
            output.append(f"\n[BRIQ {i}] {briq.title} ({briq.source})")
            output.append(f"  Content: {briq.content[:80]}...")
        
        return "\n".join(output)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='LocalInstruQtor - Zero-Cost Task Splitter')
    parser.add_argument('--text', '-t', type=str, help='Task text to split')
    parser.add_argument('--file', '-f', type=str, help='File containing task')
    parser.add_argument('--sensitivity', '-s', type=int, default=5, help='Sensitivity level (0-16). Higher=More briqs')
    parser.add_argument('--explain', '-e', action='store_true', help='Show detailed analysis')
    args = parser.parse_args()
    
    text = None
    if args.text:
        text = args.text
    elif args.file:
        with open(args.file, 'r') as f:
            text = f.read()
    else:
        # Read from stdin
        text = sys.stdin.read()
    
    if not text:
        print("No input provided")
        sys.exit(1)
    
    instruqtor = LocalInstruQtor()
    
    if args.explain:
        print(instruqtor.explain(text, args.sensitivity))
    else:
        result = instruqtor.split(text, args.sensitivity)
        print(f"Generated {len(result.briqs)} BRIQs:")
        for i, briq in enumerate(result.briqs, 1):
            print(f"  [{i}] {briq.title}")

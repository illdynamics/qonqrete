"""
Placeholder adapters for the other providers named in the provider manifest
(config/providers.yaml). Wire one of these up the exact same way
CodeSeeqAdapter is wired in adapters/parameters.py: build a CLI command
pointed at spec.workdir, run it, instruct it in the prompt to write JSON to
spec.output_file, then read that file. Left unimplemented on purpose --
one real, tested adapter beats five guessed-at ones.
"""
from __future__ import annotations

from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities


class _StubAdapter(AgentAdapter):
    def capabilities(self) -> Capabilities:
        return Capabilities()

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        raise NotImplementedError(
            f"The '{self.name}' adapter is a stub -- see adapters/stubs.py "
            f"and adapters/parameters.py for the pattern to follow."
        )


class JaminiAdapter(_StubAdapter):
    name = "jamini"


class JeanClaudeAdapter(_StubAdapter):
    name = "jeanclaude"


class CodexAdapter(_StubAdapter):
    name = "codex"


class GeminiCliAdapter(_StubAdapter):
    name = "gemini-cli"


class ClaudeCodeAdapter(_StubAdapter):
    name = "claude-code"

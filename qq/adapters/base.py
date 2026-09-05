"""
Provider adapter interface.

Every coding-agent backend (CodeSeeq, Jamini, JeanClaude, raw Codex, Gemini
CLI, Claude Code, ...) gets normalized behind this one interface. QonQrete
v1 never had this -- its CodeSeeq support and its direct/hybrid/heredoc
transport machinery ended up fighting each other instead of composing,
because there was no single seam between "what an agent needs to do" and
"how a specific CLI happens to be invoked". This is that seam.
"""
from __future__ import annotations

import abc
import dataclasses
from typing import Optional, Callable


@dataclasses.dataclass
class Capabilities:
    supports_sessions: bool = False         # multi-turn within one live process
    supports_interactive_tui: bool = False  # a real human-in-the-loop TUI exists
    supports_exec_mode: bool = True         # scriptable one-shot run
    supports_tools: bool = True             # agent can read/write files itself
    supports_thinking_mode: bool = False
    requires_host_mode: bool = False
    safe_in_container: bool = True


@dataclasses.dataclass
class AgentCallSpec:
    """Everything one agent invocation needs. The adapter decides how to
    turn this into an actual subprocess command for its specific CLI.

    output_file may be an absolute path (e.g. under run_root for receipts)
    or a relative filename (legacy, resolved against workdir). New code
    MUST provide absolute paths under run_root for all agent receipts.
    """
    role: str                       # "qlarifier" | "instruqtor" | "construqtor" | "inspeqtor"
    model: str
    prompt: str
    workdir: str
    output_file: str                # Absolute path (preferred) or relative filename; agent writes JSON here
    thinking: bool = False
    reasoning_effort: str = ""      # low | high | max | "" (empty = default; "minimal" accepted for compat)
    temperature: Optional[float] = None  # 0.0-2.0, non-thinking models only
    top_p: Optional[float] = None        # 0.0-1.0, non-thinking models only
    sandbox: str = "workspace-write"     # Write access to workspace; most-restrictive safe default
    approval: str = "never"              # untrusted | on-failure | on-request | never
    timeout_seconds: int = 1800
    extra_env: Optional[dict] = None
    cd: str = ""                  # --cd directory to pass to the agent CLI
    repo_root: str = ""           # repo root for context
    workspace_root: str = ""       # the real project folder (must be cwd)
    run_root: str = ""             # QonQrete metadata only (never cwd)
    is_metadata_call: bool = False  # if True, agent writes JSON/status artifact to run_root (but still uses workspace_root as cwd)
    artifact_dir: str = ""          # where to write call artifacts (prompt.md, stdout.txt, etc.)
    call_id: str = ""               # unique call identifier
    # Live output streaming
    stream_output: bool = False
    stream_mode: str = "prefixed"   # prefixed | raw
    stream_indicator: str = "stream"  # stream | spinner | none — what appears after role prefix
    stream_stderr: bool = True
    output_sink: Optional[Callable] = None  # callable(chunk: dict) for live output


@dataclasses.dataclass
class AgentCallResult:
    spec: AgentCallSpec
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    output_path_exists: bool
    raw_output_text: Optional[str] = None   # contents of output_file, if the agent wrote it


class AgentAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    @abc.abstractmethod
    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        """Run one agent invocation to completion and return the result.

        Implementations are responsible for actually producing
        spec.output_file — by instructing the model, in the prompt, to
        write it there itself. These are real agentic coding CLIs with
        file read/write tools, not bare chat-completion endpoints, so
        this is the natural and most robust way to get structured output
        back: no stdout-scraping, no hoping the model's prose happens to
        contain valid JSON somewhere in the middle.

        If spec.output_file is an absolute path, the adapter should write
        the prompt to instruct the agent to write to that exact path.
        If it's a relative path, it's resolved against spec.workdir (legacy).
        """
        ...

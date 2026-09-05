from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities
from .codeseeq import CodeSeeqAdapter, ChatGptAdapter
from .mock import MockAdapter
from .stubs import (
    ClaudeCodeAdapter,
    CodexAdapter,
    GeminiCliAdapter,
    JaminiAdapter,
    JeanClaudeAdapter,
)

_REGISTRY = {
    "codeseeq": CodeSeeqAdapter,
    "chatgpt": ChatGptAdapter,   # native ChatGPT account sign-in (codeseeq login)
    "mock": MockAdapter,
    "jamini": JaminiAdapter,
    "jeanclaude": JeanClaudeAdapter,
    "codex": CodexAdapter,
    "gemini-cli": GeminiCliAdapter,
    "claude-code": ClaudeCodeAdapter,
}

# Kwargs known to each adapter class — unknown kwargs are silently dropped
# so CLI callers can pass codeseeq-specific options even when using --dry-run.
_ADAPTER_KWARGS = {
    CodeSeeqAdapter: {"codeseeq_path", "runtime_mode", "bridge_mode", "no_repo"},
    ChatGptAdapter: {"codeseeq_path", "runtime_mode", "bridge_mode", "no_repo"},
    MockAdapter: set(),
}


def get_adapter(name: str, **kwargs) -> AgentAdapter:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown provider '{name}'. Known: {sorted(_REGISTRY)}")
    allowed = _ADAPTER_KWARGS.get(cls, set())
    # Filter kwargs to only what this adapter accepts
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    return cls(**filtered)


__all__ = [
    "AgentAdapter", "AgentCallResult", "AgentCallSpec", "Capabilities",
    "CodeSeeqAdapter", "ChatGptAdapter", "MockAdapter", "get_adapter",
]

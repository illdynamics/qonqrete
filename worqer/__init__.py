"""WorQer package - contains the three worQer agents for QonQrete.

This package supersedes the legacy `worker` package.  It includes the
instruQtor (planner), construQtor (executor) and inspeQtor (reviewer).
Each worQer reads its configuration from the worqspace and prepends the
direQtor prompt (from the `DIREQTOR_PROMPT` environment variable) to
its LLM prompts.
"""
"""MlxAdapter — OpenAI-compatible HTTP backend for Apple's local MLX server.

Routes every agent call to a separately-running ``mlx_lm.server`` process via
``/v1/chat/completions`` — the same adapter machinery llama.cpp uses, with the
MLX server's conventions.  The MLX model itself (MLX safetensors format on
Apple Silicon — NOT GGUF) is loaded and run by that server process; QonQrete
only talks to ``host:port`` while the model runs separately.

Default endpoint: http://127.0.0.1:8080/v1   (mlx_lm.server's default port)
Override via:
  - ``QQ_MLX_ENDPOINT`` env var
  - ``endpoint=`` kwarg to MlxAdapter()
  - ``local_endpoints.mlx`` in config/qq.yaml (wired by the CLI)

No API key is required for local servers.  Set ``QQ_MLX_API_KEY`` if your MLX
server sits behind an auth proxy.

Model-field handling
--------------------
llama.cpp ignores the request's ``model`` id.  ``mlx_lm.server`` does not: it
treats that id as the model to (re)load, so a placeholder such as ``local``
would make it try to load a model literally named "local".  When no explicit
model is configured, this adapter therefore OMITS the ``model`` field so the
server resolves its built-in ``default_model`` alias to the model it was
started with (``mlx_lm.server --model ... --port 8080``).  A concrete per-role
model id configured in config/qq.yaml is sent verbatim, which is the supported
way to load a *different* MLX model on a server started without ``--model``.
"""
from __future__ import annotations

from .llama_cpp import LlamaCppAdapter
from .base import AgentCallSpec


class MlxAdapter(LlamaCppAdapter):
    """OpenAI-compatible adapter targeting Apple's local MLX server.

    Mirrors the llama.cpp adapter (same HTTP flow, same WSL/endpoint helpers,
    same JSON-receipt handling) but defaults to the MLX server port and never
    sends a placeholder model name — the MLX server would treat it as a model
    to load.
    """

    name = "mlx"
    provider_label = "mlx"
    server_name = "MLX server"
    server_binary = "mlx_lm.server"
    endpoint_env_var = "QQ_MLX_ENDPOINT"
    api_key_env_var = "QQ_MLX_API_KEY"
    default_endpoint = "http://127.0.0.1:8080/v1"
    default_model = "local"
    send_default_model = False

    def _payload_model(self, spec: AgentCallSpec):
        """Model id to send, or ``None`` to omit the field entirely.

        ``mlx_lm.server`` maps a request's ``model`` id straight to the model
        it loads (``_model_map.get(model, model)``), so sending the ``local``
        placeholder would try to load a model literally named "local".  When
        only the placeholder is set we omit the field, letting the server use
        the model it was started with.  An explicit model id is passed through
        verbatim so users can target a specific MLX model.
        """
        model = (spec.model or self.default_model or "").strip()
        if not model or model == self.default_model:
            return None
        return model

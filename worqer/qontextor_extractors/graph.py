from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

GRAPH_SCHEMA_VERSION = "2.0"
GRAPH_NODE_TYPES = [
    "file",
    "module",
    "class",
    "function",
    "method",
    "variable",
    "selector",
    "html_element",
    "html_id",
    "html_class",
    "shell_function",
    "command",
    "env_var",
    "asset",
]
GRAPH_EDGE_TYPES = [
    "imports",
    "exports",
    "calls",
    "extends",
    "implements",
    "sources",
    "reads_env",
    "writes_env",
    "invokes_command",
    "links_asset",
    "matches_selector",
    "binds_event",
    "reads_storage",
    "writes_storage",
]


@dataclass
class GraphEdge:
    type: str
    source: str
    target: str
    line: Optional[int] = None
    resolved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "resolved": self.resolved,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class SymbolSummary:
    name: str
    type: str
    line: int
    signature: str
    purpose: str
    qualified_name: Optional[str] = None
    parent: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    docstring: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    reads_env: list[str] = field(default_factory=list)
    writes_env: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "line": self.line,
            "signature": self.signature,
            "purpose": self.purpose,
            "dependencies": sorted(dict.fromkeys(self.dependencies)),
        }
        if self.qualified_name:
            data["qualified_name"] = self.qualified_name
        if self.parent:
            data["parent"] = self.parent
        if self.decorators:
            data["decorators"] = self.decorators
        if self.docstring:
            data["docstring"] = self.docstring
        if self.reads_env:
            data["reads_env"] = sorted(dict.fromkeys(self.reads_env))
        if self.writes_env:
            data["writes_env"] = sorted(dict.fromkeys(self.writes_env))
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    def as_graph_node(self, file_path: str, module: Optional[str], language: str) -> dict[str, Any]:
        node = self.to_dict()
        node["id"] = self.qualified_name or f"{file_path}::{self.name}"
        node["file_path"] = file_path
        node["module"] = module
        node["language"] = language
        return node


@dataclass
class FileContext:
    file_path: str
    language: Optional[str] = None
    extractor: Optional[str] = None
    module: Optional[str] = None
    symbols: list[SymbolSummary] = field(default_factory=list)
    summary: Optional[str] = None
    error: Optional[str] = None
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    inbound_refs: list[str] = field(default_factory=list)
    relationships: list[GraphEdge] = field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = field(default_factory=list)
    file_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if self.error:
            return {
                "file_path": self.file_path,
                "language": self.language,
                "extractor": self.extractor,
                "error": self.error,
                "graph_schema": {
                    "version": GRAPH_SCHEMA_VERSION,
                    "node_types": GRAPH_NODE_TYPES,
                    "edge_types": GRAPH_EDGE_TYPES,
                },
            }

        data: dict[str, Any] = {
            "file_path": self.file_path,
            "language": self.language,
            "extractor": self.extractor,
            "graph_schema": {
                "version": GRAPH_SCHEMA_VERSION,
                "node_types": GRAPH_NODE_TYPES,
                "edge_types": GRAPH_EDGE_TYPES,
            },
        }
        if self.module:
            data["module"] = self.module
        if self.summary:
            data["summary"] = self.summary
        if self.symbols:
            data["symbols"] = [symbol.to_dict() for symbol in self.symbols]
        if self.imports:
            data["imports"] = sorted(dict.fromkeys(self.imports))
        if self.exports:
            data["exports"] = sorted(dict.fromkeys(self.exports))
        if self.dependencies:
            data["dependencies"] = sorted(dict.fromkeys(self.dependencies))
        if self.inbound_refs:
            data["inbound_refs"] = sorted(dict.fromkeys(self.inbound_refs))
        if self.relationships:
            data["relationships"] = [edge.to_dict() for edge in self.relationships]
        if self.graph_nodes:
            data["graph_nodes"] = self.graph_nodes
        if self.file_metadata:
            data["file_metadata"] = self.file_metadata
        return data


class ProjectGraph:
    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self.contexts: dict[Path, FileContext] = {}
        self.modules: dict[str, FileContext] = {}
        self.symbols_by_qname: dict[str, SymbolSummary] = {}
        self.file_to_module: dict[str, str] = {}
        self.file_nodes: dict[str, str] = {}
        self.node_index: dict[str, dict[str, Any]] = {}
        self.top_level_by_module: dict[str, dict[str, str]] = defaultdict(dict)
        self.class_methods: dict[str, dict[str, str]] = defaultdict(dict)
        self.package_inits: set[str] = set()
        self.extra: dict[str, Any] = defaultdict(dict)

    def register_context(self, file_path: Path, ctx: FileContext) -> None:
        resolved = file_path.resolve()
        self.contexts[resolved] = ctx
        if ctx.module:
            self.modules[ctx.module] = ctx
            self.file_to_module[ctx.file_path] = ctx.module
        for node in ctx.graph_nodes:
            node_id = node.get("id")
            if node_id:
                self.node_index[node_id] = node
                if node.get("type") == "file":
                    self.file_nodes[ctx.file_path] = node_id
        for symbol in ctx.symbols:
            if symbol.qualified_name:
                self.symbols_by_qname[symbol.qualified_name] = symbol

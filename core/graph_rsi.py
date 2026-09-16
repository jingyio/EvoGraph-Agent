"""A small, dependency-free implementation of the Graph RSI invariants.

The production runtime lives on the ``develop`` branch.  This module deliberately
keeps only the pieces needed to inspect and test the mechanism: validated DAGs,
current-task binding, version lineage, and evidence that a later task used a
specific version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


class GraphValidationError(ValueError):
    """Raised when a graph or a current-task binding is unsafe to execute."""


@dataclass(frozen=True)
class GraphNode:
    """One reusable operation; it holds structure, never a prior task result."""

    node_id: str
    operation: str
    depends_on: tuple[str, ...] = ()
    parameter_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionGraph:
    graph_id: str
    nodes: tuple[GraphNode, ...]

    def validate(self) -> None:
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise GraphValidationError("node IDs must be unique")
        known = set(ids)
        for node in self.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise GraphValidationError(
                    f"{node.node_id} depends on unknown node(s): {sorted(unknown)}"
                )

        remaining = {node.node_id: set(node.depends_on) for node in self.nodes}
        resolved: set[str] = set()
        while remaining:
            ready = [node_id for node_id, deps in remaining.items() if deps <= resolved]
            if not ready:
                raise GraphValidationError("graph contains a dependency cycle")
            for node_id in ready:
                resolved.add(node_id)
                del remaining[node_id]

    @property
    def required_slots(self) -> frozenset[str]:
        return frozenset(slot for node in self.nodes for slot in node.parameter_slots)


@dataclass(frozen=True)
class Binding:
    """Only current task values that an executed graph node actually consumes."""

    values: Mapping[str, Any]
    ignored_values: tuple[str, ...] = ()


def bind_current_task(graph: ExecutionGraph, provided: Mapping[str, Any]) -> Binding:
    """Validate and normalize current parameters without inventing business values.

    Extra values are retained only in an audit field.  This lets a matcher submit a
    broad candidate binding without causing a safe selected subgraph to fall back;
    missing required slots still fail closed.
    """

    graph.validate()
    required = graph.required_slots
    missing = required - set(provided)
    if missing:
        raise GraphValidationError(f"missing current value(s): {sorted(missing)}")
    values = {name: provided[name] for name in required}
    ignored = tuple(sorted(set(provided) - required))
    return Binding(values=values, ignored_values=ignored)


@dataclass(frozen=True)
class GraphVersion:
    version_id: str
    graph: ExecutionGraph
    source_run_id: str
    parent_version_id: str | None = None
    change_kind: str = "creation"
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()


@dataclass(frozen=True)
class VersionUse:
    run_id: str
    task_id: str
    version_id: str
    executed_nodes: tuple[str, ...]


@dataclass
class VersionLedger:
    """Append-only provenance for creation, revision, and real later use."""

    versions: dict[str, GraphVersion] = field(default_factory=dict)
    uses: list[VersionUse] = field(default_factory=list)

    def add(self, version: GraphVersion) -> None:
        version.graph.validate()
        if version.version_id in self.versions:
            raise GraphValidationError(f"duplicate graph version: {version.version_id}")
        if version.parent_version_id and version.parent_version_id not in self.versions:
            raise GraphValidationError("parent graph version is not recorded")
        if version.parent_version_id:
            parent = self.versions[version.parent_version_id]
            added, removed = structural_diff(parent.graph, version.graph)
            if not (added or removed):
                raise GraphValidationError("a revision needs a structural graph difference")
            if version.added_nodes and tuple(sorted(version.added_nodes)) != added:
                raise GraphValidationError("recorded added nodes do not match the graph diff")
            if version.removed_nodes and tuple(sorted(version.removed_nodes)) != removed:
                raise GraphValidationError("recorded removed nodes do not match the graph diff")
        self.versions[version.version_id] = version

    def record_use(
        self, *, run_id: str, task_id: str, version_id: str, executed_nodes: Iterable[str]
    ) -> VersionUse:
        version = self.versions.get(version_id)
        if version is None:
            raise GraphValidationError("used graph version is not recorded")
        if run_id == version.source_run_id:
            raise GraphValidationError("creation is not evidence of a later graph use")
        valid_nodes = {node.node_id for node in version.graph.nodes}
        executed = tuple(executed_nodes)
        if not executed or not set(executed) <= valid_nodes:
            raise GraphValidationError("a use must name actual nodes from that graph version")
        use = VersionUse(run_id, task_id, version_id, executed)
        self.uses.append(use)
        return use


def structural_diff(before: ExecutionGraph, after: ExecutionGraph) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return added and removed nodes. Changed node contracts count as remove + add."""

    before_by_id = {node.node_id: node for node in before.nodes}
    after_by_id = {node.node_id: node for node in after.nodes}
    added = tuple(sorted(
        node_id for node_id, node in after_by_id.items()
        if node_id not in before_by_id or before_by_id[node_id] != node
    ))
    removed = tuple(sorted(
        node_id for node_id, node in before_by_id.items()
        if node_id not in after_by_id or after_by_id[node_id] != node
    ))
    return added, removed

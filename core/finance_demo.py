"""A runnable current-data finance reconciliation example for the minimal core."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .graph_rsi import (
    ExecutionGraph,
    GraphNode,
    GraphVersion,
    VersionLedger,
    bind_current_task,
    structural_diff,
)


@dataclass(frozen=True)
class ReconciliationResult:
    task_id: str
    graph_version: str
    order_count: int
    paid_cents: int
    expected_cents: int
    flagged_orders: Mapping[str, tuple[str, ...]]
    evidence: Mapping[str, tuple[str, ...]]
    ignored_binding_values: tuple[str, ...]


def finance_graph(include_installment_check: bool = True) -> ExecutionGraph:
    """A graph stores operations and slots, not old order IDs or amounts."""

    nodes = [
        GraphNode("orders", "read_current_orders"),
        GraphNode("payments", "read_current_payments"),
        GraphNode("items", "read_current_items"),
        GraphNode("reconcile", "sum_and_compare", ("orders", "payments", "items"), ("difference_cents",)),
        GraphNode("missing", "find_missing_records", ("orders", "payments", "items")),
    ]
    if include_installment_check:
        nodes.append(
            GraphNode(
                "installments",
                "flag_high_installments",
                ("payments",),
                ("installment_threshold",),
            )
        )
    return ExecutionGraph("finance-reconciliation", tuple(nodes))


def reconcile_current_attachment(
    *,
    task_id: str,
    graph_version: str,
    graph: ExecutionGraph,
    attachment: Mapping[str, Sequence[Mapping[str, Any]]],
    parameters: Mapping[str, Any],
) -> ReconciliationResult:
    """Recompute every amount and evidence reference from the supplied attachment."""

    binding = bind_current_task(graph, parameters)
    orders = {str(row["order_id"]): row for row in attachment["orders"]}
    payments_by_order: dict[str, list[Mapping[str, Any]]] = {order_id: [] for order_id in orders}
    items_by_order: dict[str, list[Mapping[str, Any]]] = {order_id: [] for order_id in orders}
    for row in attachment["payments"]:
        payments_by_order.setdefault(str(row["order_id"]), []).append(row)
    for row in attachment["items"]:
        items_by_order.setdefault(str(row["order_id"]), []).append(row)

    uses_installments = "installments" in {node.node_id for node in graph.nodes}
    flagged: dict[str, tuple[str, ...]] = {}
    evidence: dict[str, tuple[str, ...]] = {}
    expected_total = 0
    paid_total = 0

    for order_id in sorted(orders):
        order = orders[order_id]
        payments = payments_by_order.get(order_id, [])
        items = items_by_order.get(order_id, [])
        expected = sum(int(row["line_cents"]) + int(row.get("freight_cents", 0)) for row in items)
        paid = sum(int(row["amount_cents"]) for row in payments)
        expected_total += expected
        paid_total += paid
        reasons: list[str] = []
        refs = [f"order:{order_id}"]
        refs.extend(f"payment:{row['payment_id']}" for row in payments)
        refs.extend(f"item:{row['item_id']}" for row in items)
        if not payments:
            reasons.append("缺少支付资料")
        if not items:
            reasons.append("缺少商品资料")
        if payments and items and abs(paid - expected) > int(binding.values["difference_cents"]):
            reasons.append("金额差异")
        if uses_installments and any(
            int(row.get("installments", 1)) >= int(binding.values["installment_threshold"])
            for row in payments
        ):
            reasons.append("高分期")
        if reasons:
            flagged[order_id] = tuple(reasons)
            evidence[order_id] = tuple(refs)

    return ReconciliationResult(
        task_id=task_id,
        graph_version=graph_version,
        order_count=len(orders),
        paid_cents=paid_total,
        expected_cents=expected_total,
        flagged_orders=flagged,
        evidence=evidence,
        ignored_binding_values=binding.ignored_values,
    )


def sample_attachment(order_id: str, paid_cents: int) -> dict[str, list[dict[str, Any]]]:
    """Two different current inputs used to show that a graph never copies outcomes."""

    return {
        "orders": [{"order_id": order_id}],
        "payments": [
            {"payment_id": f"pay-{order_id}", "order_id": order_id, "amount_cents": paid_cents, "installments": 10}
        ],
        "items": [
            {"item_id": f"item-{order_id}", "order_id": order_id, "line_cents": 9_500, "freight_cents": 500}
        ],
    }


def run_demo() -> dict[str, Any]:
    """Create G0, revise it, then show a later task really using G1."""

    g0 = finance_graph(include_installment_check=False)
    g1 = finance_graph(include_installment_check=True)
    added, removed = structural_diff(g0, g1)
    ledger = VersionLedger()
    ledger.add(GraphVersion("G0", g0, source_run_id="run-train-01"))
    ledger.add(
        GraphVersion(
            "G1",
            g1,
            source_run_id="run-train-02",
            parent_version_id="G0",
            change_kind="coverage_extension",
            added_nodes=added,
            removed_nodes=removed,
        )
    )
    later = reconcile_current_attachment(
        task_id="review-current-03",
        graph_version="G1",
        graph=g1,
        attachment=sample_attachment("order-current-03", paid_cents=10_800),
        parameters={"difference_cents": 5, "installment_threshold": 8, "unused_candidate_slot": "audit only"},
    )
    ledger.record_use(
        run_id="run-review-03",
        task_id=later.task_id,
        version_id="G1",
        executed_nodes=(node.node_id for node in g1.nodes),
    )
    return {
        "result": asdict(later),
        "version_lineage": [asdict(version) for version in ledger.versions.values()],
        "actual_later_use": asdict(ledger.uses[-1]),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))

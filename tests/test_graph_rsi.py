import unittest

from core.finance_demo import finance_graph, reconcile_current_attachment, sample_attachment
from core.graph_rsi import ExecutionGraph, GraphNode, GraphValidationError, GraphVersion, VersionLedger, bind_current_task, structural_diff


class GraphRsiCoreTests(unittest.TestCase):
    def test_cycles_fail_closed(self):
        graph = ExecutionGraph("cycle", (GraphNode("a", "read", ("b",)), GraphNode("b", "read", ("a",))))
        with self.assertRaises(GraphValidationError):
            graph.validate()

    def test_current_binding_keeps_only_needed_slots(self):
        graph = finance_graph()
        binding = bind_current_task(graph, {"difference_cents": 5, "installment_threshold": 8, "old_order_id": "never-used"})
        self.assertEqual(set(binding.values), {"difference_cents", "installment_threshold"})
        self.assertEqual(binding.ignored_values, ("old_order_id",))
        with self.assertRaises(GraphValidationError):
            bind_current_task(graph, {"difference_cents": 5})

    def test_same_graph_recomputes_new_current_business_values(self):
        graph = finance_graph()
        parameters = {"difference_cents": 5, "installment_threshold": 8}
        first = reconcile_current_attachment(task_id="t1", graph_version="G1", graph=graph, attachment=sample_attachment("order-a", 10_800), parameters=parameters)
        second = reconcile_current_attachment(task_id="t2", graph_version="G1", graph=graph, attachment=sample_attachment("order-b", 10_000), parameters=parameters)
        self.assertEqual(first.flagged_orders["order-a"], ("金额差异", "高分期"))
        self.assertNotIn("order-a", second.flagged_orders)
        self.assertEqual(second.paid_cents, 10_000)

    def test_revision_has_diff_and_later_actual_use(self):
        g0 = finance_graph(False)
        g1 = finance_graph(True)
        added, removed = structural_diff(g0, g1)
        self.assertEqual(added, ("installments",))
        self.assertEqual(removed, ())
        ledger = VersionLedger()
        ledger.add(GraphVersion("G0", g0, "train-01"))
        ledger.add(GraphVersion("G1", g1, "train-02", "G0", "coverage_extension", added, removed))
        use = ledger.record_use(run_id="review-03", task_id="t3", version_id="G1", executed_nodes=(node.node_id for node in g1.nodes))
        self.assertEqual(use.version_id, "G1")
        self.assertEqual(len(ledger.uses), 1)
        with self.assertRaises(GraphValidationError):
            ledger.record_use(
                run_id="train-02",
                task_id="t3",
                version_id="G1",
                executed_nodes=(node.node_id for node in g1.nodes),
            )


if __name__ == "__main__":
    unittest.main()

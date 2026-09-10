# Minimal AutoTool Inertia Design

Date: 2026-09-10. This is a bounded supplement to Graph RSI, not a full reproduction of AutoTool (arXiv:2511.14650).

## Goal and modes

`motif_only` runs the selected current Plan DAG, historical Workflow, or Persistent TinyEdge exactly as Graph RSI does, then uses the existing model execution loop. `motif_first` uses the same route, but at a historical graph handoff where the original loop is about to ask the executor model for unresolved reads, attempts at most one read-only inertial call before returning to that loop. It does not alter DAG scheduling, introduce `autotool_first`, or run candidate rollouts.

The trace names the sources separately: `plan-dag` is this-run compilation; `persisted-graph` and `persistent-tinyedge` are historical structures; `model` is an LLM decision; and `inertia` is AutoTool's local execution. A compiled DAG is never presented as a historical Motif hit.

## Minimal TIG record

`artifacts/online-graphs.json` gains a backwards-compatible `toolInertia` payload. It stores no old task IDs, record values, answers, or observations:

- `toolPaths`: normalized serial model-origin tool paths, support, and source run/task IDs;
- `parameterEdges`: `(source tool, normalized output path) -> (target tool, parameter)` contracts, support, and sources;
- schema/contract identity and aggregate update information.

Only passed `train` runs update it. The extractor accepts a transition only if the preceding model tool observation completed before the next model action began. Therefore calls from one concurrent read batch cannot create a fake dependency. Graph- and inertia-origin calls remain traceable but never reinforce TIG statistics.

## Search and binding

Before the eligible model call, local search takes the current recent successful tool names (regardless of runtime source), matches learned model-origin paths, and scores candidates by conservative frequency/confidence plus deterministic lexical intent-to-tool-description relevance. The paper calls this CIPS; this implementation logs both components but uses local token overlap rather than embeddings or hidden `thought` extraction. It requires support >= 2 and a fixed acceptance threshold.

For each required parameter, binding only follows a learned parameter edge to a value in this run's successful observation ledger. Array positions are stored as wildcards and bind only when they resolve to one type-valid unique current value. Missing, ambiguous, invalid, or schema-incompatible values reject the whole call. Task text, prior business values, environment-specific heuristic filling, and model calls for tool selection or thought are excluded.

The first release allows only registered `read` tools. It rejects a same-signature successful call, an already complete observation, unavailable tools, and budget overflow. One accepted or failed attempt is followed by the normal scheduler/model recovery; every rejection, tool error, and later recovery model cost is retained.

## Relation to the paper

The paper's Sections 4.2-4.5 and Algorithm 1 use an inertial attempt before each standard LLM decision, a dynamic Tool Inertia Graph with sequence and parameter edges, CIPS frequency/context scoring, and hierarchical parameter filling. Appendix A describes a default inertia window of two, a confidence factor for sparse paths, and an environment Adapter with contextual and heuristic filling.

This project preserves the two-stage gate and LLM-origin learning rule, but intentionally omits embeddings, `thought` extraction, Adapter/environment context, heuristic parameter filling, negative path weighting, tool-node cached examples, and cross-environment bootstrap. These omissions prevent task-answer leakage and keep the taskbank runtime deterministic. Current BM25 tool retrieval/read-DAG compilation is separate functionality and is not called TIG.

## Acceptance

Protocol tests must prove train-only/model-only updates; parameter provenance; all binding rejects; no duplicate read; one-call bounds; and recovery. A real precheck uses a small number of normal train tasks. A later bounded paired evaluation freezes the same graph and inertia snapshot for `motif_only` and `motif_first`; it reports actual model/token/tool/latency deltas including local TIG query/update/persist time and does not infer benefit from acceptance alone. Validation/test never update TIG or Motif.

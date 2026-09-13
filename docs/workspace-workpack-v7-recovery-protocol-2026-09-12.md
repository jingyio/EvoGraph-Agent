# Workspace Workpack V7 Shared-Recovery Protocol

Date: 2026-09-12. This document defines the next isolated online experiment
after the V6 precheck diagnostic. It does not alter or replace any saved V5 or
V6 artifact.

## Why V7 Is Required

V6 exposed a shared quality failure in `tickets-triage-01`: the first report
had the correct business metrics and selection, but had read only one activity
row. The public delivery contract named source files, while private validation
required all rows from the declared sources as evidence. Generic recovery then
asked the model to infer the missing scope and terminated after a repeated
`evidence_coverage` signature.

This is neither a Graph RSI advantage nor a valid same-quality cost comparison:
it affects the shared report/runtime boundary used by Plan + ReAct and RSI.
V6 is retained as an invalid cost diagnostic, including all requests and token
usage already incurred.

## V7 Change and Boundary

Each materialized workpack now adds public `deliveryContract.requiredTableSlots`.
The slots are schema-level names for sources already declared by the task, such
as `orders` or `activity`; they never include row IDs, expected metrics,
selected IDs, or private validation evidence.

After an `evidence_coverage` failure with actual missing observations, the
runtime may:

1. page through only those publicly declared current-workspace tables;
2. re-submit the unchanged business fields of the prior report;
3. let normal evidence canonicalization derive IDs from the new observations.

It may not reveal private validator data to the model, alter metrics or
selection, retry an unchanged failure without progress, or invoke another model
turn for this deterministic operation. The logic is shared by `plan_react` and
`graph_rsi`; `modelRequests`, recovery reads, and deterministic resubmits are
recorded separately.

## Verification Before Paid Runs

- Regression covers both Plan + ReAct and Graph RSI with a two-row public
  table: the model reads one row and publishes correct business fields;
  runtime completes the public scope, re-submits once, and makes no later model
  request.
- `install_workpack` has a regression-covered table-slot contract.
- V7 starts from a new experiment directory and separate empty RSI experience.
  V6 experience, artifacts, and results are never reused.

## Staged Online Plan

1. `smoke_v7`: three frozen train workpacks, one per scenario, six Agent runs.
2. If both arms pass hard validation at the exact V7 runtime fingerprint,
   `precheck_v7`: twelve frozen train workpacks, 24 Agent runs.
3. Only a V7 quality-passing precheck may enable `full_train_v5`: 48 workpacks
   per arm, 96 Agent runs.

All stages are serial: `run_limit=model_limit=read_limit=1`. Baseline remains
strong Plan + ReAct without cross-task learning. RSI starts empty, updates only
after passed train tasks, and may use only prior snapshots. Judge cost remains
separate and is not started with Agent runs.

## Claim Rules

A V7 token comparison is valid only if every started task in both arms passes
private structured fact and evidence validation. Otherwise token totals remain
a failure diagnosis, not a same-quality saving. V7 may demonstrate G0 formation
and later Fast use only if saved traces show it; it must not claim Composition,
G1/G2, or a 30% saving without observed evidence.

# Relevance Handoff / 关联筛选交接

## Decision Vocabulary / 决策词表

Use one primary decision:

- `ignore`: irrelevant or unusable
- `archive`: worth keeping as background only
- `watch`: interesting, but missing evidence or maturity
- `knowledge_mapping`: map ideas into existing knowledge
- `architecture_mapping`: compare architecture against current system structure
- `light_validation`: run a small isolated smoke test
- `capability_intake`: package or adopt a reusable capability
- `task_dispatch`: create a control-plane task for a project
- `export_candidate`: prepare a public/shareable package

## Minimum Batch Summary / 最小批量总结

For each readable source, answer:

- what it says
- what is worth absorbing
- what overlaps with the current system
- what the real gap is
- what practical effect adoption would create
- what the next decision is

For blocked sources, answer:

- what was captured
- what was not read
- what blocker stopped extraction
- what input would be needed to analyze the actual content

## Progressive Context Reading / 渐进式上下文读取

Read context in levels and stop once the decision is supported:

| level | read | use |
| --- | --- | --- |
| `L0-routing` | hot cache, indexes, source metadata | choose tags and likely owner |
| `L1-topic` | matching concept pages and existing bridges | compare knowledge |
| `L2-project-capsule` | project registry, README, project summary | compare project state |
| `L3-evidence` | run reports, scripts, tests, artifacts | prove overlap or gap |
| `L4-implementation` | code and dependencies | only for validation or implementation |

Do not read an entire project before tags justify it.

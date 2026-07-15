---
goal: Reframe the Chinese manuscript around auditable regulatory evidence retrieval and structured fact verification
version: 1.0
date_created: 2026-07-15
last_updated: 2026-07-15
owner: Kaifeng Sun
status: 'Completed'
tags: [paper, narrative, regulatory-evidence, retrieval, knowledge-graph]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan restructures the Chinese manuscript so that its claims match the frozen experiments: text retrieval locates regulatory source passages, while structured graph paths provide a separately evaluated fact-verification channel.

## 1. Requirements & Constraints

- **REQ-001**: Rewrite the title, abstract, introduction, contributions, research questions, result interpretation, discussion, and conclusion around the two-task evidence model.
- **REQ-002**: Preserve every reported metric and frozen experimental outcome.
- **REQ-003**: State that only the selective reranking study used a locked confirmatory design.
- **REQ-004**: Limit the graph result to recovery of six small-sample, human-accepted structured paths.
- **CON-001**: Do not rerun retrieval or evaluation experiments.
- **CON-002**: Do not claim SOTA performance, causal shortage prediction, graph superiority over structured-query baselines, or annotator agreement.
- **CON-003**: Keep `sections/draft_chinese.md` unchanged and edit only `sections/draft_chinese_rewritten.md`.
- **SEC-001**: Do not introduce private API keys, local review workbooks, or excluded data into Git.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Align the manuscript's headline claims and task formulation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Rewrite the title and abstract in `sections/draft_chinese_rewritten.md` around text-first evidence retrieval and structured fact verification. | Yes | 2026-07-15 |
| TASK-002 | Rewrite the introduction and contribution list so each contribution is supported by an existing artifact or experiment. | Yes | 2026-07-15 |
| TASK-003 | Revise the task definition and method overview to separate source chunks, hierarchy context, and structured graph paths. | Yes | 2026-07-15 |

### Implementation Phase 2

- GOAL-002: Align experiments, findings, limitations, and reproducibility claims.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Rewrite RQ1-RQ5 and the result-section framing without changing metrics. | Yes | 2026-07-15 |
| TASK-005 | Rewrite discussion and conclusion to distinguish observed findings, design rules, and future hypotheses. | Yes | 2026-07-15 |
| TASK-006 | Add explicit limitations for single-reviewer gold construction, missing answer-level evaluation, structured-query baselines, path efficiency, and frozen snapshot status. | Yes | 2026-07-15 |
| TASK-007 | Run claim, number, placeholder, and terminology consistency checks. | Yes | 2026-07-15 |
| TASK-008 | Commit and push the reviewed manuscript changes as a separate Git commit. | Yes | 2026-07-15 |

## 3. Alternatives

- **ALT-001**: Change only the title and abstract. Rejected because the method-centric research questions and discussion would remain inconsistent.
- **ALT-002**: Add new external baselines before rewriting. Deferred because the current task is to correct claims using already frozen evidence.
- **ALT-003**: Remove all graph experiments. Rejected because the six structured paths provide valid small-sample evidence about traceable relationship representation.

## 4. Dependencies

- **DEP-001**: `docs/superpowers/specs/2026-07-15-regulatory-evidence-narrative-redesign.md`.
- **DEP-002**: Frozen retrieval and statistical reports under the locally excluded `outputs/` directory.
- **DEP-003**: Current manuscript at `sections/draft_chinese_rewritten.md`.

## 5. Files

- **FILE-001**: `sections/draft_chinese_rewritten.md`, the only manuscript file modified.
- **FILE-002**: `plan/refactor-paper-regulatory-evidence-narrative-1.md`, execution record updated after validation.

## 6. Testing

- **TEST-001**: Verify no `TODO`, `TBD`, or `FIXME` markers remain.
- **TEST-002**: Verify all headline metrics match frozen formal reports.
- **TEST-003**: Search for unsupported phrases implying universal graph, dense-retrieval, or reranking superiority.
- **TEST-004**: Verify the manuscript explicitly distinguishes exploratory, held-out, and confirmatory evidence.
- **TEST-005**: Run the existing 92-test Python suite to ensure repository integrity before push.

## 7. Risks & Assumptions

- **RISK-001**: A GraphRAG-centered title could continue to invite inappropriate SOTA comparisons.
- **RISK-002**: Six structured paths could be overgeneralized beyond their small-sample scope.
- **RISK-003**: The current single-reviewer process limits gold-standard reliability claims.
- **ASSUMPTION-001**: The frozen result reports remain the sole numerical source of truth.
- **ASSUMPTION-002**: English manuscript preparation begins only after user approval of the revised Chinese version.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-15-regulatory-evidence-narrative-redesign.md`
- `docs/three_path_formal_evaluation_protocol_2026-07-11.md`
- `docs/experiments/adaptive_text_first_heldout_protocol_2026-07-15.md`

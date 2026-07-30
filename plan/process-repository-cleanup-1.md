---
goal: Prepare BioGraph for public reproducibility while removing approved local waste
version: 1.0
date_created: 2026-07-30
last_updated: 2026-07-30
owner: Kaifeng Sun
status: 'Completed'
tags: [process, cleanup, reproducibility, git]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-green)

Execute the approved path-level cleanup, preserve all frozen research assets,
and improve the tracked repository without rewriting public Git history.

## 1. Requirements & Constraints

- **REQ-001**: Delete only paths listed in the approved design specification.
- **REQ-002**: Preserve frozen data, models, Neo4j state, audit records, canonical outputs, and final manuscripts.
- **REQ-003**: Keep existing experiment entry-point paths stable.
- **REQ-004**: Make `pytest -q` run only the intended BioGraph test suite.
- **REQ-005**: Keep manuscript result validation passing.
- **SEC-001**: Do not track API keys, credentials, raw copyrighted PDFs, or private reviewer workbooks.
- **CON-001**: Do not run generic Git prune, rewrite history, or force-push.
- **CON-002**: Commit recoverable checkpoints after each implementation phase.
- **PAT-001**: Use literal-path deletion and pre/post SHA-256 inventories.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Record a recoverable pre-cleanup baseline.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Record starting `main` and `origin/main` commit IDs in `artifacts/repository_cleanup_2026-07-30/baseline.json`. | Yes | 2026-07-30 |
| TASK-002 | Generate preserved-file SHA-256 inventory in `artifacts/repository_cleanup_2026-07-30/preserved_before.json`. | Yes | 2026-07-30 |
| TASK-003 | Record the literal deletion allowlist and pre-delete sizes. | Yes | 2026-07-30 |

### Implementation Phase 2

- GOAL-002: Remove only approved generated or superseded local files.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Delete each existing path in the approved literal allowlist with verified absolute PowerShell/.NET paths. | Yes | 2026-07-30 |
| TASK-005 | Verify the approved Codex snapshot ref is absent after Word-build files are tracked. | Yes | 2026-07-30 |
| TASK-006 | Record deleted paths and reclaimed bytes in the cleanup report. | Yes | 2026-07-30 |

### Implementation Phase 3

- GOAL-003: Improve repository configuration and documentation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Normalize `.gitignore` and add missing generated-file rules without untracking preserved files. | Yes | 2026-07-30 |
| TASK-008 | Replace `requirements.txt` and add optional/dev dependency files based on actual imports. | Yes | 2026-07-30 |
| TASK-009 | Add `pytest.ini` with `testpaths = tests`. | Yes | 2026-07-30 |
| TASK-010 | Track Word manuscript build scripts. | Yes | 2026-07-30 |
| TASK-011 | Add reproducibility and script-index documentation; update `README.md` and `PROJECT_DOCUMENTATION.md`. | Yes | 2026-07-30 |

### Implementation Phase 4

- GOAL-004: Verify preservation and publish the cleanup commit.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Generate `preserved_after.json` and compare it to the pre-cleanup inventory. | Yes | 2026-07-30 |
| TASK-013 | Run `pytest -q` and require all intended tests to pass. | Yes | 2026-07-30 |
| TASK-014 | Run manuscript validation and repository secret/large-file audits. | Yes | 2026-07-30 |
| TASK-015 | Commit tracked changes, push `main`, and verify starting commits remain ancestors. | Yes | 2026-07-30 |

## 3. Alternatives

- **ALT-001**: Aggressive cleanup was rejected because models and historical experiment assets may be needed during peer review.
- **ALT-002**: GitHub-only cleanup was rejected because known superseded local outputs occupy more than 5 GB.
- **ALT-003**: Broad script relocation was rejected because it would add path-breakage risk without improving reproducibility.

## 4. Dependencies

- **DEP-001**: Git command-line client configured for `origin`.
- **DEP-002**: PowerShell with SHA-256 hashing support.
- **DEP-003**: `D:\Anaconda3\python.exe` with the currently validated BioGraph test environment.
- **DEP-004**: Approved design at `docs/superpowers/specs/2026-07-30-repository-cleanup-design.md`.

## 5. Files

- **FILE-001**: `.gitignore`
- **FILE-002**: `requirements.txt`
- **FILE-003**: `requirements-optional.txt`
- **FILE-004**: `requirements-dev.txt`
- **FILE-005**: `pytest.ini`
- **FILE-006**: `README.md`
- **FILE-007**: `PROJECT_DOCUMENTATION.md`
- **FILE-008**: `docs/REPRODUCIBILITY.md`
- **FILE-009**: `docs/SCRIPT_INDEX.md`
- **FILE-010**: `paper/scripts/build_word_manuscript.py`
- **FILE-011**: `paper/scripts/plain_math.lua`
- **FILE-012**: `paper/scripts/word_numeric.csl`
- **FILE-013**: `artifacts/repository_cleanup_2026-07-30/*.json`

## 6. Testing

- **TEST-001**: `D:\Anaconda3\python.exe -m pytest -q`
- **TEST-002**: `D:\Anaconda3\python.exe paper/scripts/validate_paper.py`
- **TEST-003**: Compare preserved inventories by relative path, size, and SHA-256.
- **TEST-004**: Scan tracked and reachable text blobs for secret-like literals without printing values.
- **TEST-005**: Assert no tracked file exceeds 50 MiB.
- **TEST-006**: Assert starting local and remote commits remain ancestors of final tips.

## 7. Risks & Assumptions

- **RISK-001**: Deleted local outputs are intentionally unrecoverable; mitigation is the literal allowlist and pre-cleanup inventory.
- **RISK-002**: Dependency declarations may not cover optional external services; optional dependencies remain explicitly separated.
- **RISK-003**: Network interruption may prevent the final push; local commits preserve all source changes for later retry.
- **RISK-004**: A retired local Neo4j password remains in pre-cleanup public history. Current source no longer contains or prints it; the credential must be rotated. History rewriting was intentionally not performed.
- **RISK-005**: A Codex-managed local snapshot ref created during the cleanup retains one deleted 417.66 MiB blob. It is not part of `main` and will not be pushed; removing that newly created ref requires separate approval.
- **ASSUMPTION-001**: Per-query v3/v4 graph-ranking outputs supersede the two monolithic ranking files.
- **ASSUMPTION-002**: Final manuscript deliverables remain outside the deletion allowlist.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-30-repository-cleanup-design.md`
- `README.md`
- `paper/README.md`

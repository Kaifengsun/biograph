# Repository Cleanup and Reproducibility Design

Date: 2026-07-30

## Objective

Prepare the BioGraph project and public Git repository for journal or conference
review without removing frozen research assets. The local workspace retains its
historical directory name, `financial knowledge graph`, while the project and
public repository are named BioGraph. The cleanup should reduce local storage,
prevent generated files from entering Git, and make the tracked repository
easier to install, test, and audit.

## Constraints

- Deletion requires explicit user approval.
- Preserve frozen data, downloaded models, Neo4j state, reviewer records,
  canonical experiment outputs, and final manuscript deliverables.
- Do not reorganize established script paths solely for aesthetics.
- Do not rewrite or force-push the public `main` history.
- Do not expose API keys, local credentials, copyrighted PDFs, or reviewer
  workbooks in the public repository.

## Approved Cleanup Scope

Deletion is implemented as a literal-path allowlist. No wildcard or recursive
discovery may add paths beyond the directories explicitly listed below.

The user approved deletion of the following regenerable or superseded assets:

- `outputs/relation_chain_ranking_30_2026-07-18/rankings.json`
- `outputs/relation_chain_ranking_30_2026-07-18/rankings_v2.json`
- `System.Collections.Hashtable.Dir/`
- `.superpowers/`
- `.pytest_cache/`
- `__pycache__/`
- `tests/__pycache__/`
- `paper/main.aux`
- `paper/main.blg`
- `paper/main.log`
- `paper/main.out`
- `paper/main.synctex.gz`
- `paper/main.fdb_latexmk`
- `paper/main.fls`
- `outputs/docx_conversion_2026-07-20/`
- `outputs/paper_render_2026-07-20/`
- `outputs/paper_graph_update_render_2026-07-18/`
- `outputs/figure_design_preview_2026-07-20/`
- `paper/outputs/`
- `paper/build_unsrt/`
- `paper/validation/rendered_pages/`
- `run_full.log`
- `run_test.log`
- `qwen36_pilot.err`
- `qwen36_pilot.out`
- `.pipeline_pid`
- `.pipeline_run.cmd`
- `.pipeline_run.ps1`

The expected workspace reduction is approximately 5.19 GB.

The exact local snapshot ref
`refs/codex/turn-diffs/captures/1785414580846/e83af01e-5921-48b8-a10b-fe9d2b20f1f3/base`
may be removed only after the Word-build files it protects are committed.
Generic `git prune`, reflog expiration, history rewriting, and forced pushes are
outside this cleanup. Local Git object compaction is deferred because generic
garbage collection could remove unrelated recovery objects.

## Preserved Assets

- `data/`, including frozen evaluation records and source-derived artifacts
- `models/`
- `neo4j_docker_data/`
- `artifacts/`
- adjudication workbooks and audit records
- final experiment summaries and validation JSON
- final PDF, final Word manuscript, LaTeX source, figures, and bibliography
- current source code and tests

## Repository Changes

### Ignore policy

Normalize `.gitignore` and add explicit rules for local browser sessions,
failed download artifacts, Python caches, LaTeX intermediates, conversion
renders, local databases, model weights, raw corpora, review workbooks, and
credentials. Ignore changes must not delete, untrack, move, or modify any
preserved local asset.

### Reproducibility

- Replace the obsolete, incorrectly encoded dependency file with a dependency
  layout that distinguishes the tested core from optional heavy components.
- Add pytest configuration so default discovery runs the BioGraph tests under
  `tests/` and does not collect ignored local reference projects.
- Document the verified test command, manuscript validation command, local
  asset boundaries, and the relationship between final experiments and their
  entry-point scripts.
- Track the Word manuscript builder and its Pandoc support files.

### Git maintenance

Commit useful source and documentation before removing the exact Codex snapshot
ref named in the approved cleanup scope. Do not expire reflogs, prune objects,
rewrite history, or force-push. Record the starting `main` and `origin/main`
commit IDs. After the final commit and push, verify that both starting commits
remain ancestors of the new local and remote tips.

## Preservation Inventory

Before deletion, create a machine-readable inventory containing relative path,
file size, modification time, and SHA-256 for every file under the following
preserved roots:

- `data/`
- `models/`
- `neo4j_docker_data/`
- `artifacts/`
- `outputs/`, excluding the approved deletion allowlist
- `paper/`, excluding generated paths in the approved deletion allowlist

The inventory must explicitly include final manuscript deliverables and
review/audit files. Recompute the inventory after cleanup and require exact
path, size, and hash equality for all pre-cleanup preserved files. New
documentation or source files created during cleanup are recorded separately
and do not invalidate the preservation comparison.

## Verification

The cleanup is complete only when:

1. `pytest -q` runs only the intended suite under `tests/`; every collected test
   passes and there are no unexpected skips or collection errors. The current
   baseline is 113 passing tests.
2. `paper/scripts/validate_paper.py` reports `passed: true`.
3. A tracked-file scan and a Git-reachable-text-blob scan test for provider-key,
   password-assignment, and token-assignment patterns without printing secret
   values; both report no findings.
4. No tracked file is larger than 50 MiB, which is stricter than GitHub's
   maximum file policy.
5. `git status` is clean after the final commit.
6. the final manuscript files and approved frozen experiment outputs still
   exist.
7. The post-cleanup preservation inventory matches the pre-cleanup inventory
   for every preserved file.
8. The recorded starting `main` and `origin/main` commits remain ancestors of
   the final local and remote tips.

## Rollback

Source edits will be committed normally and can be reverted through Git. Local
files listed in the approved cleanup scope are intentionally not recoverable
after deletion. Canonical preserved assets and public Git history are outside
the deletion scope.

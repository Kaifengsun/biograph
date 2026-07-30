# Repository Cleanup and Reproducibility Design

Date: 2026-07-30

## Objective

Prepare the BioGraph workspace and public Git repository for journal or
conference review without removing frozen research assets. The cleanup should
reduce local storage, prevent generated files from entering Git, and make the
tracked repository easier to install, test, and audit.

## Constraints

- Deletion requires explicit user approval.
- Preserve frozen data, downloaded models, Neo4j state, reviewer records,
  canonical experiment outputs, and final manuscript deliverables.
- Do not reorganize established script paths solely for aesthetics.
- Do not rewrite or force-push the public `main` history.
- Do not expose API keys, local credentials, copyrighted PDFs, or reviewer
  workbooks in the public repository.

## Approved Cleanup Scope

The user approved deletion of the following regenerable or superseded assets:

- `outputs/relation_chain_ranking_30_2026-07-18/rankings.json`
- `outputs/relation_chain_ranking_30_2026-07-18/rankings_v2.json`
- `System.Collections.Hashtable.Dir/`
- `.superpowers/`
- Python and pytest cache directories
- LaTeX auxiliary files, excluding `main.bbl`
- Word/PDF conversion and manuscript render-QA directories
- Machine-local run logs, process IDs, and temporary launch files
- The local Codex turn-diff snapshot ref after its useful Word-build files have
  been committed

The expected workspace reduction is approximately 5.19 GB, plus approximately
290 MB from local Git object cleanup.

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
credentials.

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

Commit useful source and documentation before removing the Codex snapshot ref.
Delete only the local `refs/codex/turn-diffs/...` capture that retains the
accidental 418 MB blob, then expire unreachable objects and run Git garbage
collection. This must not change `main`, `origin/main`, or any public commit.

## Verification

The cleanup is complete only when:

1. `pytest -q` runs the BioGraph suite and reports 113 passing tests.
2. `paper/scripts/validate_paper.py` reports `passed: true`.
3. tracked-file and Git-history secret scans find no literal provider keys.
4. no tracked file exceeds the public repository size policy.
5. `git status` is clean after the final commit.
6. the final manuscript files and approved frozen experiment outputs still
   exist.

## Rollback

Source edits will be committed normally and can be reverted through Git. Local
files listed in the approved cleanup scope are intentionally not recoverable
after deletion. Canonical preserved assets and public Git history are outside
the deletion scope.

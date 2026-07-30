# Reproducibility

## What the repository preserves

The tracked repository contains the source code, experiment protocols, lock
metadata, aggregate result artifacts, manuscript sources, figures, tables,
bibliography, and automated validation checks used for the BioGraph paper.

The local working directory additionally contains frozen corpora, indexes,
model weights, Neo4j state, source-bearing review material, and API outputs.
Those assets are not automatically suitable for public redistribution.

## Environment

Use a dedicated Python environment:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional document-conversion and model-download utilities are listed in
`requirements-optional.txt`. MinerU is an external CLI dependency and should be
installed from its upstream project for the target hardware.

API keys and database credentials must be supplied through environment
variables. `.env.example` documents the supported LLM variables without
containing credentials.

## Fast verification

The following commands verify the maintained code and the manuscript/result
contract:

```powershell
python -m pytest -q
python paper/scripts/validate_paper.py
```

The second command checks headline values and experiment records used by the
paper. It is intended to detect accidental drift between frozen outputs and the
manuscript.

## Experiment families

- Regulatory source-chunk retrieval:
  `evaluate_bm25_enrichment_ablation.py`,
  `adaptive_text_first.py`, and the locked scripts referenced in
  `docs/experiments/`.
- Double annotation and adjudication:
  `tools/dual_annotation_60/`.
- Modern reranking extensions:
  `tools/modern_reranker_58/` and `tools/medcpt_58/`.
- Structured relation-chain evaluation:
  `tools/relation_chain_ranking/`.
- Manuscript consistency:
  `paper/scripts/validate_paper.py`.

The exact task order and supporting scripts are summarized in
`docs/SCRIPT_INDEX.md`.

## Frozen assets and limitations

Full end-to-end reproduction requires the same frozen source corpus, model
revisions, graph snapshot, and adjudicated evidence records. Several of these
files are intentionally absent from Git because they are large, copyrighted,
private, or machine-specific. Their omission should not be interpreted as a
claim that the public repository alone reproduces every API or annotation step.

For peer-review packaging, release only source material whose redistribution
terms permit it. When raw passages cannot be redistributed, provide stable
source identifiers, checksums, retrieval outputs, and instructions for
reconstructing the corpus from authoritative public sources.

## Integrity checks

Repository cleanup uses `tools/repository_cleanup_audit.py` to compare preserved
files by relative path, byte size, and SHA-256. Cleanup reports are local
artifacts and are excluded from Git because they include machine-specific
inventory information.

# BioGraph

BioGraph is a research prototype for auditable retrieval across pharmaceutical
regulatory text and structured drug-shortage facts. It deliberately separates
two evidence tasks:

1. retrieving source-grounded regulatory passages and tables; and
2. verifying structured relations among shortage events, NDC products, active
   ingredients, manufacturers, and source records.

The current study treats BM25 as a strong text-retrieval default. Hierarchical
navigation, neural reranking, and graph paths are evaluated as complementary
mechanisms with distinct evidence roles. The repository does not claim that
graph retrieval replaces source-text retrieval or that it outperforms general
GraphRAG systems.

## Repository map

- `pharma_doc_pipeline/`: document conversion, hierarchical chunking,
  enrichment, and vectorization.
- `pharma_graphrag/`: text, hierarchy, and graph retrieval components.
- `pharma_supply_chain/`: structured pharmaceutical data collection and graph
  construction.
- `tools/`: locked evaluation, annotation, adjudication, and audit utilities.
- `tests/`: the intended automated test suite.
- `paper/`: English LaTeX manuscript, figures, tables, bibliography, validation
  checks, and Word-build utilities.
- `docs/`: experiment protocols, design decisions, and reproducibility notes.

## Quick start

Create an isolated Python environment, then install the core dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install optional conversion and model-download tools only when needed:

```powershell
python -m pip install -r requirements-optional.txt
```

Configure API clients through user environment variables or an untracked
`.env` file. Use `.env.example` as the template and never commit real keys.

## Verification

Run the intended test suite from the repository root:

```powershell
python -m pytest -q
```

Validate that manuscript claims still match the frozen result artifacts:

```powershell
python paper/scripts/validate_paper.py
```

Build instructions for the LaTeX and Word manuscripts are in
`paper/README.md`. A task-oriented script map is available in
`docs/SCRIPT_INDEX.md`.

## Reproducibility boundary

Large model weights, local Neo4j state, raw PDFs, copyrighted source material,
review workbooks, API outputs, and machine-local logs are excluded from Git.
Tracked protocols, lock files, evaluation code, aggregate results, paper
assets, and validation checks document the reported experiments. See
`docs/REPRODUCIBILITY.md` for the exact boundary and verification workflow.

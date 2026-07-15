# BioGraph

BioGraph is a research prototype for auditable retrieval across pharmaceutical regulatory text and structured drug-shortage facts. The project separates two evidence tasks:

1. locating source-grounded regulatory passages with text-first retrieval; and
2. validating structured relationships among shortage records, products, NDCs, ingredients, manufacturers, and regulatory evidence.

The current empirical conclusion is deliberately conservative: BM25 is a strong default for regulatory source-passage retrieval, while hierarchical navigation and graph paths are complementary mechanisms for context traversal and structured fact verification. The repository does not claim general superiority over external GraphRAG systems.

## Repository contents

- `pharma_doc_pipeline/`: regulatory document processing
- `pharma_graphrag/`: hierarchical and graph retrieval components
- `pharma_supply_chain/`: structured supply-chain data processing
- `tests/`: automated tests
- `tools/`: review and experiment utilities
- `sections/`: Chinese manuscript drafts
- `docs/superpowers/specs/`: locked experiment and narrative design documents

Large indexes, local Neo4j databases, raw PDFs, review workbooks, API outputs, and machine-local logs are intentionally excluded from Git. A curated public data release and reproducibility package will be prepared separately after source licensing and privacy review.

## Environment

Install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Set API configuration through environment variables. See `.env.example`; do not place real credentials in tracked files.

## Research status

The Chinese manuscript and experiments are under active revision. Results should be interpreted as domain-specific evidence about retrieval roles and boundaries, not as a cross-system SOTA benchmark.


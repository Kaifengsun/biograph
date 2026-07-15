# Neo4j Cleanup Proposal

Status: proposal only. No cleanup query in this document has been executed.

## Why Cleanup Is Needed

The current graph has 4,016 `DocChunk` nodes while enriched JSON contains 2,410 chunks and FAISS contains 3,500 document vectors. Neo4j also contains duplicate document ID families and uses `(:DocChunk)-[:FROM_DOCUMENT]->(:Document)` where the intended canonical direction should be explicit and consistent.

The preferred approach is to rebuild from frozen enriched JSON after document ID normalization. Incrementally deleting nodes from the live graph before the corpus is frozen would make provenance harder to reason about.

## Stage 0: Read-Only Preview

These queries are safe to run before any cleanup:

```cypher
MATCH (c:DocChunk)
RETURN c.doc_id AS doc_id, count(*) AS chunks
ORDER BY doc_id;
```

```cypher
MATCH (c:DocChunk)
WHERE c.doc_id IN [
  'ema_gmp_annex11',
  'ema_gmp_annex_11',
  'ich_q1_draft2025',
  'ich_q1_draft_2025'
]
RETURN c.doc_id AS doc_id, count(*) AS chunks
ORDER BY doc_id;
```

```cypher
MATCH (c:DocChunk)-[r:FROM_DOCUMENT]->(d:Document)
RETURN count(r) AS reverse_edges;
```

## Stage 1: Freeze Canonical JSON Outside Neo4j

Before graph changes:

1. Normalize canonical document IDs in the chunking pipeline.
2. Rebuild affected enriched JSON into a staging directory.
3. Produce a final chunk allowlist and compare old versus staged counts.
4. Rebuild FAISS from the approved canonical JSON.
5. Record exact models, scripts, and counts in `data/corpus_manifest_2026-06.json`.

## Stage 2: Preferred Graph Rebuild

Preferred method: rebuild `Document`, `DocChunk`, `TableChunk`, and document-structure edges from the approved canonical JSON, then verify counts before switching the formal experiment configuration to the rebuilt graph.

This is intentionally not expressed as a one-command live replacement. The exact import command and backup procedure should be reviewed after the staged JSON files exist.

## Stage 3: Destructive Operations Requiring Explicit Confirmation

The following categories require a separate user confirmation immediately before execution:

```cypher
MATCH (c:DocChunk)
WHERE NOT c.chunk_id IN $canonical_chunk_ids
DETACH DELETE c;
```

```cypher
MATCH (:DocChunk)-[r:FROM_DOCUMENT]->(:Document)
DELETE r;
```

Any index drop, constraint drop, live-database replacement, or large JSON/FAISS artifact replacement also requires confirmation.

## Historical Script Warning

`fix_enriched_chunks.py` is not suitable for automatic execution during this upgrade. It writes enriched JSON in place and can run `DETACH DELETE` against Neo4j. It may remain useful as a reference, but the new rebuild should use a staged directory and an explicit approval checkpoint.

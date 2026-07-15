# Enrichment QA To-Do

Date: 2026-06-10  
Scope: Audit `data/staging/enrichment_full_2026-06-v1/` before any corpus freeze, index rebuild, or Neo4j update.

## Goal

Decide whether the full local enrichment output is reliable enough to become the frozen experiment corpus for retrieval ablation and paper results.

## To-Do

1. Check artifact completeness.
   - Expect 32 enriched document files.
   - Expect 2478 enriched chunks.
   - Expect all enriched chunks to contain `enrichment_meta`.
   - Expect excluded `arxiv_supply_chain` to remain absent.

2. Check enrichment coverage.
   - Count generated summaries against eligible chunks.
   - Count generated HyDE question sets and total questions.
   - Count C1/C2 split.
   - Count table-summary coverage.

3. Check source-grounding risks.
   - Inspect chunks marked irrelevant by summary, HyDE, or table-summary logic.
   - Inspect unsupported named-reference filters.
   - Confirm generated questions do not cite unsupported ICH/FDA/WHO/EMA documents.

4. Sample content quality.
   - Review examples from long chunks, short chunks, and table-heavy documents.
   - Include examples from ICH Q3D, Q3C, Q7, WHO EML, and WHO Stability.
   - Check whether summaries and questions are specific rather than generic.

5. Inspect table-summary gaps.
   - Locate the one table row without a generated summary.
   - Decide whether it is harmless, empty, malformed, or needs remediation.

6. Produce a written audit report.
   - Save report to `docs/enrichment_quality_audit_2026-06-10.md`.
   - Include pass/fail checks, risk notes, sample findings, and recommendation.

## Exit Criteria

The enrichment can move toward corpus freeze only if:

- Artifact counts match the manifest.
- No excluded documents appear.
- Table-summary coverage remains near complete.
- Spot checks show no systematic hallucination or wrong-document attribution.
- Any remaining issues are small enough to handle during indexing or manual evaluation.


# Qwen3.6-27B Server Pilot Quality Review

Date: 2026-06-11

## Run Summary

- Source archive: `pilot_qwen36_27b_result.tar.gz`
- Extracted analysis path: `artifacts/pilot_qwen36_27b_result_20260611/`
- Model endpoint used on server: `http://192.168.10.109:8051/v1`
- Model id: `Qwen/Qwen3.6-27B`
- Pilot documents: 13
- Pilot chunks: 156
- Pilot tables: 45
- New LLM calls: 245
- Canonical artifacts replaced: false
- Server stderr: only `nohup: ignoring input`, no runtime error.

Note: the run report contains `"backend": "deepseek"` inside `runtime_quality.llm`.
This is a local code label for the non-Ollama API path, not evidence that the
DeepSeek server was called. The model field correctly records `Qwen/Qwen3.6-27B`.

## Coverage

From `_pilot_run_report.json`:

- Summary eligible chunks: 59
- Summary generated chunks: 58
- Summary irrelevant chunks: 1
- HyDE eligible chunks: 144
- HyDE generated chunks: 134
- HyDE questions generated: 266
- HyDE irrelevant chunks: 5
- HyDE empty outputs: 4
- C1 chunks: 107
- C2 chunks: 37
- Unsupported named-reference questions filtered: 3
- Table summary eligible/generated: 47/47

Local file scan:

- Enriched files: 13
- Chunks scanned: 156
- Chunks with summaries: 58
- Chunks with HyDE questions: 134
- HyDE questions found: 266
- Table summaries found in table files: 45
- Chinese/CJK fragments in generated summaries/questions: 0
- Duplicate HyDE questions: 0
- Very short questions: 0
- Malformed question not ending in `?`: 1

## Comparison With Local Qwen2.5 Full Enrichment

Matched the same 156 chunk ids against `data/staging/enrichment_full_2026-06-v1`.

| Metric | Local qwen2.5 matched chunks | Server Qwen3.6 pilot |
| --- | ---: | ---: |
| Summary chunks | 57 | 58 |
| HyDE chunks | 141 | 134 |
| HyDE questions | 278 | 266 |
| CJK fragments in generated text | 1 | 0 |
| Malformed/non-ASCII question ending issues | 2 | 1 |
| Duplicate questions | 0 | 0 |
| Median HyDE question length | 184.5 chars | 223.5 chars |
| Median summary length | 630 chars | 793.5 chars |

Preliminary interpretation: Qwen3.6 produces cleaner English and richer
questions/summaries than local qwen2.5, but it is also more willing to expand
from regulatory requirements into broader supply-chain strategy language.

## Observed Quality Strengths

- No Chinese fragments appeared in generated summaries or HyDE questions.
- Summaries are more detailed and usually more compliance-oriented than qwen2.5.
- Questions are self-contained and generally stronger for retrieval than the
  shorter qwen2.5 questions.
- Table summaries are complete for the pilot table set.
- No duplicate generated HyDE questions were found.

## Observed Issues

1. One malformed HyDE question was generated for an OCR-noisy WHO EML chunk:

   - Chunk: `who_eml_2023_C0019_24addf45`
   - Source heading: `WHO Model List of Essential Medicines 每 23rd List (2023)`
   - Source contains OCR noise such as `桶`, `OModer`, `Essertial Meaicines`,
     `zSrd List (z0zS)`.
   - Generated question:
     `Which specific antibiotic product, formulation, and strengths are identified as the first-choice essential medicine for high`

   This is primarily a source/chunk quality problem, but the enrichment parser
   should also filter malformed questions.

2. Some Qwen3.6 HyDE questions introduce broad mitigation language that is not
   directly stated in the source. Example from ICH Q7 computerized systems:

   `What contingency plans and dual-sourcing strategies should be established...`

   This behavior follows the current prompt, which explicitly includes
   "dual-sourcing, contingency, or compliance strategies" as an angle. If the
   paper emphasizes source-grounded regulatory RAG, this prompt should be
   tightened before the final full enrichment.

3. The API backend is labeled as `deepseek` in metadata and logs because
   `run_server_enrichment_pilot.py` maps all non-Ollama API calls to that
   backend label. This is confusing and should be renamed to `api` or
   `openai_compatible`.

## Recommendation

Do not replace the canonical local qwen2.5 enrichment yet.

Recommended next steps:

1. Run the DeepSeek-V4-Flash pilot with the same current prompt and same pilot
   sample so the model comparison is fair.
2. Compare Qwen3.6 vs DeepSeek on:
   - malformed output count,
   - source-grounding,
   - regulatory specificity,
   - retrieval-oriented usefulness,
   - tendency to over-generalize supply-chain implications.
3. After model comparison, make a small enrichment-code update:
   - rename API backend metadata label,
   - filter malformed HyDE questions that do not end with `?`,
   - filter CJK-containing generated questions,
   - consider a v4 HyDE prompt that replaces broad "dual-sourcing" language
     with stricter source-grounded risk/compliance questions.
4. Re-run the winning model on the pilot after the guardrails, then launch the
   full enrichment only after the pilot passes.

# DeepSeek-V4-Flash vs Qwen3.6-27B Pilot Quality Review

Date: 2026-06-11

## Artifacts

- DeepSeek archive: `pilot_deepseek_v4_flash_result.tar.gz`
- DeepSeek extracted path: `artifacts/pilot_deepseek_v4_flash_result_20260611/`
- Qwen archive: `pilot_qwen36_27b_result.tar.gz`
- Qwen extracted path: `artifacts/pilot_qwen36_27b_result_20260611/`

Both pilots used the same 13-document, 156-chunk sample and the same prompt
versions:

- Summary: `v2_source_grounded`
- HyDE: `v3_doc_meta_filter`
- Table summary: `v3_sha256_source_grounded`

## Run Status

DeepSeek completed successfully.

- Report status: `completed_server_enrichment_pilot`
- Model: `deepseek-v4-flash`
- Input manifest timestamp: `2026-06-11T10:27:32`
- Report timestamp: `2026-06-11T10:32:33`
- Approximate active runtime: about 5 minutes
- Server stderr: only `nohup: ignoring input`
- Canonical artifacts replaced: false

## Quantitative Comparison

| Metric | Local qwen2.5 matched sample | Qwen3.6-27B pilot | DeepSeek-V4-Flash pilot |
| --- | ---: | ---: | ---: |
| Pilot chunks | 156 | 156 | 156 |
| Summary chunks | 57 | 58 | 56 |
| HyDE chunks | 141 | 134 | 143 |
| HyDE questions | 278 | 266 | 274 |
| Table summaries found | n/a | 45 | 45 |
| CJK fragments in generated text | 1 | 0 | 0 |
| Malformed/non-question outputs | 2 | 1 | 0 |
| Duplicate questions | 0 | 0 | 0 |
| Median HyDE question length | 184.5 chars | 223.5 chars | 327.5 chars |
| Mean HyDE question length | 187.5 chars | 222.4 chars | 328.2 chars |
| Median summary length | 630 chars | 793.5 chars | 720 chars |
| Questions longer than 350 chars | 1 | 2 | 104 |

## Over-Generalization Signals

The current HyDE v3 prompt explicitly asks models to consider supply-chain
disruption, affected entities, mitigation, and regulatory consequences. Under
this prompt, DeepSeek follows the requested style more aggressively than Qwen3.6.

Term frequency in generated HyDE questions:

| Term | Qwen3.6-27B | DeepSeek-V4-Flash |
| --- | ---: | ---: |
| `dual-sourcing` | 10 / 266 (3.8%) | 58 / 274 (21.2%) |
| `contingency` | 14 / 266 (5.3%) | 49 / 274 (17.9%) |
| `import alert` | 0 / 266 (0.0%) | 69 / 274 (25.2%) |
| `production halt` | 1 / 266 (0.4%) | 107 / 274 (39.1%) |
| `recall` | 1 / 266 (0.4%) | 20 / 274 (7.3%) |
| `supplier` | 13 / 266 (4.9%) | 65 / 274 (23.7%) |
| `supply chain disruption` | 19 / 266 (7.1%) | 134 / 274 (48.9%) |
| `regulatory enforcement` | 4 / 266 (1.5%) | 17 / 274 (6.2%) |
| `enforcement action` | 6 / 266 (2.3%) | 21 / 274 (7.7%) |

Interpretation: DeepSeek is more stable in format, but it has a stronger
tendency to turn regulatory excerpts into high-consequence supply-chain risk
scenarios. This may help recall in a broad retrieval setting, but it is risky
for a source-grounded regulatory RAG claim unless the prompt is tightened.

## Qualitative Findings

### DeepSeek Strengths

- Best output formatting among the three tested models.
- No CJK fragments, no malformed questions, no duplicates.
- Higher HyDE chunk coverage than Qwen3.6.
- Table summaries completed for the full pilot table set.
- Strong ability to preserve regulatory details in summaries.

### DeepSeek Risks

- Generates very long HyDE questions; 38.0% exceed 350 characters.
- Frequently injects high-consequence regulatory outcomes such as import alert,
  production halt, recall, or enforcement action even when the source excerpt
  only states a general quality requirement.
- Often adds mitigation concepts such as dual-sourcing or contingency planning
  because the current prompt invites this angle.
- For WHO EML medicine-list chunks, it can infer supply-chain details such as
  sulfate sourcing or vial production capacity that are not directly stated.

### Qwen3.6 Strengths

- Cleaner than local qwen2.5, with no CJK fragments in the pilot.
- More concise than DeepSeek.
- Better balance between regulatory specificity and retrieval usefulness.
- Longer and richer than local qwen2.5 without becoming as expansive as
  DeepSeek.

### Qwen3.6 Risks

- Produced one malformed/truncated HyDE question on an OCR-noisy WHO EML chunk.
- Generated fewer HyDE chunks than DeepSeek in this pilot.
- Some questions are too generic compared with DeepSeek's more detailed outputs.

## Current Recommendation

Do not launch a full canonical enrichment with either server model yet.

The best next step is to update enrichment guardrails before choosing the final
model:

1. Rename the API backend metadata label from `deepseek` to `api` or
   `openai_compatible` so Qwen API runs are not mislabeled.
2. Filter malformed HyDE questions:
   - must end with `?`,
   - must not contain CJK characters,
   - should have a practical length cap,
   - should be discarded if it is obviously truncated.
3. Tighten the HyDE prompt to v4:
   - remove broad "dual-sourcing" and "contingency" as default angles,
   - require regulatory consequence terms only when directly supported by the
     excerpt or provided context,
   - prefer "compliance/risk question answerable from this excerpt" over
     speculative supply-chain scenarios.
4. Re-run the same pilot for Qwen3.6 and DeepSeek with the v4 prompt.

Preliminary model preference:

- If using the current v3 prompt: Qwen3.6 is safer because it is less
  over-expansive.
- If we tighten the v4 prompt successfully: DeepSeek may become the better
  candidate because its formatting discipline and coverage are stronger.

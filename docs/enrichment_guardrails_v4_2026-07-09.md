# Enrichment Guardrails v4

Date: 2026-07-09

## Purpose

The Qwen3.6 and DeepSeek pilot comparison showed that stronger server models
produce cleaner text than local qwen2.5, but the HyDE v3 prompt allowed too much
speculative supply-chain expansion. This update tightens the enrichment step
before launching another model pilot.

## Code Changes

- `pharma_doc_pipeline/step_03_enrich.py`
  - Upgraded HyDE prompt version from `v3_doc_meta_filter` to
    `v4_source_grounded_guarded`.
  - Replaced broad mitigation prompts with stricter source-grounded retrieval
    questions.
  - Added explicit instructions not to introduce terms such as import alert,
    recall, production halt, dual-sourcing, contingency plan, CMO, or
    single-source unless directly supported.
  - Added HyDE output filters:
    - malformed or truncated question filter,
    - CJK fragment filter,
    - over-length question filter,
    - existing unsupported named-reference filter retained.
  - Added runtime counters and per-chunk metadata for the new filters.

- `run_server_enrichment_pilot.py`
  - Changed OpenAI-compatible API runs to record `settings.llm.backend = "api"`
    instead of the misleading old `deepseek` label.

- `make_server_enrichment_bundle.ps1`
  - Generates both `.zip` and `.tar.gz` server bundles.
  - Linux servers should prefer `.tar.gz` to avoid the previous unzip directory
    permission issue.

## Validation

- Python syntax check passed for:
  - `pharma_doc_pipeline/step_03_enrich.py`
  - `run_server_enrichment_pilot.py`
  - `pharma_doc_pipeline/config.py`
- `run_server_enrichment_pilot.py --help` works.
- Local filter self-test confirms:
  - valid English question is accepted,
  - truncated question is rejected as malformed,
  - CJK-containing question is rejected,
  - over-length question is rejected.

## New Server Bundle

- Bundle directory:
  `artifacts/server_enrichment_pilot_20260709_101647/`
- Preferred Linux archive:
  `artifacts/server_enrichment_pilot_20260709_101647.tar.gz`
- Zip fallback:
  `artifacts/server_enrichment_pilot_20260709_101647.zip`

## Next Server Runs

Run both models again on the same pilot sample with HyDE v4.

Qwen3.6:

```bash
nohup python3 -u run_server_enrichment_pilot.py \
  --backend api \
  --api-base-url "http://192.168.10.109:8051/v1" \
  --api-key "EMPTY" \
  --model "Qwen/Qwen3.6-27B" \
  --temperature 0.1 \
  --timeout 600 \
  --output data/staging/pilot_qwen36_27b_v4 \
  > qwen36_v4_pilot.out 2> qwen36_v4_pilot.err &
```

DeepSeek-V4-Flash:

```bash
nohup python3 -u run_server_enrichment_pilot.py \
  --backend api \
  --api-base-url "http://192.168.10.135:8002/v1" \
  --api-key "EMPTY" \
  --model "deepseek-v4-flash" \
  --temperature 0.1 \
  --timeout 600 \
  --output data/staging/pilot_deepseek_v4_flash_v4 \
  > deepseek_v4_pilot.out 2> deepseek_v4_pilot.err &
```

After completion, return the packed outputs to the local project for another
quality comparison.

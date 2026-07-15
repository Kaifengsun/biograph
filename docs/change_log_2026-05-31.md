Change Log - 2026-05-31

Overview
- Added an entity-anchored evaluation set and selection flag for ablation runs.
- Switched LLM configs to DeepSeek v4-pro (GraphRAG/agents) and Moonshot Kimi (doc enrichment, literature).
- Strengthened DocChunk -> entity MENTIONS linking with alias normalization and broader labels.
- Removed hard-coded API keys; all keys now sourced from environment variables.

Files Modified
- pharma_doc_pipeline/config.py
  - Default LLM backend set to moonshot.
  - API base URL set to https://api.moonshot.cn/v1.
  - API key now read from MOONSHOT_API_KEY; model from MOONSHOT_MODEL (default kimi-k2.6).

- pharma_doc_pipeline/main.py
  - Added CLI choices for moonshot and openai backends.

- pharma_graphrag/config.py
  - DeepSeek model set to deepseek-v4-pro.
  - API key now read from DEEPSEEK_API_KEY (no hard-coded key).

- pharma_doc_pipeline/step_04_vectorize.py
  - Expanded MENTIONS linking to include Regulation, ShortageEvent, Country, RecallEvent.
  - Added alias normalization (parentheses split, colon split), length thresholds, and word-boundary matching for Latin text.
  - Added missing re import.

- retrieval_ablation.py
  - Added --eval to select evaluation query set.

- process_literature.py
  - Switched to Moonshot Kimi via MOONSHOT_API_KEY, MOONSHOT_API_BASE_URL, MOONSHOT_MODEL.

- summarize_literature.py
  - Switched to Moonshot Kimi via MOONSHOT_API_KEY, MOONSHOT_API_BASE_URL, MOONSHOT_MODEL.

New Files
- data/eval_queries_entity_anchor.json
  - 40 entity-anchored queries (EMA GMP, FDA cGMP, ICH Q9, ICH Q10) with verified chunk IDs.

Notes
- No API keys are stored in source code. Use environment variables:
  - MOONSHOT_API_KEY, MOONSHOT_API_BASE_URL, MOONSHOT_MODEL
  - DEEPSEEK_API_KEY
- Vectorization remains local with tencent/Youtu-Embedding as requested.

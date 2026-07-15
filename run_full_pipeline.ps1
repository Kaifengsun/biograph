# ============================================================
# PharmGraphRAG 完整重建流程
# ============================================================
# 步骤:
#   1. Neo_StandardExtracter 切分全部 33 个文档 → *_rag.json
#   2. 格式适配器            → data/chunks/*_enriched.json
#   3. step_04_vectorize     → data/vectors/pharma_docs.faiss
# ============================================================

$ROOT = "d:\Projects\financial knowledge graph"
$NEO  = "$ROOT\Neo_StandardExtracter"

# --- API 配置 ---
if (-not $env:OPENAI_API_KEY) { throw "OPENAI_API_KEY is required. Set it in the user environment before running the pipeline." }
$env:OPENAI_BASE_URL  = "https://api.deepseek.com/v1"
$env:OPENAI_MODEL     = "deepseek-chat"
$env:LLM_MAX_CONCURRENT = "2"
$env:HF_ENDPOINT      = "https://hf-mirror.com"

Write-Host "============================================================"
Write-Host " PharmGraphRAG Pipeline"
Write-Host "============================================================"

# ──────────────────────────────────────────────
# 步骤 1: Neo_StandardExtracter — 切分全部文档
# ──────────────────────────────────────────────
Write-Host "`n[Step 1] Running Neo_StandardExtracter on all 33 docs..."
Set-Location $NEO
python main.py --input "../data/markdown" --output "./output"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Neo_StandardExtracter failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
Write-Host "[Step 1] Done." -ForegroundColor Green

# ──────────────────────────────────────────────
# 步骤 2: 格式适配器 — RAGDocument → ChunkNode
# ──────────────────────────────────────────────
Write-Host "`n[Step 2] Converting RAG JSON to ChunkNode format..."
Set-Location $ROOT
python pharma_doc_pipeline\step_02b_adapt_neo_rag.py `
    --input "$NEO\output" `
    --output "data\chunks"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Format adapter failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 2
}
Write-Host "[Step 2] Done." -ForegroundColor Green

# ──────────────────────────────────────────────
# 步骤 3: 向量化 — 重建 FAISS 索引
# ──────────────────────────────────────────────
Write-Host "`n[Step 3] Vectorizing chunks and rebuilding FAISS index..."
Set-Location $ROOT
python -m pharma_doc_pipeline.step_04_vectorize
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Vectorization failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 3
}
Write-Host "[Step 3] Done." -ForegroundColor Green

Write-Host "`n============================================================"
Write-Host " All steps completed successfully!"
Write-Host " Next: start Neo4j Docker and run import_neo4j_data.py"
Write-Host "============================================================"

# ============================================================
# pipeline 完成后的一键后处理脚本
# 当 Neo_StandardExtracter 跑完 33 个文档后，运行此脚本完成：
#   Step A: 格式适配器  →  data/chunks/*_enriched.json
#   Step B: 向量化      →  data/vectors/pharma_docs.faiss
#   Step C: 评估        →  data/eval_results.json（FAISS 基线）
#   Step D: 提示完成
# ============================================================

$ROOT    = "d:\Projects\financial knowledge graph"
$NEO_OUT = "$ROOT\Neo_StandardExtracter\output"
$CHUNKS  = "$ROOT\data\chunks"
$LOG     = "$ROOT\postprocess.log"

$env:HF_ENDPOINT = "https://hf-mirror.com"

function Write-Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "$ts | $msg" | Tee-Object -FilePath $LOG -Append
}

Write-Log "=========================================="
Write-Log "Post-pipeline processing started"
Write-Log "=========================================="

# ── 检查 pipeline 是否完成（期望 33 个 _rag.json）──
$ragFiles = Get-ChildItem $NEO_OUT -Recurse -Filter "*_rag.json" | Measure-Object
Write-Log "Found $($ragFiles.Count) _rag.json files"
if ($ragFiles.Count -lt 33) {
    Write-Log "[WARN] Pipeline may not be fully complete (only $($ragFiles.Count)/33)"
    Write-Log "[WARN] Proceeding anyway with available files..."
}

# ── Step A: 格式适配器 ──
Write-Log ""
Write-Log "[Step A] Format adapter: RAGDocument -> ChunkNode..."
Set-Location $ROOT
python pharma_doc_pipeline\step_02b_adapt_neo_rag.py `
    --input $NEO_OUT `
    --output $CHUNKS 2>&1 | Tee-Object -FilePath $LOG -Append
if ($LASTEXITCODE -ne 0) {
    Write-Log "[ERROR] Format adapter failed (exit $LASTEXITCODE)"
    exit 1
}
$chunkCount = (Get-ChildItem $CHUNKS -Filter "*_enriched.json" | Measure-Object).Count
Write-Log "[Step A] Done. $chunkCount enriched files created."

# ── Step B: 向量化 ──
Write-Log ""
Write-Log "[Step B] Vectorizing with Youtu-Embedding..."
python -m pharma_doc_pipeline.step_04_vectorize 2>&1 | Tee-Object -FilePath $LOG -Append
if ($LASTEXITCODE -ne 0) {
    Write-Log "[ERROR] Vectorization failed (exit $LASTEXITCODE)"
    exit 2
}
Write-Log "[Step B] Done. FAISS index built."

# ── Step C: 检索评估（FAISS 基线）──
Write-Log ""
Write-Log "[Step C] Running retrieval evaluation (FAISS baseline)..."
python eval_retrieval.py `
    --method faiss `
    --k 1 5 10 20 `
    --output data/eval_results_faiss.json 2>&1 | Tee-Object -FilePath $LOG -Append
Write-Log "[Step C] Done."

# ── 完成 ──
Write-Log ""
Write-Log "=========================================="
Write-Log "Post-processing complete!"
Write-Log ""
Write-Log "Next manual steps:"
Write-Log "  1. docker start pharma-neo4j"
Write-Log "  2. python import_neo4j_data.py   (update DocChunk nodes)"
Write-Log "  3. python run_simulation.py --event all  (WITH GraphRAG)"
Write-Log "  4. python eval_retrieval.py --method graphrag"
Write-Log "=========================================="

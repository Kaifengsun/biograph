import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const round1Path = path.join(root, "data/eval/bm25_enrichment_heldout_reviewed_round1_2026-07-15.json");
const revisionPackPath = path.join(root, "data/eval/bm25_enrichment_heldout_revision_round_2026-07-15.json");
const workbookPath = process.env.CONFIRMED_REVISION_WORKBOOK || "D:/Downloads/BM25与语料富化消融_8题修订二次确认表_2026-07-15_已确认.xlsx";
const corpusDir = path.join(root, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const outputPath = path.join(root, "data/eval/bm25_enrichment_heldout_frozen_pending_method_lock_2026-07-15.json");
const priorPacks = [path.join(root, "data/eval/three_path_evaluation_frozen_2026-07-15.json"), path.join(root, "data/eval/adaptive_text_first_heldout_frozen_run_ready_2026-07-15.json")];

const digest = async (filePath) => crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
const splitIds = (value) => String(value || "").split(/[;\n]+/).map((item) => item.trim()).filter(Boolean);
async function directoryFingerprint(dirPath, suffix) {
  const files = (await fs.readdir(dirPath)).filter((name) => name.endsWith(suffix)).sort();
  const entries = [];
  for (const name of files) entries.push({ name, sha256: await digest(path.join(dirPath, name)) });
  return { file_count: entries.length, sha256: crypto.createHash("sha256").update(JSON.stringify(entries)).digest("hex") };
}

try { await fs.access(outputPath); throw new Error(`refusing to overwrite frozen set: ${outputPath}`); } catch (error) { if (error?.code !== "ENOENT") throw error; }
const round1 = JSON.parse(await fs.readFile(round1Path, "utf8"));
const revisionPack = JSON.parse(await fs.readFile(revisionPackPath, "utf8"));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const rows = workbook.worksheets.getItem("Revision Queue").getRange("A5:H12").values;
const revisionSource = new Map(revisionPack.revisions.map((row) => [row.revision_id, row]));
const confirmed = new Map();
for (const row of rows) {
  const revisionId = String(row[0] || "").trim();
  if (!revisionId) continue;
  if (!revisionSource.has(revisionId)) throw new Error(`unknown revision ID: ${revisionId}`);
  const status = String(row[5] || "").trim();
  if (status !== "Confirmed") throw new Error(`revision is not Confirmed: ${revisionId} (${status})`);
  const finalQuestion = String(row[6] || "").trim();
  if (!finalQuestion) throw new Error(`confirmed revision has no final question: ${revisionId}`);
  confirmed.set(revisionId, { finalQuestion, note: String(row[7] || "").trim() });
}
if (confirmed.size !== revisionPack.revisions.length) throw new Error(`expected ${revisionPack.revisions.length} confirmations, found ${confirmed.size}`);

const chunkIds = new Set();
for (const fileName of (await fs.readdir(corpusDir)).filter((name) => name.endsWith("_enriched.json"))) {
  for (const row of JSON.parse(await fs.readFile(path.join(corpusDir, fileName), "utf8"))) if (row.chunk_id) chunkIds.add(String(row.chunk_id));
}
const priorGold = new Set();
for (const filePath of priorPacks) for (const row of (JSON.parse(await fs.readFile(filePath, "utf8")).queries || [])) for (const id of row.gold_evidence_chunk_ids || []) priorGold.add(id);
const revisionBySourceId = new Map(revisionPack.revisions.map((row) => [row.source_review_id, row]));
const queries = round1.decisions.filter((row) => row.review_status !== "Exclude").map((row) => {
  if (row.review_status === "Confirmed") return {
    annotation_id: row.review_id, query_slice: row.query_slice, query: row.original_question,
    gold_evidence_chunk_ids: row.final_gold_evidence_chunk_ids, review_status: "reviewed", eligible_for_formal_evaluation: true,
  };
  const revision = revisionBySourceId.get(row.review_id);
  if (!revision) throw new Error(`missing revision for ${row.review_id}`);
  const decision = confirmed.get(revision.revision_id);
  return {
    annotation_id: row.review_id, query_slice: row.query_slice, query: decision.finalQuestion,
    gold_evidence_chunk_ids: row.final_gold_evidence_chunk_ids, review_status: "reviewed", eligible_for_formal_evaluation: true,
    revision_history: [{ revision_id: revision.revision_id, original_question: row.original_question, revised_question: decision.finalQuestion, round1_reviewer_note: row.reviewer_note, round2_reviewer_note: decision.note }],
  };
});
const expectedSlices = { single_clause: 10, table: 8, document_structure: 6, cross_document: 6 };
const actualSlices = Object.fromEntries(Object.keys(expectedSlices).map((slice) => [slice, queries.filter((row) => row.query_slice === slice).length]));
if (queries.length !== 30 || new Set(queries.map((row) => row.annotation_id)).size !== 30) throw new Error("frozen set must contain exactly 30 unique questions");
if (JSON.stringify(expectedSlices) !== JSON.stringify(actualSlices)) throw new Error(`slice mismatch: ${JSON.stringify(actualSlices)}`);
for (const row of queries) {
  if (!row.query.trim() || !row.gold_evidence_chunk_ids.length) throw new Error(`incomplete frozen row: ${row.annotation_id}`);
  for (const id of row.gold_evidence_chunk_ids) {
    if (!chunkIds.has(id)) throw new Error(`unknown gold chunk ${id}`);
    if (priorGold.has(id)) throw new Error(`prior-gold overlap ${id}`);
  }
}
const frozen = {
  schema_version: "1.0", status: "frozen_human_reviewed_heldout_pending_method_lock", formal_metrics_ready: false, retrieval_execution_prohibited: true,
  frozen_at_utc: new Date().toISOString(), freeze_requirements: { exact_total: 30, exact_slice_counts: expectedSlices, prior_gold_overlap_count: 0 },
  review_ledger: { total_rows: 30, eligible_rows: 30, by_status: { reviewed: 30 }, by_slice: actualSlices }, queries,
  provenance: {
    round1_pack: round1Path, round1_pack_sha256: await digest(round1Path), revision_pack: revisionPackPath, revision_pack_sha256: await digest(revisionPackPath),
    confirmed_revision_workbook: workbookPath, confirmed_revision_workbook_sha256: await digest(workbookPath), corpus: corpusDir, corpus_fingerprint: await directoryFingerprint(corpusDir, "_enriched.json"),
    prior_frozen_packs: await Promise.all(priorPacks.map(async (filePath) => ({ file: filePath, sha256: await digest(filePath) }))),
  },
};
frozen.query_content_sha256 = crypto.createHash("sha256").update(JSON.stringify(queries)).digest("hex");
await fs.writeFile(outputPath, JSON.stringify(frozen, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, status: frozen.status, review_ledger: frozen.review_ledger, query_content_sha256: frozen.query_content_sha256 }, null, 2));

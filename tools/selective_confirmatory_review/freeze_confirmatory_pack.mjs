import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const payloadPath = process.env.REVIEW_PAYLOAD || path.join(root, "outputs/selective_source_chunk_reranker_confirmatory_review_2026-07-16/review_payload.json");
const round1WorkbookPath = process.env.ROUND1_WORKBOOK || "D:/Downloads/选择性重排_30题全新确认集_带原文盲审表_2026-07-16_已审核.xlsx";
const round2WorkbookPath = process.env.ROUND2_WORKBOOK || "D:/Downloads/选择性重排_6题修订二次确认表_2026-07-16_已确认.xlsx";
const corpusDir = process.env.FROZEN_CORPUS || path.join(root, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const outputPath = process.env.FROZEN_OUTPUT || path.join(root, "data/eval/selective_reranker_confirmatory_frozen_pending_2026-07-16.json");

const sha256 = async (filePath) => crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
const splitIds = (value) => String(value || "").split(/[;,；，\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean);

async function refuseOverwrite(filePath) {
  try {
    await fs.access(filePath);
    throw new Error(`refusing to overwrite frozen pack: ${filePath}`);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function directoryFingerprint(dirPath) {
  const names = (await fs.readdir(dirPath)).filter((name) => name.endsWith("_enriched.json") || name.endsWith("_tables.json")).sort();
  const files = [];
  for (const name of names) files.push({ name, sha256: await sha256(path.join(dirPath, name)) });
  return { file_count: files.length, sha256: crypto.createHash("sha256").update(JSON.stringify(files)).digest("hex") };
}

await refuseOverwrite(outputPath);
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const payloadById = new Map(payload.questions.map((question) => [question.annotation_id, question]));

const round1Workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(round1WorkbookPath));
const round1Rows = round1Workbook.worksheets.getItem("Review Queue").getRange("A2:F31").values;
const round1 = new Map();
for (const row of round1Rows) {
  const reviewId = String(row[0] || "").trim();
  if (!reviewId) continue;
  if (!payloadById.has(reviewId)) throw new Error(`unknown first-round Review ID: ${reviewId}`);
  const status = String(row[3] || "").trim();
  if (!new Set(["Confirmed", "Revise", "Exclude"]).has(status)) throw new Error(`invalid first-round status: ${reviewId} ${status}`);
  round1.set(reviewId, {
    querySlice: String(row[1] || "").trim(),
    question: String(row[2] || "").trim(),
    status,
    passageIds: splitIds(row[4]),
    reviewerNote: String(row[5] || "").trim(),
  });
}
if (round1.size !== 30) throw new Error(`expected 30 first-round rows, found ${round1.size}`);

const round2Workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(round2WorkbookPath));
const round2Rows = round2Workbook.worksheets.getItem("Review Queue").getRange("A2:H7").values;
const round2 = new Map();
for (const row of round2Rows) {
  const revisionId = String(row[0] || "").trim();
  if (!revisionId) continue;
  const status = String(row[5] || "").trim();
  if (status !== "Confirmed") throw new Error(`revision is not Confirmed: ${revisionId} (${status})`);
  const sourceId = revisionId.replace(/__R1$/, "");
  if (!payloadById.has(sourceId)) throw new Error(`unknown revised source ID: ${sourceId}`);
  const proposedIds = splitIds(row[4]);
  if (!proposedIds.length) throw new Error(`confirmed revision lacks Gold passages: ${revisionId}`);
  round2.set(sourceId, {
    revisionId,
    originalQuestion: String(row[2] || "").trim(),
    revisedQuestion: String(row[3] || "").trim(),
    passageIds: proposedIds,
    revisionRationale: String(row[6] || "").trim(),
    reviewerNote: String(row[7] || "").trim(),
  });
}
if (round2.size !== 6) throw new Error(`expected 6 confirmed revisions, found ${round2.size}`);

const corpusChunkIds = new Set();
for (const name of (await fs.readdir(corpusDir)).filter((item) => item.endsWith("_enriched.json")).sort()) {
  const rows = JSON.parse(await fs.readFile(path.join(corpusDir, name), "utf8"));
  for (const row of rows) if (row.chunk_id) corpusChunkIds.add(String(row.chunk_id));
}
if (corpusChunkIds.size !== 2478) throw new Error(`expected 2478 source chunks, found ${corpusChunkIds.size}`);

function chunkIdsFor(question, passageIds) {
  const passageById = new Map(question.passages.map((passage) => [passage.passage_id, passage]));
  return passageIds.map((passageId) => {
    const passage = passageById.get(passageId);
    if (!passage) throw new Error(`${question.annotation_id}: invalid Passage ID ${passageId}`);
    if (!corpusChunkIds.has(passage.chunk_id)) throw new Error(`${question.annotation_id}: unknown corpus chunk ${passage.chunk_id}`);
    return passage.chunk_id;
  });
}

const queries = [];
for (const source of payload.questions) {
  const decision = round1.get(source.annotation_id);
  if (!decision) throw new Error(`missing first-round decision: ${source.annotation_id}`);
  if (decision.querySlice !== source.query_slice || decision.question !== source.query) throw new Error(`first-round row changed unexpectedly: ${source.annotation_id}`);
  if (decision.status === "Exclude") continue;
  if (decision.status === "Confirmed") {
    if (!decision.passageIds.length) throw new Error(`confirmed row lacks Gold passages: ${source.annotation_id}`);
    queries.push({
      annotation_id: source.annotation_id,
      query_slice: source.query_slice,
      query: source.query,
      gold_evidence_chunk_ids: chunkIdsFor(source, decision.passageIds),
      review_status: "reviewed",
      eligible_for_formal_evaluation: true,
      human_review: { round1_status: "Confirmed", gold_passage_ids: decision.passageIds, reviewer_note: decision.reviewerNote },
    });
    continue;
  }
  const revision = round2.get(source.annotation_id);
  if (!revision) throw new Error(`missing confirmed revision: ${source.annotation_id}`);
  if (revision.originalQuestion !== source.query) throw new Error(`revision original question mismatch: ${source.annotation_id}`);
  queries.push({
    annotation_id: source.annotation_id,
    query_slice: source.query_slice,
    query: revision.revisedQuestion,
    gold_evidence_chunk_ids: chunkIdsFor(source, revision.passageIds),
    review_status: "reviewed",
    eligible_for_formal_evaluation: true,
    revision_history: [{
      revision_id: revision.revisionId,
      original_question: source.query,
      revised_question: revision.revisedQuestion,
      round1_reviewer_note: decision.reviewerNote,
      revision_rationale: revision.revisionRationale,
      round2_reviewer_note: revision.reviewerNote,
      gold_passage_ids: revision.passageIds,
    }],
  });
}

const expectedSlices = { single_clause: 10, table: 8, document_structure: 6, cross_document: 6 };
const actualSlices = Object.fromEntries(Object.keys(expectedSlices).map((slice) => [slice, queries.filter((row) => row.query_slice === slice).length]));
if (queries.length !== 30 || new Set(queries.map((row) => row.annotation_id)).size !== 30) throw new Error("frozen pack must contain 30 unique queries");
if (JSON.stringify(expectedSlices) !== JSON.stringify(actualSlices)) throw new Error(`slice mismatch: ${JSON.stringify(actualSlices)}`);
if (queries.some((row) => !row.query || !row.gold_evidence_chunk_ids.length)) throw new Error("incomplete frozen query");

const frozen = {
  schema_version: "1.0",
  status: "frozen_human_reviewed_confirmatory_pending_activation",
  confirmatory_for_source_chunk_reranker: true,
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  frozen_at_utc: new Date().toISOString(),
  freeze_requirements: { exact_total: 30, exact_slice_counts: expectedSlices, first_round_confirmed: 24, revised_then_confirmed: 6, excluded: 0 },
  review_ledger: { total_rows: 30, eligible_rows: 30, by_slice: actualSlices, by_resolution: { first_round_confirmed: 24, revised_then_confirmed: 6 } },
  queries,
  provenance: {
    review_payload: payloadPath,
    review_payload_sha256: await sha256(payloadPath),
    first_round_workbook: round1WorkbookPath,
    first_round_workbook_sha256: await sha256(round1WorkbookPath),
    second_round_workbook: round2WorkbookPath,
    second_round_workbook_sha256: await sha256(round2WorkbookPath),
    corpus: corpusDir,
    corpus_fingerprint: await directoryFingerprint(corpusDir),
    method_lock_declared_at_review: payload.method_lock,
    original_query_content_sha256_before_review: payload.query_content_sha256,
  },
};
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, JSON.stringify(frozen, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, status: frozen.status, review_ledger: frozen.review_ledger }, null, 2));

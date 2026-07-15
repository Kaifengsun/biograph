import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const inputPath = process.env.REVIEWED_WORKBOOK || "D:/Downloads/BM25与语料富化消融_30题带原文简化审核表_2026-07-15_已审核.xlsx";
const candidatePath = path.join(root, "data/eval/bm25_enrichment_heldout_review_candidates_2026-07-15.json");
const auditDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15/reviewed_audit");
const round1Path = path.join(root, "data/eval/bm25_enrichment_heldout_reviewed_round1_2026-07-15.json");
const revisionPath = path.join(root, "data/eval/bm25_enrichment_heldout_revision_round_2026-07-15.json");

function splitIds(value) {
  return String(value || "").split(/[;\n]+/).map((item) => item.trim()).filter(Boolean);
}
function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

const candidatePack = JSON.parse(await fs.readFile(candidatePath, "utf8"));
const inputBytes = await fs.readFile(inputPath);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const rows = workbook.worksheets.getItem("Review Queue").getRange("A5:J34").values;
const sourceById = new Map(candidatePack.queries.map((row) => [row.review_id, row]));
const allowed = new Set(["Confirmed", "Revise", "Exclude"]);
const errors = [];
const seen = new Set();
const decisions = [];

for (const row of rows) {
  const reviewId = String(row[0] || "").trim();
  if (!reviewId) continue;
  if (seen.has(reviewId)) errors.push(`${reviewId}: duplicate workbook row`);
  seen.add(reviewId);
  const source = sourceById.get(reviewId);
  if (!source) {
    errors.push(`${reviewId}: unknown review ID`);
    continue;
  }
  const status = String(row[4] || "").trim();
  const revisedQuestion = String(row[5] || "").trim();
  const finalGold = splitIds(row[6]);
  const reviewerNote = String(row[7] || "").trim();
  if (!allowed.has(status)) errors.push(`${reviewId}: unsupported or pending status ${status || "<empty>"}`);
  if (status === "Revise" && !revisedQuestion) errors.push(`${reviewId}: Revise requires a revised question`);
  if (status === "Revise" && !reviewerNote) errors.push(`${reviewId}: Revise requires a reviewer note`);
  if (["Confirmed", "Revise"].includes(status) && !finalGold.length) errors.push(`${reviewId}: accepted row requires final gold IDs`);
  const reviewedEvidence = new Set(source.evidence.map((item) => item.chunk_id));
  for (const id of finalGold) if (!reviewedEvidence.has(id)) errors.push(`${reviewId}: gold ID outside reviewed evidence ${id}`);
  decisions.push({
    review_id: reviewId,
    query_slice: source.query_slice,
    original_question: source.question,
    review_status: status,
    revised_question: revisedQuestion,
    final_gold_evidence_chunk_ids: finalGold,
    reviewer_note: reviewerNote,
    evidence: source.evidence,
  });
}
for (const id of sourceById.keys()) if (!seen.has(id)) errors.push(`${id}: missing workbook row`);
if (decisions.length !== 30) errors.push(`expected 30 decisions, found ${decisions.length}`);

const counts = Object.fromEntries(["Confirmed", "Revise", "Exclude"].map((status) => [status, decisions.filter((row) => row.review_status === status).length]));
const report = { status: errors.length ? "invalid" : "valid_requires_revision_confirmation", row_count: decisions.length, status_counts: counts, errors };
await fs.mkdir(auditDir, { recursive: true });
await fs.writeFile(path.join(auditDir, "validation_report.json"), JSON.stringify(report, null, 2), "utf8");
if (errors.length) {
  console.error(JSON.stringify(report, null, 2));
  process.exit(1);
}

const round1 = {
  schema_version: "1.0",
  status: "human_reviewed_round1_pending_revision_confirmation",
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  reviewed_at_utc: new Date().toISOString(),
  review_ledger: { total: decisions.length, by_status: counts },
  decisions,
  provenance: {
    candidate_pack: candidatePath,
    candidate_pack_sha256: sha256(await fs.readFile(candidatePath)),
    reviewed_workbook: inputPath,
    reviewed_workbook_sha256: sha256(inputBytes),
  },
};
const revisions = decisions.filter((row) => row.review_status === "Revise").map((row) => ({
  revision_id: `${row.review_id}__R1`,
  source_review_id: row.review_id,
  query_slice: row.query_slice,
  original_question: row.original_question,
  proposed_revised_question: row.revised_question,
  gold_evidence_chunk_ids: row.final_gold_evidence_chunk_ids,
  round1_reviewer_note: row.reviewer_note,
  review_status: "Pending",
  final_revised_question: row.revised_question,
  round2_reviewer_note: "",
  evidence: row.evidence.filter((item) => row.final_gold_evidence_chunk_ids.includes(item.chunk_id)),
}));
const revisionPack = {
  schema_version: "1.0",
  status: "revision_confirmation_required",
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  created_at_utc: new Date().toISOString(),
  revision_count: revisions.length,
  revisions,
  provenance: { round1_pack: round1Path, reviewed_workbook: inputPath, reviewed_workbook_sha256: sha256(inputBytes) },
};
await fs.writeFile(round1Path, JSON.stringify(round1, null, 2), "utf8");
await fs.writeFile(revisionPath, JSON.stringify(revisionPack, null, 2), "utf8");
console.log(JSON.stringify({ status: report.status, status_counts: counts, round1Path, revisionPath, revision_ids: revisions.map((row) => row.revision_id) }, null, 2));

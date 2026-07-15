import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const packPath = process.env.HELDOUT_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_candidates_2026-07-15.json");
const workbookPath = process.env.REVIEWED_WORKBOOK || "D:/Downloads/adaptive_text_first_heldout_review_2026-07-15_reviewed.xlsx";
const auditDir = process.env.REVIEW_AUDIT_OUTPUT || path.join(projectRoot, "outputs/heldout_review_2026-07-15/reviewed_audit");
const outputPath = process.env.REVIEWED_PACK_OUTPUT || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_reviewed_round1_2026-07-15.json");

function splitIds(value) {
  return String(value || "").split(/[;\n]+/).map((item) => item.trim()).filter(Boolean);
}

function splitPath(value) {
  return String(value || "").split(/\s*(?:;|->|→|\n)\s*/).map((item) => item.trim()).filter(Boolean);
}

async function sha256(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

try {
  await fs.access(outputPath);
  throw new Error(`refusing to overwrite existing reviewed snapshot: ${outputPath}`);
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}

const validation = JSON.parse(await fs.readFile(path.join(auditDir, "validation_report.json"), "utf8"));
if (validation.errors.length) throw new Error(`review validation has ${validation.errors.length} errors`);
const pack = JSON.parse(await fs.readFile(packPath, "utf8"));
const queueAudit = JSON.parse(await fs.readFile(path.join(auditDir, "review_queue_values.json"), "utf8"));
const [headers, ...rawRows] = queueAudit.rows;
const index = Object.fromEntries(headers.map((header, position) => [header, position]));
const decisions = new Map(rawRows.filter((row) => row[index["Review ID"]]).map((row) => [String(row[index["Review ID"]]), {
  status: String(row[index.Status] || "Pending").trim(),
  gold: splitIds(row[index["Gold evidence chunk IDs"]]),
  path: splitPath(row[index["Accepted Graph Path Node IDs"]]),
  rationale: String(row[index["Reviewer Rationale"]] || "").trim(),
}]));

const queries = pack.queries.map((source) => {
  const decision = decisions.get(String(source.annotation_id));
  if (!decision) throw new Error(`missing decision: ${source.annotation_id}`);
  const row = { ...source, reviewer_rationale: decision.rationale };
  if (decision.status === "Confirmed") {
    row.gold_evidence_chunk_ids = decision.gold;
    row.accepted_graph_path_node_ids = decision.path;
    row.review_status = "reviewed";
    row.eligible_for_formal_evaluation = true;
  } else if (decision.status === "Revise") {
    row.gold_evidence_chunk_ids = decision.gold;
    row.accepted_graph_path_node_ids = decision.path;
    row.review_status = "needs_revision";
    row.eligible_for_formal_evaluation = false;
  } else if (decision.status === "Exclude") {
    row.gold_evidence_chunk_ids = [];
    row.accepted_graph_path_node_ids = [];
    row.review_status = "excluded";
    row.eligible_for_formal_evaluation = false;
  } else {
    row.review_status = "unreviewed";
    row.eligible_for_formal_evaluation = false;
  }
  return row;
});
const ledger = Object.fromEntries(["reviewed", "needs_revision", "excluded", "unreviewed"].map((status) => [
  status,
  queries.filter((row) => row.review_status === status).length,
]));
const result = {
  ...pack,
  status: "human_review_round1_applied_not_frozen",
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  review_ledger: ledger,
  queries,
  reviewer_workbook_application: {
    workbook: workbookPath,
    workbook_sha256: await sha256(workbookPath),
    source_pack: packPath,
    source_pack_sha256: await sha256(packPath),
    validation_report: path.join(auditDir, "validation_report.json"),
  },
};
await fs.writeFile(outputPath, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, review_ledger: ledger }, null, 2));

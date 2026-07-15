import fs from "node:fs/promises";
import path from "node:path";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const auditDir = process.env.REVIEW_AUDIT_OUTPUT || path.join(projectRoot, "outputs/heldout_review_2026-07-15/reviewed_audit");
const packPath = process.env.HELDOUT_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_candidates_2026-07-15.json");
const corpusDir = process.env.FROZEN_CORPUS || path.join(projectRoot, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const graphDir = process.env.FROZEN_GRAPH || path.join(projectRoot, "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda");

function splitIds(value) {
  return String(value || "").split(/[;\n]+/).map((item) => item.trim()).filter(Boolean);
}

function splitPath(value) {
  return String(value || "").split(/\s*(?:;|->|→|\n)\s*/).map((item) => item.trim()).filter(Boolean);
}

async function readJsonLines(filePath) {
  return (await fs.readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

const pack = JSON.parse(await fs.readFile(packPath, "utf8"));
const queueAudit = JSON.parse(await fs.readFile(path.join(auditDir, "review_queue_values.json"), "utf8"));
const [headers, ...rawRows] = queueAudit.rows;
const index = Object.fromEntries(headers.map((header, position) => [header, position]));
const decisions = rawRows.filter((row) => row[index["Review ID"]]).map((row) => ({
  annotation_id: String(row[index["Review ID"]]),
  status: String(row[index.Status] || "Pending").trim(),
  gold_evidence_chunk_ids: splitIds(row[index["Gold evidence chunk IDs"]]),
  accepted_graph_path_node_ids: splitPath(row[index["Accepted Graph Path Node IDs"]]),
  reviewer_rationale: String(row[index["Reviewer Rationale"]] || "").trim(),
}));

const chunks = new Map();
for (const fileName of (await fs.readdir(corpusDir)).filter((name) => name.endsWith("_enriched.json")).sort()) {
  const rows = JSON.parse(await fs.readFile(path.join(corpusDir, fileName), "utf8"));
  for (const row of rows) if (row.chunk_id) chunks.set(String(row.chunk_id), row);
}
const nodes = new Set((await readJsonLines(path.join(graphDir, "nodes.jsonl"))).map((row) => String(row.id)));
const edges = new Set((await readJsonLines(path.join(graphDir, "edges.jsonl"))).map((row) => `${row.source}\u0000${row.target}`));

const packById = new Map(pack.queries.map((row) => [String(row.annotation_id), row]));
const decisionById = new Map(decisions.map((row) => [row.annotation_id, row]));
const errors = [];
const warnings = [];
const allowedStatuses = new Set(["Confirmed", "Revise", "Exclude", "Pending"]);

for (const annotationId of packById.keys()) {
  if (!decisionById.has(annotationId)) errors.push({ annotation_id: annotationId, issue: "missing_workbook_row" });
}
for (const decision of decisions) {
  const source = packById.get(decision.annotation_id);
  if (!source) {
    errors.push({ annotation_id: decision.annotation_id, issue: "unknown_workbook_id" });
    continue;
  }
  if (!allowedStatuses.has(decision.status)) errors.push({ annotation_id: decision.annotation_id, issue: "unsupported_status", value: decision.status });
  if (decision.status !== "Pending" && !decision.reviewer_rationale) errors.push({ annotation_id: decision.annotation_id, issue: "missing_rationale" });
  if (["Confirmed", "Revise"].includes(decision.status) && decision.gold_evidence_chunk_ids.length === 0) {
    errors.push({ annotation_id: decision.annotation_id, issue: "missing_gold_evidence" });
  }
  const candidates = new Set(source.candidate_evidence_chunk_ids || []);
  for (const chunkId of decision.gold_evidence_chunk_ids) {
    if (!chunks.has(chunkId)) errors.push({ annotation_id: decision.annotation_id, issue: "unknown_chunk", value: chunkId });
    if (!candidates.has(chunkId)) warnings.push({ annotation_id: decision.annotation_id, issue: "gold_outside_review_candidates", value: chunkId });
    if (/^(?:fda_shortage:|fda_ndc:|fda_ingredient:|document:|section:|entity:)/.test(chunkId)) {
      errors.push({ annotation_id: decision.annotation_id, issue: "structured_node_in_text_gold", value: chunkId });
    }
  }
  for (const nodeId of decision.accepted_graph_path_node_ids) {
    if (!nodes.has(nodeId)) errors.push({ annotation_id: decision.annotation_id, issue: "unknown_graph_node", value: nodeId });
  }
  for (let position = 0; position + 1 < decision.accepted_graph_path_node_ids.length; position += 1) {
    const sourceNode = decision.accepted_graph_path_node_ids[position];
    const targetNode = decision.accepted_graph_path_node_ids[position + 1];
    if (!edges.has(`${sourceNode}\u0000${targetNode}`)) {
      errors.push({ annotation_id: decision.annotation_id, issue: "non_contiguous_graph_path", value: `${sourceNode} -> ${targetNode}` });
    }
  }
  if (source.query_slice === "supply_chain_evidence_path" && decision.status === "Confirmed" && decision.accepted_graph_path_node_ids.length === 0) {
    errors.push({ annotation_id: decision.annotation_id, issue: "confirmed_supply_path_missing_graph_nodes" });
  }
}

const statusCounts = Object.fromEntries(["Confirmed", "Revise", "Exclude", "Pending"].map((status) => [
  status,
  decisions.filter((row) => row.status === status).length,
]));
const revisions = decisions.filter((row) => row.status === "Revise").map((decision) => {
  const source = packById.get(decision.annotation_id);
  return {
    ...decision,
    original_query: source.query,
    evidence: decision.gold_evidence_chunk_ids.map((chunkId) => ({
      chunk_id: chunkId,
      doc_id: chunks.get(chunkId)?.doc_id || "",
      heading: chunks.get(chunkId)?.heading || "",
      content: chunks.get(chunkId)?.content || "",
    })),
  };
});
const report = {
  status: errors.length ? "invalid" : "valid_requires_revision_resolution",
  row_count: decisions.length,
  unique_id_count: decisionById.size,
  status_counts: statusCounts,
  errors,
  warnings,
  revisions,
};
await fs.writeFile(path.join(auditDir, "validation_report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  status: report.status,
  row_count: report.row_count,
  unique_id_count: report.unique_id_count,
  status_counts: report.status_counts,
  error_count: errors.length,
  warning_count: warnings.length,
  revision_ids: revisions.map((row) => row.annotation_id),
}, null, 2));
if (errors.length) process.exitCode = 1;

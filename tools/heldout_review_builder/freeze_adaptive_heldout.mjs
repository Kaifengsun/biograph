import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const round1Path = process.env.ROUND1_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_reviewed_round1_2026-07-15.json");
const revisionPackPath = process.env.REVISION_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_revision_round_2026-07-15.json");
const revisionWorkbookPath = process.env.CONFIRMED_REVISION_WORKBOOK || "D:/Downloads/adaptive_text_first_heldout_revision_round_2026-07-15_confirmed.xlsx";
const revisionAuditPath = process.env.REVISION_CONFIRM_AUDIT || path.join(projectRoot, "outputs/heldout_review_2026-07-15/revision_confirmed_audit/revision_queue_values.json");
const corpusDir = process.env.FROZEN_CORPUS || path.join(projectRoot, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const graphDir = process.env.FROZEN_GRAPH || path.join(projectRoot, "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda");
const outputPath = process.env.FROZEN_HELDOUT_OUTPUT || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_frozen_pending_method_lock_2026-07-15.json");

function splitIds(value) {
  return String(value || "").split(/[;\n]+/).map((item) => item.trim()).filter(Boolean);
}

async function sha256(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function readJsonLines(filePath) {
  return (await fs.readFile(filePath, "utf8")).split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function directoryFingerprint(dirPath, suffix) {
  const files = (await fs.readdir(dirPath)).filter((name) => name.endsWith(suffix)).sort();
  const manifest = [];
  for (const name of files) manifest.push({ name, sha256: await sha256(path.join(dirPath, name)) });
  return {
    file_count: manifest.length,
    sha256: crypto.createHash("sha256").update(JSON.stringify(manifest)).digest("hex"),
  };
}

try {
  await fs.access(outputPath);
  throw new Error(`refusing to overwrite existing frozen held-out set: ${outputPath}`);
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}

const round1 = JSON.parse(await fs.readFile(round1Path, "utf8"));
const revisionPack = JSON.parse(await fs.readFile(revisionPackPath, "utf8"));
const revisionAudit = JSON.parse(await fs.readFile(revisionAuditPath, "utf8"));
const revisionById = new Map(revisionPack.revisions.map((row) => [String(row.revision_id), row]));
const [headers, ...rawRows] = revisionAudit.rows;
const index = Object.fromEntries(headers.map((header, position) => [header, position]));
const confirmed = new Map();
for (const row of rawRows.filter((item) => item[index["Revision ID"]])) {
  const revisionId = String(row[index["Revision ID"]]);
  if (String(row[index.Status] || "") !== "Confirmed") throw new Error(`revision is not Confirmed: ${revisionId}`);
  const gold = splitIds(row[index["Accepted Gold chunk IDs"]]);
  if (!gold.length) throw new Error(`confirmed revision has no Gold chunks: ${revisionId}`);
  confirmed.set(revisionId, { gold, reviewer_rationale: String(row[index["Reviewer Rationale"]] || "").trim() });
}
if (confirmed.size !== revisionPack.revisions.length) throw new Error(`expected ${revisionPack.revisions.length} confirmed revisions, found ${confirmed.size}`);

const chunks = new Set();
for (const fileName of (await fs.readdir(corpusDir)).filter((name) => name.endsWith("_enriched.json")).sort()) {
  for (const row of JSON.parse(await fs.readFile(path.join(corpusDir, fileName), "utf8"))) if (row.chunk_id) chunks.add(String(row.chunk_id));
}
const graphNodes = new Set((await readJsonLines(path.join(graphDir, "nodes.jsonl"))).map((row) => String(row.id)));
const graphEdges = new Set((await readJsonLines(path.join(graphDir, "edges.jsonl"))).map((row) => `${row.source}\u0000${row.target}`));

const revisionsByOriginal = new Map(revisionPack.revisions.map((row) => [String(row.original_annotation_id), row]));
const queries = round1.queries.map((source) => {
  if (source.review_status === "reviewed" && source.eligible_for_formal_evaluation) return { ...source };
  const revision = revisionsByOriginal.get(String(source.annotation_id));
  if (!revision) throw new Error(`unresolved held-out row: ${source.annotation_id}`);
  const decision = confirmed.get(String(revision.revision_id));
  return {
    ...source,
    query: revision.revised_query,
    gold_evidence_chunk_ids: decision.gold,
    review_status: "reviewed",
    eligible_for_formal_evaluation: true,
    revision_history: [{
      revision_id: revision.revision_id,
      original_query: revision.original_query,
      revised_query: revision.revised_query,
      revision_reason: revision.revision_reason,
      round1_reviewer_rationale: revision.round1_reviewer_rationale,
      round2_reviewer_rationale: decision.reviewer_rationale,
    }],
  };
});

const expectedSlices = { single_clause: 10, table: 6, cross_document: 4, document_structure: 4, supply_chain_evidence_path: 6 };
const actualSlices = Object.fromEntries(Object.keys(expectedSlices).map((slice) => [slice, queries.filter((row) => row.query_slice === slice).length]));
if (queries.length !== 30 || new Set(queries.map((row) => row.annotation_id)).size !== 30) throw new Error("held-out set must contain exactly 30 unique IDs");
if (JSON.stringify(actualSlices) !== JSON.stringify(expectedSlices)) throw new Error(`slice composition mismatch: ${JSON.stringify(actualSlices)}`);
for (const row of queries) {
  if (row.review_status !== "reviewed" || !row.eligible_for_formal_evaluation) throw new Error(`ineligible frozen row: ${row.annotation_id}`);
  if (!(row.gold_evidence_chunk_ids || []).length) throw new Error(`missing Gold chunks: ${row.annotation_id}`);
  for (const chunkId of row.gold_evidence_chunk_ids) if (!chunks.has(chunkId)) throw new Error(`unknown Gold chunk ${chunkId} in ${row.annotation_id}`);
  const pathNodes = row.accepted_graph_path_node_ids || [];
  for (const nodeId of pathNodes) if (!graphNodes.has(nodeId)) throw new Error(`unknown graph node ${nodeId} in ${row.annotation_id}`);
  for (let position = 0; position + 1 < pathNodes.length; position += 1) {
    if (!graphEdges.has(`${pathNodes[position]}\u0000${pathNodes[position + 1]}`)) throw new Error(`broken graph path in ${row.annotation_id}`);
  }
  if (row.query_slice === "supply_chain_evidence_path" && pathNodes.length === 0) throw new Error(`supply-chain row lacks graph path: ${row.annotation_id}`);
}

const frozen = {
  schema_version: "1.0",
  status: "frozen_human_reviewed_heldout_pending_method_lock",
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  frozen_at_utc: new Date().toISOString(),
  activation_requirement: "Create a run-ready copy only after adaptive method code, parameters, indexes, and baselines are locked on the 60-query development set.",
  freeze_requirements: { exact_total: 30, exact_slice_counts: expectedSlices },
  review_ledger: { total_rows: 30, eligible_rows: 30, by_status: { reviewed: 30 }, by_slice: actualSlices },
  queries,
  provenance: {
    round1_pack: round1Path,
    round1_pack_sha256: await sha256(round1Path),
    revision_pack: revisionPackPath,
    revision_pack_sha256: await sha256(revisionPackPath),
    confirmed_revision_workbook: revisionWorkbookPath,
    confirmed_revision_workbook_sha256: await sha256(revisionWorkbookPath),
    corpus: corpusDir,
    corpus_fingerprint: await directoryFingerprint(corpusDir, "_enriched.json"),
    graph: graphDir,
    graph_nodes_sha256: await sha256(path.join(graphDir, "nodes.jsonl")),
    graph_edges_sha256: await sha256(path.join(graphDir, "edges.jsonl")),
  },
};
await fs.writeFile(outputPath, JSON.stringify(frozen, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, status: frozen.status, formal_metrics_ready: false, retrieval_execution_prohibited: true, review_ledger: frozen.review_ledger }, null, 2));

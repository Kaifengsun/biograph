import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPack = process.env.REVISION_PACK || "data/eval/three_path_revision_round_2026-07-14-v2-with-retrieval.json";
const retrievalPath = process.env.REVISION_RETRIEVAL || "artifacts/three_path_retrieval/revision_round_2026-07-14-v2/per_query.json";
const llmReviewPath = process.env.REVISION_LLM_REVIEW || "artifacts/llm_annotation_review/deepseek-v4-pro-revision-round-2026-07-14/llm_assisted_reviews.jsonl";
const corpusDir = "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4";
const graphDir = "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda";
const outputDir = process.env.REVISION_OUTPUT_DIR || "outputs/revision_annotation_review_2026-07-14-v2";
const outputPath = process.env.REVISION_OUTPUT_PATH || `${outputDir}/three_path_annotation_review_revision_round_2026-07-14-v2.xlsx`;

const pack = JSON.parse(await fs.readFile(inputPack, "utf8"));
const retrievalRows = JSON.parse(await fs.readFile(retrievalPath, "utf8"));
const llmRows = (await fs.readFile(llmReviewPath, "utf8")).split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
const llmById = new Map(llmRows.map((row) => [row.annotation_id, row.review || {}]));

function joined(values) { return (values || []).filter(Boolean).join("; "); }

async function loadCorpus() {
  const byId = new Map();
  for (const name of await fs.readdir(corpusDir)) {
    if (!name.endsWith("_enriched.json")) continue;
    const sourcePath = path.join(corpusDir, name);
    for (const row of JSON.parse(await fs.readFile(sourcePath, "utf8"))) {
      if (row.chunk_id) byId.set(row.chunk_id, { ...row, sourcePath });
    }
  }
  return byId;
}

async function loadGraphNodes() {
  const byId = new Map();
  const text = await fs.readFile(path.join(graphDir, "nodes.jsonl"), "utf8");
  for (const line of text.split(/\r?\n/)) {
    if (line.trim()) { const node = JSON.parse(line); byId.set(node.id, node); }
  }
  return byId;
}

function routeRankings(retrieval) {
  const rankings = new Map();
  for (const [route, rows] of [["Bottom-up", retrieval.bottom_up], ["Top-down", retrieval.top_down?.evidence], ["Graph-backed", retrieval.graph_path?.evidence]]) {
    for (const [index, item] of (rows || []).entries()) {
      if (!item.chunk_id) continue;
      rankings.set(item.chunk_id, [...(rankings.get(item.chunk_id) || []), { route, rank: index + 1 }]);
    }
  }
  return rankings;
}

function humanNode(nodeId, graphNodes, chunks) {
  if (nodeId.startsWith("chunk:")) { const row = chunks.get(nodeId.slice(6)); return `Source chunk: ${row?.heading || nodeId.slice(6)}`; }
  const node = graphNodes.get(nodeId);
  return node ? `${node.label || "Node"}: ${node.name || nodeId}` : nodeId;
}

function pathText(pathRow, graphNodes, chunks) {
  return (pathRow.node_ids || []).map((nodeId, index) => index >= (pathRow.edges || []).length
    ? humanNode(nodeId, graphNodes, chunks)
    : `${humanNode(nodeId, graphNodes, chunks)} --[${pathRow.edges[index].relation || "RELATED"}]-- `).join("");
}

const corpus = await loadCorpus();
const graphNodes = await loadGraphNodes();
const retrievalById = new Map(retrievalRows.map((row) => [row.query_id, row.retrieval]));
const queueRows = [], evidenceRows = [], pathRows = [];
for (const row of pack.queries) {
  const retrieval = retrievalById.get(row.annotation_id) || {};
  const llm = llmById.get(row.annotation_id) || {};
  const directIds = llm.direct_support_chunk_ids || [];
  const directSet = new Set(directIds);
  const rankings = routeRankings(retrieval);
  const candidateIds = [...new Set([...(directIds || []), ...(row.candidate_evidence_chunk_ids || [])])].sort((a, b) => {
    const ap = directSet.has(a) ? 1 : rankings.has(a) ? 2 : 3;
    const bp = directSet.has(b) ? 1 : rankings.has(b) ? 2 : 3;
    const ar = Math.min(...(rankings.get(a) || [{ rank: 999 }]).map((x) => x.rank));
    const br = Math.min(...(rankings.get(b) || [{ rank: 999 }]).map((x) => x.rank));
    return ap - bp || ar - br || a.localeCompare(b);
  });
  queueRows.push([row.annotation_id, row.original_annotation_id, row.query_slice, row.original_query, row.query, row.revision_note, joined(directIds) || "No direct LLM evidence suggested", Boolean(llm.insufficient_evidence), llm.rationale || "", `Filter Evidence Reader by ${row.annotation_id}`, "Pending", "", "", ""]);
  if (!candidateIds.length) evidenceRows.push([row.annotation_id, "No evidence", "No candidate passage available", "", "", "", "", "The frozen corpus did not supply a candidate passage."]);
  for (const chunkId of candidateIds) {
    const chunk = corpus.get(chunkId);
    const priority = directSet.has(chunkId) ? "1. LLM direct evidence" : rankings.has(chunkId) ? "2. Ranked retrieval evidence" : "3. Additional candidate";
    const routeText = (rankings.get(chunkId) || []).map((item) => `${item.route} #${item.rank}`).join(" | ");
    evidenceRows.push([row.annotation_id, priority, chunkId, chunk?.doc_id || "Missing from frozen corpus", chunk?.heading || "", chunk?.content || "No matching chunk was found in the frozen corpus.", chunk?.sourcePath || "", directSet.has(chunkId) ? "The LLM selected this candidate as direct support. Verify against its original passage." : routeText || "Additional candidate; inspect only when earlier passages are insufficient."]);
  }
  for (const [index, graphPath] of (retrieval.graph_path?.paths || []).slice(0, 5).entries()) {
    pathRows.push([row.annotation_id, index + 1, "Read after source passages", pathText(graphPath, graphNodes, corpus), joined((graphPath.node_ids || []).filter((id) => id.startsWith("chunk:")).map((id) => id.slice(6))), joined((graphPath.edges || []).map((edge) => edge.relation)), "A graph path is contextual support only. Confirm source evidence before accepting path nodes."]);
  }
}

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Overview");
const queue = workbook.worksheets.add("Review Queue");
const evidence = workbook.worksheets.add("Evidence Reader");
const paths = workbook.worksheets.add("Graph Paths");
for (const sheet of [overview, queue, evidence, paths]) sheet.showGridLines = false;

overview.getRange("A1:F1").merge(); overview.getRange("A1").values = [["Three-Path Evidence Review"]];
overview.getRange("A2:F2").merge(); overview.getRange("A2").values = [["All revised questions reproduce the reviewer-approved wording from 实验审核结果.docx. This workbook is a human-review aid, not a formal result."]];
overview.getRange("A4:C8").values = [["Review order", "What to do", "Why"], ["1", "Read the original question, revision basis, and revised question in Review Queue.", "Confirm the revision did not change the intended scope."], ["2", "Filter Evidence Reader by Revision ID. Read Priority 1, then Priority 2, then Priority 3 only if needed.", "The LLM suggestion is only a ranked aid."], ["3", "Set Confirmed only when a source passage directly answers the revised question; enter its Chunk ID.", "This creates a defensible gold-evidence label."], ["4", "Read Graph Paths last for cross-document/entity questions.", "A graph path cannot substitute for source evidence."]];
overview.getRange("A10:F12").values = [["Review queue", "Evidence rows", "Graph paths", "Formal status", "", ""], [`=COUNTA('Review Queue'!A2:A${queueRows.length + 1})`, `=COUNTA('Evidence Reader'!A2:A${evidenceRows.length + 1})`, `=COUNTA('Graph Paths'!A2:A${Math.max(pathRows.length + 1, 2)})`, "Not formal until human reviewed and frozen", "", ""], [`${queueRows.length} questions in this review round`, "Source passages embedded", "Context only", "No metrics yet", "", ""]];

const queueHeaders = ["Revision ID", "Original Review ID", "Slice", "Original question", "Revised question", "Why revised (from first review)", "LLM suggested evidence chunk IDs", "LLM says insufficient", "LLM rationale", "Where to read evidence", "Reviewer status", "Gold evidence chunk IDs", "Accepted graph path node IDs", "Reviewer note"];
queue.getRangeByIndexes(0, 0, 1, queueHeaders.length).values = [queueHeaders];
queue.getRangeByIndexes(1, 0, queueRows.length, queueHeaders.length).values = queueRows;
queue.tables.add(`A1:N${queueRows.length + 1}`, true, "RevisionReviewQueue");
queue.getRange(`K2:K${queueRows.length + 1}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };

const evidenceHeaders = ["Revision ID", "Priority", "Chunk ID", "Document ID", "Section heading", "Original source passage", "Frozen source file", "Why this passage is shown"];
evidence.getRangeByIndexes(0, 0, 1, evidenceHeaders.length).values = [evidenceHeaders];
evidence.getRangeByIndexes(1, 0, evidenceRows.length, evidenceHeaders.length).values = evidenceRows;
evidence.tables.add(`A1:H${evidenceRows.length + 1}`, true, "RevisionEvidenceReader");

const pathHeaders = ["Revision ID", "Path rank", "Review order", "Human-readable graph path", "Source chunk IDs on path", "Relations", "How to use this path"];
paths.getRangeByIndexes(0, 0, 1, pathHeaders.length).values = [pathHeaders];
if (pathRows.length) { paths.getRangeByIndexes(1, 0, pathRows.length, pathHeaders.length).values = pathRows; paths.tables.add(`A1:G${pathRows.length + 1}`, true, "RevisionGraphPaths"); }

const title = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center", verticalAlignment: "center" };
const header = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
const subHeader = { fill: "#2A6F97", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
overview.getRange("A1:F1").format = title; overview.getRange("A2:F2").format = { fill: "#E8F1F5", font: { italic: true, color: "#17465E" }, wrapText: true }; overview.getRange("A4:C4").format = subHeader; overview.getRange("A10:F10").format = subHeader;
overview.getRange("A1:F12").format.wrapText = true; overview.getRange("A1:F12").format.verticalAlignment = "center"; overview.getRange("A1:F1").format.rowHeight = 30; overview.getRange("A2:F2").format.rowHeight = 36; overview.getRange("A4:C8").format.rowHeight = 44; overview.getRange("A1:A12").format.columnWidth = 17; overview.getRange("B1:B12").format.columnWidth = 62; overview.getRange("C1:C12").format.columnWidth = 48; overview.getRange("D1:F12").format.columnWidth = 22;
for (const sheet of [queue, evidence, paths]) { sheet.freezePanes.freezeRows(1); sheet.getRange("A1:Z1").format = header; sheet.getRange("A1:Z1").format.rowHeight = 34; }
queue.freezePanes.freezeColumns(2); queue.getRange(`A2:N${queueRows.length + 1}`).format.wrapText = true; queue.getRange(`A2:N${queueRows.length + 1}`).format.verticalAlignment = "top"; queue.getRange(`A2:N${queueRows.length + 1}`).format.rowHeight = 92;
for (const [col, width] of [["A",17],["B",17],["C",20],["D",46],["E",46],["F",58],["G",32],["H",14],["I",50],["J",22],["K",16],["L",34],["M",42],["N",38]]) queue.getRange(`${col}1:${col}${queueRows.length + 1}`).format.columnWidth = width;
queue.getRange(`K2:K${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: "#D9EAD3", font: { color: "#2E6B2E", bold: true } } }); queue.getRange(`K2:K${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } } }); queue.getRange(`K2:K${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: "#F4CCCC", font: { color: "#990000", bold: true } } });
evidence.freezePanes.freezeColumns(2); evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.wrapText = true; evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.verticalAlignment = "top"; evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.rowHeight = 92;
for (const [col, width] of [["A",17],["B",25],["C",34],["D",25],["E",36],["F",72],["G",55],["H",46]]) evidence.getRange(`${col}1:${col}${evidenceRows.length + 1}`).format.columnWidth = width;
evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "1.", format: { fill: "#D9EAD3", font: { color: "#2E6B2E", bold: true } } }); evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "2.", format: { fill: "#DDEBF7", font: { color: "#1F4E78", bold: true } } }); evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "3.", format: { fill: "#F3F3F3", font: { color: "#666666" } } });
paths.freezePanes.freezeColumns(2); paths.getRange(`A1:G${Math.max(pathRows.length + 1, 2)}`).format.wrapText = true; paths.getRange(`A1:G${Math.max(pathRows.length + 1, 2)}`).format.verticalAlignment = "top"; paths.getRange(`A2:G${Math.max(pathRows.length + 1, 2)}`).format.rowHeight = 78;
for (const [col, width] of [["A",17],["B",12],["C",24],["D",90],["E",34],["F",32],["G",48]]) paths.getRange(`${col}1:${col}301`).format.columnWidth = width;

await fs.mkdir(outputDir, { recursive: true });
const checks = [await workbook.inspect({ kind: "table", range: "Review Queue!A1:N6", include: "values,formulas", tableMaxRows: 6, tableMaxCols: 14 }), await workbook.inspect({ kind: "table", range: "Evidence Reader!A1:H6", include: "values", tableMaxRows: 6, tableMaxCols: 8 }), await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?", options: { useRegex: true, maxResults: 100 } })];
await fs.writeFile(`${outputDir}/workbook_checks.ndjson`, checks.map((check) => check.ndjson).join("\n"));
for (const [sheetName, range, name] of [["Overview", "A1:F12", "overview"], ["Review Queue", "A1:N6", "queue"], ["Evidence Reader", "A1:H6", "evidence"], ["Graph Paths", "A1:G6", "paths"]]) { const image = await workbook.render({ sheetName, range, scale: 1, format: "png" }); await fs.writeFile(`${outputDir}/${name}.png`, new Uint8Array(await image.arrayBuffer())); }
const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(outputPath);
console.log(JSON.stringify({ outputPath, reviewRows: queueRows.length, evidenceRows: evidenceRows.length, graphPathRows: pathRows.length }, null, 2));

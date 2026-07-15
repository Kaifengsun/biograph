import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPack = "data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json";
const retrievalPath = "artifacts/three_path_retrieval/annotation_candidates_2026-07-11-v1/per_query.json";
const corpusDir = "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4";
const graphDir = "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda";
const outputDir = "outputs/guided_annotation_review_2026-07-13";
const outputPath = `${outputDir}/three_path_annotation_review_guided_2026-07-13.xlsx`;

const quotas = {
  single_clause: 20,
  cross_document: 20,
  document_structure: 7,
  table: 12,
  supply_chain_evidence_path: 1,
};

const pack = JSON.parse(await fs.readFile(inputPack, "utf8"));
const retrievalRows = JSON.parse(await fs.readFile(retrievalPath, "utf8"));

function normalizeAlias(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function reviewPriority(row) {
  const review = row.llm_assisted_review || {};
  return [
    review.insufficient_evidence ? 0 : 1,
    (row.retrieval_candidate_graph_paths || []).length ? 0 : 1,
    -(row.candidate_evidence_chunk_ids || []).length,
    row.annotation_id,
  ];
}

function comparePriority(a, b) {
  const left = reviewPriority(a);
  const right = reviewPriority(b);
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] < right[i]) return -1;
    if (left[i] > right[i]) return 1;
  }
  return 0;
}

async function loadCorpus() {
  const byId = new Map();
  for (const name of await fs.readdir(corpusDir)) {
    if (!name.endsWith("_enriched.json")) continue;
    const sourcePath = path.join(corpusDir, name);
    const rows = JSON.parse(await fs.readFile(sourcePath, "utf8"));
    for (const row of rows) {
      if (row.chunk_id) byId.set(row.chunk_id, { ...row, sourcePath });
    }
  }
  return byId;
}

async function loadGraphNodes() {
  const text = await fs.readFile(path.join(graphDir, "nodes.jsonl"), "utf8");
  const byId = new Map();
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const node = JSON.parse(line);
    byId.set(node.id, node);
  }
  return byId;
}

function routeRankings(retrieval) {
  const rankings = new Map();
  const addRows = (route, rows) => {
    for (const [index, item] of (rows || []).entries()) {
      const chunkId = item.chunk_id;
      if (!chunkId) continue;
      const existing = rankings.get(chunkId) || [];
      existing.push({ route, rank: index + 1 });
      rankings.set(chunkId, existing);
    }
  };
  addRows("Bottom-up", retrieval.bottom_up);
  addRows("Top-down", retrieval.top_down?.evidence);
  addRows("Graph-backed", retrieval.graph_path?.evidence);
  return rankings;
}

function humanNode(nodeId, graphNodes, chunks) {
  const node = graphNodes.get(nodeId);
  if (nodeId.startsWith("chunk:")) {
    const chunkId = nodeId.slice("chunk:".length);
    const chunk = chunks.get(chunkId);
    return `Source chunk: ${chunk?.heading || chunkId}`;
  }
  if (!node) return nodeId;
  return `${node.label || "Node"}: ${node.name || nodeId}`;
}

function pathText(pathRow, graphNodes, chunks) {
  const nodes = pathRow.node_ids || [];
  const edges = pathRow.edges || [];
  return nodes.map((nodeId, index) => {
    const nodeText = humanNode(nodeId, graphNodes, chunks);
    if (index >= edges.length) return nodeText;
    return `${nodeText} --[${edges[index].relation || "RELATED"}]-- `;
  }).join("");
}

function joined(values) {
  return (values || []).filter(Boolean).join("; ");
}

const activeRows = pack.queries.filter((row) => row.review_status !== "excluded");
const selected = [];
for (const [slice, quota] of Object.entries(quotas)) {
  selected.push(...activeRows.filter((row) => row.query_slice === slice).sort(comparePriority).slice(0, quota));
}
if (selected.length !== 60) throw new Error(`Expected 60 review rows, got ${selected.length}`);

const corpus = await loadCorpus();
const graphNodes = await loadGraphNodes();
const retrievalByQuery = new Map(retrievalRows.map((record) => [normalizeAlias(record.retrieval?.query), record.retrieval]));

const queueRows = [];
const evidenceRows = [];
const pathRows = [];
for (const row of selected) {
  const retrieval = retrievalByQuery.get(normalizeAlias(row.query)) || {};
  const directIds = row.llm_assisted_review?.direct_support_chunk_ids || [];
  const directSet = new Set(directIds);
  const rankings = routeRankings(retrieval);
  const candidateIds = [...new Set([...(directIds || []), ...(row.candidate_evidence_chunk_ids || [])])];
  const orderedIds = candidateIds.sort((left, right) => {
    const leftPriority = directSet.has(left) ? 1 : rankings.has(left) ? 2 : 3;
    const rightPriority = directSet.has(right) ? 1 : rankings.has(right) ? 2 : 3;
    if (leftPriority !== rightPriority) return leftPriority - rightPriority;
    const leftRank = Math.min(...(rankings.get(left) || [{ rank: 999 }]).map((item) => item.rank));
    const rightRank = Math.min(...(rankings.get(right) || [{ rank: 999 }]).map((item) => item.rank));
    return leftRank - rightRank || left.localeCompare(right);
  });

  queueRows.push([
    row.annotation_id,
    row.query_slice,
    row.query,
    directIds.length ? joined(directIds) : "No direct LLM evidence suggested",
    Boolean(row.llm_assisted_review?.insufficient_evidence),
    row.llm_assisted_review?.rationale || "",
    `Filter Evidence Reader by ${row.annotation_id}`,
    "Pending",
    "",
    "",
    "",
  ]);

  if (!orderedIds.length) {
    evidenceRows.push([row.annotation_id, "No evidence", "No candidate passage available", "", "", "", "", "The current frozen corpus did not supply a candidate passage."]);
  }
  for (const chunkId of orderedIds) {
    const chunk = corpus.get(chunkId);
    const priority = directSet.has(chunkId) ? "1. LLM direct evidence" : rankings.has(chunkId) ? "2. Ranked retrieval evidence" : "3. Additional candidate";
    const routeText = (rankings.get(chunkId) || []).map((item) => `${item.route} #${item.rank}`).join(" | ");
    evidenceRows.push([
      row.annotation_id,
      priority,
      chunkId,
      chunk?.doc_id || "Missing from frozen corpus",
      chunk?.heading || "",
      chunk?.content || "No matching chunk was found in the frozen source corpus.",
      chunk?.sourcePath || "",
      directSet.has(chunkId) ? "The LLM selected this candidate as direct support. Verify against its original passage." : routeText || "Legacy/additional candidate; inspect only when earlier evidence is insufficient.",
    ]);
  }

  for (const [index, pathRow] of (retrieval.graph_path?.paths || []).slice(0, 5).entries()) {
    pathRows.push([
      row.annotation_id,
      index + 1,
      "Read after source passages",
      pathText(pathRow, graphNodes, corpus),
      joined((pathRow.node_ids || []).filter((nodeId) => nodeId.startsWith("chunk:")).map((nodeId) => nodeId.slice("chunk:".length))),
      joined((pathRow.edges || []).map((edge) => edge.relation)),
      "A path is contextual support only. Confirm its source chunk answers the question before accepting any node IDs.",
    ]);
  }
}

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Overview");
const queue = workbook.worksheets.add("Review Queue");
const evidence = workbook.worksheets.add("Evidence Reader");
const paths = workbook.worksheets.add("Graph Paths");
for (const sheet of [overview, queue, evidence, paths]) sheet.showGridLines = false;

overview.getRange("A1:F1").merge();
overview.getRange("A1").values = [["Guided Three-Path Evidence Review"]];
overview.getRange("A2:F2").merge();
overview.getRange("A2").values = [["This workbook embeds frozen source passages. It is a human-review aid, not a formal result."]];
overview.getRange("A4:F7").values = [
  ["Review order", "What to do", "Why", "", "", ""],
  ["1", "Find the Review ID in Review Queue, then filter Evidence Reader by that ID.", "This keeps all source passages for one question together.", "", "", ""],
  ["2", "Read Priority 1: LLM direct evidence. Check the original passage, not the model rationale alone.", "The model suggestion can still be wrong.", "", "", ""],
  ["3", "If needed, read Priority 2: ranked retrieval evidence. Use Priority 3 only when the earlier passages are insufficient.", "This reduces unnecessary reading while keeping every candidate available.", "", "", ""],
];
overview.getRange("A9:F12").values = [
  ["Graph paths", "When to read", "How to use", "", "", ""],
  ["Last", "Read Graph Paths only after checking source passages, and only when the question involves entities, supply chains, or cross-document links.", "A graph path provides context; it is not evidence by itself.", "", "", ""],
  ["Confirmed", "At least one passage directly answers the question.", "Copy its chunk ID into Gold evidence chunk IDs.", "", "", ""],
  ["Revise / Exclude", "Related passages do not directly answer the question, or the corpus lacks evidence.", "Use Revise for a repairable question and Exclude for an unsupported one.", "", "", ""],
];
overview.getRange("A14:F16").values = [
  ["Review queue", "Priority 1 passages", "Priority 2 passages", "Priority 3 passages", "Graph paths", "Formal status"],
  ["=COUNTA('Review Queue'!A2:A61)", `=COUNTIF('Evidence Reader'!B2:B2000,"1. LLM direct evidence")`, `=COUNTIF('Evidence Reader'!B2:B2000,"2. Ranked retrieval evidence")`, `=COUNTIF('Evidence Reader'!B2:B2000,"3. Additional candidate")`, "=COUNTA('Graph Paths'!A2:A301)", "Not formal until reviewed and frozen"],
  ["Fixed balanced sample", "Read first", "Read second", "Read only if needed", "Read last", "No retrieval metric is valid yet"],
];

const queueHeaders = [
  "Review ID", "Slice", "Question", "LLM suggested evidence chunk IDs", "LLM says insufficient", "LLM rationale",
  "Where to read the evidence", "Reviewer status", "Gold evidence chunk IDs", "Accepted graph path node IDs", "Reviewer note",
];
queue.getRangeByIndexes(0, 0, 1, queueHeaders.length).values = [queueHeaders];
queue.getRangeByIndexes(1, 0, queueRows.length, queueHeaders.length).values = queueRows;
queue.tables.add(`A1:K${queueRows.length + 1}`, true, "GuidedReviewQueue");
queue.getRange(`H2:H${queueRows.length + 1}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };

const evidenceHeaders = ["Review ID", "Priority", "Chunk ID", "Document ID", "Section heading", "Original source passage", "Frozen source file", "Why this passage is shown"];
evidence.getRangeByIndexes(0, 0, 1, evidenceHeaders.length).values = [evidenceHeaders];
evidence.getRangeByIndexes(1, 0, evidenceRows.length, evidenceHeaders.length).values = evidenceRows;
evidence.tables.add(`A1:H${evidenceRows.length + 1}`, true, "GuidedEvidenceReader");

const pathHeaders = ["Review ID", "Path rank", "Review order", "Human-readable graph path", "Source chunk IDs on path", "Relations", "How to use this path"];
paths.getRangeByIndexes(0, 0, 1, pathHeaders.length).values = [pathHeaders];
if (pathRows.length) {
  paths.getRangeByIndexes(1, 0, pathRows.length, pathHeaders.length).values = pathRows;
  paths.tables.add(`A1:G${pathRows.length + 1}`, true, "GuidedGraphPaths");
}

const titleFormat = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center", verticalAlignment: "center" };
const headerFormat = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
const subHeaderFormat = { fill: "#2A6F97", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };

overview.getRange("A1:F1").format = titleFormat;
overview.getRange("A2:F2").format = { fill: "#E8F1F5", font: { italic: true, color: "#17465E" }, wrapText: true };
overview.getRange("A4:F4").format = subHeaderFormat;
overview.getRange("A9:F9").format = subHeaderFormat;
overview.getRange("A14:F14").format = subHeaderFormat;
overview.getRange("A15:F15").format = { fill: "#F5FAFC", font: { bold: true }, horizontalAlignment: "center", wrapText: true };
overview.getRange("A1:F16").format.wrapText = true;
overview.getRange("A1:F16").format.verticalAlignment = "center";
overview.getRange("A1:F1").format.rowHeight = 30;
overview.getRange("A2:F2").format.rowHeight = 34;
overview.getRange("A4:F12").format.rowHeight = 38;
overview.getRange("A1:A16").format.columnWidth = 16;
overview.getRange("B1:B16").format.columnWidth = 45;
overview.getRange("C1:C16").format.columnWidth = 45;
overview.getRange("D1:F16").format.columnWidth = 20;
overview.getRange("A4:C7").format.borders = { preset: "outside", style: "thin", color: "#C9D9E3" };
overview.getRange("A9:C12").format.borders = { preset: "outside", style: "thin", color: "#C9D9E3" };
overview.getRange("A14:F16").format.borders = { preset: "all", style: "thin", color: "#C9D9E3" };

for (const sheet of [queue, evidence, paths]) {
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A1:Z1").format = headerFormat;
  sheet.getRange("A1:Z1").format.rowHeight = 30;
}
queue.freezePanes.freezeColumns(2);
queue.getRange(`A2:K${queueRows.length + 1}`).format.wrapText = true;
queue.getRange(`A2:K${queueRows.length + 1}`).format.verticalAlignment = "top";
queue.getRange(`A2:K${queueRows.length + 1}`).format.rowHeight = 80;
queue.getRange(`A1:A${queueRows.length + 1}`).format.columnWidth = 15;
queue.getRange(`B1:B${queueRows.length + 1}`).format.columnWidth = 20;
queue.getRange(`C1:C${queueRows.length + 1}`).format.columnWidth = 44;
queue.getRange(`D1:D${queueRows.length + 1}`).format.columnWidth = 32;
queue.getRange(`E1:E${queueRows.length + 1}`).format.columnWidth = 14;
queue.getRange(`F1:F${queueRows.length + 1}`).format.columnWidth = 55;
queue.getRange(`G1:G${queueRows.length + 1}`).format.columnWidth = 23;
queue.getRange(`H1:H${queueRows.length + 1}`).format.columnWidth = 16;
queue.getRange(`I1:I${queueRows.length + 1}`).format.columnWidth = 34;
queue.getRange(`J1:J${queueRows.length + 1}`).format.columnWidth = 45;
queue.getRange(`K1:K${queueRows.length + 1}`).format.columnWidth = 38;
queue.getRange(`H2:H${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: "#D9EAD3", font: { color: "#2E6B2E", bold: true } } });
queue.getRange(`H2:H${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } } });
queue.getRange(`H2:H${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: "#F4CCCC", font: { color: "#990000", bold: true } } });

evidence.freezePanes.freezeColumns(2);
evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.wrapText = true;
evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.verticalAlignment = "top";
evidence.getRange(`A2:H${evidenceRows.length + 1}`).format.rowHeight = 90;
evidence.getRange(`A1:A${evidenceRows.length + 1}`).format.columnWidth = 15;
evidence.getRange(`B1:B${evidenceRows.length + 1}`).format.columnWidth = 25;
evidence.getRange(`C1:C${evidenceRows.length + 1}`).format.columnWidth = 34;
evidence.getRange(`D1:D${evidenceRows.length + 1}`).format.columnWidth = 25;
evidence.getRange(`E1:E${evidenceRows.length + 1}`).format.columnWidth = 36;
evidence.getRange(`F1:F${evidenceRows.length + 1}`).format.columnWidth = 72;
evidence.getRange(`G1:G${evidenceRows.length + 1}`).format.columnWidth = 55;
evidence.getRange(`H1:H${evidenceRows.length + 1}`).format.columnWidth = 46;
evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "1.", format: { fill: "#D9EAD3", font: { color: "#2E6B2E", bold: true } } });
evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "2.", format: { fill: "#DDEBF7", font: { color: "#1F4E78", bold: true } } });
evidence.getRange(`B2:B${evidenceRows.length + 1}`).conditionalFormats.add("beginsWith", { text: "3.", format: { fill: "#F3F3F3", font: { color: "#666666" } } });

paths.freezePanes.freezeColumns(2);
paths.getRange(`A1:G${Math.max(pathRows.length + 1, 2)}`).format.wrapText = true;
paths.getRange(`A1:G${Math.max(pathRows.length + 1, 2)}`).format.verticalAlignment = "top";
paths.getRange(`A2:G${Math.max(pathRows.length + 1, 2)}`).format.rowHeight = 72;
paths.getRange("A1:A301").format.columnWidth = 15;
paths.getRange("B1:B301").format.columnWidth = 12;
paths.getRange("C1:C301").format.columnWidth = 24;
paths.getRange("D1:D301").format.columnWidth = 90;
paths.getRange("E1:E301").format.columnWidth = 34;
paths.getRange("F1:F301").format.columnWidth = 32;
paths.getRange("G1:G301").format.columnWidth = 48;

await fs.mkdir(outputDir, { recursive: true });
const checks = [
  await workbook.inspect({ kind: "table", range: "Review Queue!A1:K8", include: "values,formulas", tableMaxRows: 8, tableMaxCols: 11 }),
  await workbook.inspect({ kind: "table", range: "Evidence Reader!A1:H8", include: "values", tableMaxRows: 8, tableMaxCols: 8 }),
  await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?", options: { useRegex: true, maxResults: 100 } }),
];
await fs.writeFile(`${outputDir}/workbook_checks.ndjson`, checks.map((check) => check.ndjson).join("\n"));
for (const [sheetName, range, name] of [
  ["Overview", "A1:F16", "overview"],
  ["Review Queue", "A1:K8", "queue"],
  ["Evidence Reader", "A1:H8", "evidence"],
  ["Graph Paths", "A1:G8", "paths"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, reviewRows: queueRows.length, evidenceRows: evidenceRows.length, graphPathRows: pathRows.length }, null, 2));

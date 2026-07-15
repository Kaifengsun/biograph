import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const packPath = process.env.HELDOUT_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_candidates_2026-07-15.json");
const corpusDir = process.env.FROZEN_CORPUS || path.join(projectRoot, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const outputDir = process.env.HELDOUT_REVIEW_OUTPUT_DIR || path.join(projectRoot, "outputs/heldout_review_2026-07-15");
const outputPath = process.env.HELDOUT_REVIEW_OUTPUT || path.join(outputDir, "adaptive_text_first_heldout_review_2026-07-15.xlsx");

const pack = JSON.parse(await fs.readFile(packPath, "utf8"));
const chunkStore = new Map();
for (const fileName of (await fs.readdir(corpusDir)).filter((name) => name.endsWith("_enriched.json")).sort()) {
  const filePath = path.join(corpusDir, fileName);
  const rows = JSON.parse(await fs.readFile(filePath, "utf8"));
  for (const row of rows) {
    if (row.chunk_id) chunkStore.set(String(row.chunk_id), { ...row, frozen_source_file: filePath });
  }
}

const queueRows = [];
const evidenceRows = [];
for (const row of pack.queries) {
  const suggestedGold = row.suggested_gold_evidence_chunk_ids || [];
  const suggestedPath = row.suggested_graph_path_node_ids || [];
  queueRows.push([
    row.annotation_id,
    row.query_slice,
    row.query,
    "Pending",
    suggestedGold.join("; "),
    suggestedGold.join("; "),
    suggestedPath.join(" -> "),
    suggestedPath.join("; "),
    "",
    row.origin,
    null,
  ]);
  if (row.structured_graph_record) {
    evidenceRows.push([
      row.annotation_id,
      1,
      "Structured graph record",
      suggestedPath[0] || "",
      suggestedPath.join(" -> "),
      "FDA drug-shortage event",
      Object.entries(row.structured_graph_record).map(([key, value]) => `${key}: ${value}`).join("\n"),
      `${pack.sources.graph} | openFDA drug-shortages snapshot encoded in frozen graph`,
    ]);
  }
  const suggestedSet = new Set(suggestedGold);
  for (const chunkId of row.candidate_evidence_chunk_ids || []) {
    const chunk = chunkStore.get(chunkId);
    if (!chunk) throw new Error(`Missing frozen source chunk: ${chunkId}`);
    evidenceRows.push([
      row.annotation_id,
      suggestedSet.has(chunkId) ? 1 : 2,
      suggestedSet.has(chunkId) ? "Suggested text evidence" : "Additional text candidate",
      chunkId,
      chunk.doc_id || "",
      chunk.heading || "",
      chunk.content || "",
      chunk.frozen_source_file,
    ]);
  }
}

const workbook = Workbook.create();
const protocol = workbook.worksheets.add("Protocol");
const queue = workbook.worksheets.add("Review Queue");
const evidence = workbook.worksheets.add("Evidence Reader");
const colors = {
  navy: "#16324F",
  blue: "#2563EB",
  paleBlue: "#EAF2FF",
  yellow: "#FFF4CC",
  green: "#DCFCE7",
  red: "#FEE2E2",
  orange: "#FFEDD5",
  gray: "#64748B",
  paleGray: "#F1F5F9",
  border: "#CBD5E1",
  white: "#FFFFFF",
};

for (const sheet of [protocol, queue, evidence]) sheet.showGridLines = false;

protocol.mergeCells("A1:H1");
protocol.getRange("A1").values = [["Adaptive Text-First Held-Out Evaluation Review"]];
protocol.getRange("A1:H1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
protocol.getRange("A1:H1").format.rowHeight = 34;
protocol.getRange("A3:B10").values = [
  ["Purpose", "Human-review and freeze 30 untouched queries before adaptive retrieval is implemented."],
  ["Do not execute", "Do not run retrieval on these queries until review, freeze, code lock, and parameter lock are complete."],
  ["Review order", "Open Review Queue, choose one Review ID, then filter Evidence Reader by the same ID. Read Priority 1 first; use Priority 2 only when needed."],
  ["Confirmed", "The question is answerable from the frozen evidence. Keep or correct Gold evidence chunk IDs. For graph cases, also verify the accepted node path."],
  ["Revise", "The evidence is useful but the question or gold set needs revision. Explain the change in Reviewer Rationale."],
  ["Exclude", "The evidence does not directly answer the question or the case is unsuitable for held-out evaluation."],
  ["Graph policy", "Graph node IDs belong only in Accepted Graph Path Node IDs. Never place structured nodes in Gold evidence chunk IDs."],
  ["Reviewer input", "Yellow cells in Review Queue are editable. Suggested values are prefilled to reduce manual work."],
];
protocol.getRange("A3:A10").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy }, verticalAlignment: "top" };
protocol.getRange("B3:B10").format = { wrapText: true, verticalAlignment: "top" };
protocol.getRange("A3:B10").format.borders = { preset: "insideHorizontal", style: "thin", color: colors.border };
protocol.getRange("D3:E9").values = [
  ["Review summary", "Count"],
  ["Total", null],
  ["Pending", null],
  ["Confirmed", null],
  ["Revise", null],
  ["Exclude", null],
  ["Completed", null],
];
protocol.getRange("D3:E3").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
protocol.getRange("E4").formulas = [["=COUNTA('Review Queue'!$A$5:$A$34)"]];
protocol.getRange("E5").formulas = [["=COUNTIF('Review Queue'!$D$5:$D$34,D5)"]];
protocol.getRange("E5:E8").fillDown();
protocol.getRange("E9").formulas = [["=SUM(E6:E8)"]];
protocol.getRange("D4:E9").format.borders = { preset: "insideHorizontal", style: "thin", color: colors.border };
protocol.getRange("E4:E9").format.numberFormat = "0";
protocol.getRange("A:A").format.columnWidth = 19;
protocol.getRange("B:B").format.columnWidth = 78;
protocol.getRange("C:C").format.columnWidth = 3;
protocol.getRange("D:D").format.columnWidth = 22;
protocol.getRange("E:E").format.columnWidth = 12;

queue.mergeCells("A1:K1");
queue.getRange("A1").values = [["Held-Out Review Queue (30 questions)"]];
queue.getRange("A1:K1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 15 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
queue.getRange("A2:K2").merge();
queue.getRange("A2").values = [["Yellow cells are reviewer inputs; blue cells are suggested values. Structured graph nodes never count as text chunks."]];
queue.getRange("A2:K2").format = { fill: colors.paleBlue, font: { color: colors.navy }, wrapText: true };
const queueHeaders = [[
  "Review ID", "Slice", "Question", "Status", "Suggested Gold chunk IDs", "Gold evidence chunk IDs",
  "Suggested Graph Path", "Accepted Graph Path Node IDs", "Reviewer Rationale", "Origin", "Evidence Rows",
]];
queue.getRange("A4:K4").values = queueHeaders;
queue.getRange(`A5:K${4 + queueRows.length}`).values = queueRows;
for (let index = 0; index < queueRows.length; index += 1) {
  const excelRow = 5 + index;
  queue.getRange(`K${excelRow}`).formulas = [[`=COUNTIF('Evidence Reader'!$A$5:$A$${4 + evidenceRows.length},A${excelRow})`]];
}
const queueTable = queue.tables.add(`A4:K${4 + queueRows.length}`, true, "HeldOutReviewQueue");
queueTable.style = "TableStyleMedium2";
queue.getRange(`D5:D${4 + queueRows.length}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };
// Only status, accepted evidence/path, and rationale are reviewer inputs.
for (const column of ["D", "F", "H", "I"]) {
  queue.getRange(`${column}5:${column}${4 + queueRows.length}`).format.fill = colors.yellow;
}
for (const column of ["E", "G"]) {
  queue.getRange(`${column}5:${column}${4 + queueRows.length}`).format.fill = colors.paleBlue;
}
queue.getRange(`A5:K${4 + queueRows.length}`).format.verticalAlignment = "top";
queue.getRange(`B5:J${4 + queueRows.length}`).format.wrapText = true;
queue.getRange(`A5:K${4 + queueRows.length}`).format.rowHeight = 84;
queue.getRange(`D5:D${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
queue.getRange(`D5:D${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: colors.orange, font: { bold: true, color: "#9A3412" } } });
queue.getRange(`D5:D${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: colors.red, font: { bold: true, color: "#991B1B" } } });
queue.freezePanes.freezeRows(4);
queue.freezePanes.freezeColumns(2);
const queueWidths = [20, 25, 66, 14, 43, 43, 48, 48, 54, 32, 12];
"ABCDEFGHIJK".split("").forEach((column, index) => { queue.getRange(`${column}:${column}`).format.columnWidth = queueWidths[index]; });

evidence.mergeCells("A1:H1");
evidence.getRange("A1").values = [["Evidence Reader"]];
evidence.getRange("A1:H1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 15 },
  horizontalAlignment: "center",
};
evidence.mergeCells("A2:H2");
evidence.getRange("A2").values = [["Filter by Review ID. Priority 1 contains suggested direct evidence and structured records; Priority 2 contains additional candidates."]];
evidence.getRange("A2:H2").format = { fill: colors.paleBlue, font: { color: colors.navy }, wrapText: true };
evidence.getRange("A4:H4").values = [["Review ID", "Priority", "Evidence Type", "Evidence ID", "Document / Path", "Heading / Record", "Original Source Passage / Structured Record", "Frozen Source File / Provenance"]];
evidence.getRange(`A5:H${4 + evidenceRows.length}`).values = evidenceRows;
const evidenceTable = evidence.tables.add(`A4:H${4 + evidenceRows.length}`, true, "HeldOutEvidenceReader");
evidenceTable.style = "TableStyleMedium2";
evidence.getRange(`A5:H${4 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`C5:H${4 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A5:H${4 + evidenceRows.length}`).format.rowHeight = 108;
evidence.getRange(`B5:B${4 + evidenceRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
evidence.getRange(`B5:B${4 + evidenceRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 2, format: { fill: colors.paleGray, font: { color: colors.gray } } });
evidence.freezePanes.freezeRows(4);
evidence.freezePanes.freezeColumns(2);
const evidenceWidths = [20, 10, 24, 40, 42, 42, 100, 62];
"ABCDEFGH".split("").forEach((column, index) => { evidence.getRange(`${column}:${column}`).format.columnWidth = evidenceWidths[index]; });

await fs.mkdir(outputDir, { recursive: true });
const queueCheck = await workbook.inspect({ kind: "table", range: "Review Queue!A1:K12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 11 });
const evidenceCheck = await workbook.inspect({ kind: "table", range: "Evidence Reader!A1:H12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 8 });
const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(queueCheck.ndjson);
console.log(evidenceCheck.ndjson);
console.log(errorCheck.ndjson);

for (const [sheetName, range, fileName] of [
  ["Protocol", "A1:H10", "preview_protocol.png"],
  ["Review Queue", "A1:K10", "preview_review_queue.png"],
  ["Evidence Reader", "A1:H10", "preview_evidence_reader.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, queueRows: queueRows.length, evidenceRows: evidenceRows.length }, null, 2));

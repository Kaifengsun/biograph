import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const packPath = process.env.REVISION_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_revision_round_2026-07-15.json");
const corpusDir = process.env.FROZEN_CORPUS || path.join(projectRoot, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const outputDir = process.env.REVISION_REVIEW_OUTPUT_DIR || path.join(projectRoot, "outputs/heldout_review_2026-07-15");
const outputPath = process.env.REVISION_REVIEW_OUTPUT || path.join(outputDir, "adaptive_text_first_heldout_revision_round_2026-07-15.xlsx");

const pack = JSON.parse(await fs.readFile(packPath, "utf8"));
const chunks = new Map();
for (const fileName of (await fs.readdir(corpusDir)).filter((name) => name.endsWith("_enriched.json")).sort()) {
  const filePath = path.join(corpusDir, fileName);
  for (const row of JSON.parse(await fs.readFile(filePath, "utf8"))) {
    if (row.chunk_id) chunks.set(String(row.chunk_id), { ...row, frozen_source_file: filePath });
  }
}

const queueRows = [];
const evidenceRows = [];
for (const row of pack.revisions) {
  const proposed = row.proposed_gold_evidence_chunk_ids || [];
  queueRows.push([
    row.revision_id,
    row.query_slice,
    row.original_query,
    row.revised_query,
    "Pending",
    proposed.join("; "),
    proposed.join("; "),
    row.revision_reason,
    row.round1_reviewer_rationale,
    "",
  ]);
  const proposedSet = new Set(proposed);
  for (const chunkId of row.candidate_evidence_chunk_ids || []) {
    const chunk = chunks.get(chunkId);
    if (!chunk) throw new Error(`missing frozen chunk: ${chunkId}`);
    evidenceRows.push([
      row.revision_id,
      proposedSet.has(chunkId) ? 1 : 2,
      proposedSet.has(chunkId) ? "Proposed Gold evidence" : "Additional candidate",
      chunkId,
      chunk.doc_id || "",
      chunk.heading || "",
      chunk.content || "",
      chunk.frozen_source_file,
    ]);
  }
}

const workbook = Workbook.create();
const instructions = workbook.worksheets.add("Instructions");
const queue = workbook.worksheets.add("Revision Queue");
const evidence = workbook.worksheets.add("Evidence Reader");
const colors = {
  navy: "#16324F", paleBlue: "#EAF2FF", yellow: "#FFF4CC", green: "#DCFCE7",
  red: "#FEE2E2", orange: "#FFEDD5", paleGray: "#F1F5F9", gray: "#64748B",
  border: "#CBD5E1", white: "#FFFFFF",
};
for (const sheet of [instructions, queue, evidence]) sheet.showGridLines = false;

instructions.mergeCells("A1:F1");
instructions.getRange("A1").values = [["Held-Out Revision Round: Four-Question Confirmation"]];
instructions.getRange("A1:F1").format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 16 }, horizontalAlignment: "center" };
instructions.getRange("A1:F1").format.rowHeight = 34;
instructions.getRange("A3:B8").values = [
  ["Purpose", "Confirm four questions narrowed according to the first-round reviewer rationale."],
  ["Fast path", "Read Revised Question and Revision Reason. Check Priority 1 evidence only, then select Confirmed if the revision is directly answerable."],
  ["Confirmed", "Accept the revised wording and accepted Gold chunk IDs."],
  ["Revise", "The wording or Gold set still needs a change; explain it in Reviewer Rationale."],
  ["Exclude", "The revised case is still unsuitable for the held-out evaluation."],
  ["Do not execute", "Retrieval remains prohibited until these four revisions are resolved and the complete 30-question set is frozen."],
];
instructions.getRange("A3:A8").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy }, verticalAlignment: "top" };
instructions.getRange("B3:B8").format = { wrapText: true, verticalAlignment: "top" };
instructions.getRange("A3:B8").format.borders = { preset: "insideHorizontal", style: "thin", color: colors.border };
instructions.getRange("D3:E8").values = [["Review summary", "Count"], ["Total", 4], ["Pending", null], ["Confirmed", null], ["Revise", null], ["Exclude", null]];
instructions.getRange("D3:E3").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
instructions.getRange("E5").formulas = [["=COUNTIF('Revision Queue'!$E$5:$E$8,D5)"]];
instructions.getRange("E5:E8").fillDown();
instructions.getRange("A:A").format.columnWidth = 18;
instructions.getRange("B:B").format.columnWidth = 80;
instructions.getRange("C:C").format.columnWidth = 3;
instructions.getRange("D:D").format.columnWidth = 22;
instructions.getRange("E:E").format.columnWidth = 12;

queue.mergeCells("A1:J1");
queue.getRange("A1").values = [["Revision Queue (4 questions)"]];
queue.getRange("A1:J1").format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 15 }, horizontalAlignment: "center" };
queue.mergeCells("A2:J2");
queue.getRange("A2").values = [["Yellow cells are reviewer inputs. Blue cells are proposed values derived from the first-round rationale."]];
queue.getRange("A2:J2").format = { fill: colors.paleBlue, font: { color: colors.navy }, wrapText: true };
queue.getRange("A4:J4").values = [[
  "Revision ID", "Slice", "Original Question", "Revised Question", "Status", "Proposed Gold chunk IDs",
  "Accepted Gold chunk IDs", "Revision Reason", "Round-1 Reviewer Rationale", "Reviewer Rationale",
]];
queue.getRange(`A5:J${4 + queueRows.length}`).values = queueRows;
const queueTable = queue.tables.add(`A4:J${4 + queueRows.length}`, true, "HeldOutRevisionQueue");
queueTable.style = "TableStyleMedium2";
queue.getRange(`E5:E${4 + queueRows.length}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };
for (const column of ["E", "G", "J"]) queue.getRange(`${column}5:${column}${4 + queueRows.length}`).format.fill = colors.yellow;
queue.getRange(`F5:F${4 + queueRows.length}`).format.fill = colors.paleBlue;
queue.getRange(`A5:J${4 + queueRows.length}`).format.verticalAlignment = "top";
queue.getRange(`B5:J${4 + queueRows.length}`).format.wrapText = true;
queue.getRange(`A5:J${4 + queueRows.length}`).format.rowHeight = 116;
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: colors.orange, font: { bold: true, color: "#9A3412" } } });
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: colors.red, font: { bold: true, color: "#991B1B" } } });
queue.freezePanes.freezeRows(4);
queue.freezePanes.freezeColumns(2);
const queueWidths = [22, 24, 64, 68, 14, 44, 44, 56, 56, 48];
"ABCDEFGHIJ".split("").forEach((column, position) => { queue.getRange(`${column}:${column}`).format.columnWidth = queueWidths[position]; });

evidence.mergeCells("A1:H1");
evidence.getRange("A1").values = [["Revision Evidence Reader"]];
evidence.getRange("A1:H1").format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 15 }, horizontalAlignment: "center" };
evidence.mergeCells("A2:H2");
evidence.getRange("A2").values = [["Filter by Revision ID. Priority 1 is the proposed Gold evidence; Priority 2 is shown only for context."]];
evidence.getRange("A2:H2").format = { fill: colors.paleBlue, font: { color: colors.navy }, wrapText: true };
evidence.getRange("A4:H4").values = [["Revision ID", "Priority", "Evidence Type", "Chunk ID", "Document", "Heading", "Original Source Passage", "Frozen Source File"]];
evidence.getRange(`A5:H${4 + evidenceRows.length}`).values = evidenceRows;
const evidenceTable = evidence.tables.add(`A4:H${4 + evidenceRows.length}`, true, "HeldOutRevisionEvidence");
evidenceTable.style = "TableStyleMedium2";
evidence.getRange(`A5:H${4 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`C5:H${4 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A5:H${4 + evidenceRows.length}`).format.rowHeight = 112;
evidence.getRange(`B5:B${4 + evidenceRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
evidence.getRange(`B5:B${4 + evidenceRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 2, format: { fill: colors.paleGray, font: { color: colors.gray } } });
evidence.freezePanes.freezeRows(4);
evidence.freezePanes.freezeColumns(2);
const evidenceWidths = [22, 10, 24, 40, 36, 44, 100, 62];
"ABCDEFGH".split("").forEach((column, position) => { evidence.getRange(`${column}:${column}`).format.columnWidth = evidenceWidths[position]; });

await fs.mkdir(outputDir, { recursive: true });
const queueCheck = await workbook.inspect({ kind: "table", range: "Revision Queue!A1:J8", include: "values,formulas", tableMaxRows: 8, tableMaxCols: 10, maxChars: 20000 });
const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(queueCheck.ndjson);
console.log(errorCheck.ndjson);
for (const [sheetName, range, fileName] of [
  ["Instructions", "A1:F8", "preview_revision_instructions.png"],
  ["Revision Queue", "A1:J8", "preview_revision_queue.png"],
  ["Evidence Reader", "A1:H10", "preview_revision_evidence.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, queue_rows: queueRows.length, evidence_rows: evidenceRows.length }, null, 2));

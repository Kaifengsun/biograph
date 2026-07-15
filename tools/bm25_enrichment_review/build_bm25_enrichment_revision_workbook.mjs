import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const outputDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15");
const packPath = path.join(root, "data/eval/bm25_enrichment_heldout_revision_round_2026-07-15.json");
const outputPath = path.join(outputDir, "BM25与语料富化消融_8题修订二次确认表_2026-07-15.xlsx");
const pack = JSON.parse(await fs.readFile(packPath, "utf8"));

const queueRows = pack.revisions.map((row) => [row.revision_id, row.query_slice, row.original_question, row.proposed_revised_question, row.gold_evidence_chunk_ids.join("; "), "Pending", row.final_revised_question, ""]);
const evidenceRows = pack.revisions.flatMap((row) => row.evidence.map((item) => [row.revision_id, row.proposed_revised_question, item.chunk_id, item.doc_id, [item.parents_context, item.heading].filter(Boolean).join(" > "), item.original_source_passage, item.table_source_text, item.table_summary_reference_only]));

const wb = Workbook.create();
const guide = wb.worksheets.add("确认说明");
const queue = wb.worksheets.add("Revision Queue");
const evidence = wb.worksheets.add("Evidence Reader");
const c = { navy: "#17324D", paleBlue: "#EAF2FF", yellow: "#FFF4CC", green: "#DCFCE7", orange: "#FFEDD5", red: "#FEE2E2", purple: "#F3E8FF", border: "#CBD5E1", white: "#FFFFFF" };
for (const sheet of [guide, queue, evidence]) sheet.showGridLines = false;

guide.mergeCells("A1:E1");
guide.getRange("A1").values = [["8 题修订二次确认"]];
guide.getRange("A1:E1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 16 }, horizontalAlignment: "center" };
guide.getRange("A3:B7").values = [
  ["目的", "确认第一轮收窄后的 8 个题目是否准确对应冻结原文。已 Confirmed 的另外 22 题无需重复审核。"],
  ["Confirmed", "认可 Proposed Revised Question。将 Status 改为 Confirmed；其余内容无需修改。"],
  ["Revise", "仍需修改。将 Status 改为 Revise，并直接修改 Final Revised Question，补充 Reviewer Note。"],
  ["Exclude", "修订后仍不适合评测。将 Status 改为 Exclude，并写明原因。"],
  ["证据", "如需复核，可在 Evidence Reader 按 Revision ID 查看原文；表格摘要仍然只供理解。"],
];
guide.getRange("A3:A7").format = { fill: c.paleBlue, font: { bold: true, color: c.navy }, verticalAlignment: "top" };
guide.getRange("B3:B7").format = { wrapText: true, verticalAlignment: "top" };
guide.getRange("A3:B7").format.borders = { preset: "insideHorizontal", style: "thin", color: c.border };
guide.getRange("A:A").format.columnWidth = 18;
guide.getRange("B:B").format.columnWidth = 85;

queue.mergeCells("A1:H1");
queue.getRange("A1").values = [["Revision Queue：8 题二次确认"]];
queue.getRange("A1:H1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 15 }, horizontalAlignment: "center" };
queue.mergeCells("A2:H2");
queue.getRange("A2").values = [["若认可修订题目，只需把 Status 改为 Confirmed；黄色列可编辑。"]];
queue.getRange("A2:H2").format = { fill: c.paleBlue, font: { color: c.navy }, wrapText: true };
queue.getRange("A4:H4").values = [["Revision ID", "题型", "Original Question", "Proposed Revised Question", "Gold chunk IDs", "Status", "Final Revised Question", "Reviewer Note"]];
queue.getRange(`A5:H${4 + queueRows.length}`).values = queueRows;
queue.tables.add(`A4:H${4 + queueRows.length}`, true, "BM25EnrichmentRevisionQueue").style = "TableStyleMedium2";
queue.getRange(`F5:F${4 + queueRows.length}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };
for (const col of ["F", "G", "H"]) queue.getRange(`${col}5:${col}${4 + queueRows.length}`).format.fill = c.yellow;
queue.getRange(`D5:D${4 + queueRows.length}`).format.fill = c.paleBlue;
queue.getRange(`E5:E${4 + queueRows.length}`).format.fill = c.purple;
queue.getRange(`A5:H${4 + queueRows.length}`).format.verticalAlignment = "top";
queue.getRange(`B5:H${4 + queueRows.length}`).format.wrapText = true;
queue.getRange(`A5:H${4 + queueRows.length}`).format.rowHeight = 105;
queue.getRange(`F5:F${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: c.green, font: { bold: true, color: "#166534" } } });
queue.getRange(`F5:F${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: c.orange, font: { bold: true, color: "#9A3412" } } });
queue.getRange(`F5:F${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: c.red, font: { bold: true, color: "#991B1B" } } });
queue.freezePanes.freezeRows(4);
queue.freezePanes.freezeColumns(2);
const qWidths = [18, 20, 60, 68, 46, 14, 68, 52];
"ABCDEFGH".split("").forEach((col, i) => { queue.getRange(`${col}:${col}`).format.columnWidth = qWidths[i]; });

evidence.mergeCells("A1:H1");
evidence.getRange("A1").values = [["Evidence Reader：修订题原文"]];
evidence.getRange("A1:H1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 15 }, horizontalAlignment: "center" };
evidence.getRange("A3:H3").values = [["Revision ID", "Revised Question", "Chunk ID", "Document", "Heading / Context", "Original Source Passage", "Table Source Text", "Table Summary（仅供参考）"]];
evidence.getRange(`A4:H${3 + evidenceRows.length}`).values = evidenceRows;
evidence.tables.add(`A3:H${3 + evidenceRows.length}`, true, "BM25EnrichmentRevisionEvidence").style = "TableStyleMedium2";
evidence.getRange(`A4:H${3 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`B4:H${3 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A4:H${3 + evidenceRows.length}`).format.rowHeight = 130;
evidence.getRange(`F4:F${3 + evidenceRows.length}`).format.fill = c.paleBlue;
evidence.getRange(`G4:G${3 + evidenceRows.length}`).format.fill = c.green;
evidence.getRange(`H4:H${3 + evidenceRows.length}`).format.fill = c.purple;
evidence.freezePanes.freezeRows(3);
evidence.freezePanes.freezeColumns(1);
const eWidths = [18, 64, 38, 20, 48, 94, 80, 62];
"ABCDEFGH".split("").forEach((col, i) => { evidence.getRange(`${col}:${col}`).format.columnWidth = eWidths[i]; });

await fs.mkdir(outputDir, { recursive: true });
const checks = [];
checks.push((await wb.inspect({ kind: "table", range: "Revision Queue!A1:H13", include: "values,formulas", tableMaxRows: 13, tableMaxCols: 8 })).ndjson);
checks.push((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" })).ndjson);
await fs.writeFile(path.join(outputDir, "revision_workbook_inspection.ndjson"), checks.join("\n"), "utf8");
for (const [sheetName, range, fileName] of [["确认说明", "A1:E7", "preview_revision_确认说明.png"], ["Revision Queue", "A1:H13", "preview_revision_queue.png"], ["Evidence Reader", "A1:H9", "preview_revision_evidence.png"]]) {
  const image = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await image.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, revisions: queueRows.length, evidenceRows: evidenceRows.length }, null, 2));

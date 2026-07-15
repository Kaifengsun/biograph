import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const outputDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15");
const dataPath = path.join(outputDir, "review_workbook_data.json");
const outputPath = path.join(outputDir, "BM25与语料富化消融_30题带原文简化审核表_2026-07-15.xlsx");
const { pack } = JSON.parse(await fs.readFile(dataPath, "utf8"));

const queueRows = pack.queries.map((row) => [
  row.review_id,
  row.query_slice,
  row.question,
  row.proposed_gold_evidence_chunk_ids.join("; "),
  "Pending",
  "",
  row.final_gold_evidence_chunk_ids.join("; "),
  "",
  null,
  "PASS",
]);
const evidenceRows = pack.queries.flatMap((row) => row.evidence.map((item) => [
  row.review_id,
  row.query_slice,
  row.question,
  item.evidence_order,
  item.chunk_id,
  item.doc_id,
  [item.parents_context, item.heading].filter(Boolean).join(" > "),
  item.original_source_passage,
  item.table_source_text,
  item.table_summary_reference_only,
  item.frozen_source_file,
]));

const wb = Workbook.create();
const instructions = wb.worksheets.add("审核说明");
const queue = wb.worksheets.add("Review Queue");
const evidence = wb.worksheets.add("Evidence Reader");
const c = {
  navy: "#17324D", blue: "#2563EB", paleBlue: "#EAF2FF", yellow: "#FFF4CC",
  green: "#DCFCE7", orange: "#FFEDD5", red: "#FEE2E2", gray: "#64748B",
  paleGray: "#F1F5F9", border: "#CBD5E1", white: "#FFFFFF", purple: "#F3E8FF",
};
for (const sheet of [instructions, queue, evidence]) sheet.showGridLines = false;

instructions.mergeCells("A1:F1");
instructions.getRange("A1").values = [["BM25 基线与语料富化消融：30 题人工审核"]];
instructions.getRange("A1:F1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 16 }, horizontalAlignment: "center", verticalAlignment: "center" };
instructions.getRange("A1:F1").format.rowHeight = 36;
instructions.getRange("A3:B11").values = [
  ["你只需要做什么", "按 Review ID 审核 30 题。先在 Evidence Reader 过滤同一 ID，阅读 Original Source Passage；表格题还要阅读 Table Source Text。然后回到 Review Queue 填写状态。"],
  ["Confirmed", "原文可以直接回答问题。通常只需把 Status 改为 Confirmed；Final Gold chunk IDs 已预填。"],
  ["Revise", "原文有价值，但题目表述过宽、过窄或不准确。把 Status 改为 Revise，并在 Revised Question 写出建议题目，在 Reviewer Note 说明原因。"],
  ["Exclude", "现有原文无法直接回答，或该题不适合做检索评测。把 Status 改为 Exclude，并简要说明原因。"],
  ["表格题", "Table Source Text 是从冻结表格直接转换出的原始表格文本，属于证据；Table Summary 仅供理解，不作为人工判定依据。"],
  ["多证据题", "文档结构题和跨文档题会有多行原文。请把同一 Review ID 的全部证据读完，再判断问题是否完整可回答。"],
  ["不要做的事", "不用运行检索，不用寻找其他 chunk，也不用判断 BM25 或向量模型效果。当前只确认问题与预设原文是否匹配。"],
  ["冻结规则", "这 30 题与此前两批金标准 chunk 零重叠；在你的审核完成前，不会用于任何检索实验。"],
  ["填写区域", "Review Queue 中黄色列是你需要编辑的列；蓝色和紫色列是系统预填信息。"],
];
instructions.getRange("A3:A11").format = { fill: c.paleBlue, font: { bold: true, color: c.navy }, verticalAlignment: "top" };
instructions.getRange("B3:B11").format = { wrapText: true, verticalAlignment: "top" };
instructions.getRange("A3:B11").format.borders = { preset: "insideHorizontal", style: "thin", color: c.border };
instructions.getRange("D3:E9").values = [["审核进度", "数量"], ["总题数", null], ["Pending", null], ["Confirmed", null], ["Revise", null], ["Exclude", null], ["已完成", null]];
instructions.getRange("D3:E3").format = { fill: c.navy, font: { bold: true, color: c.white } };
instructions.getRange("E4").formulas = [["=COUNTA('Review Queue'!$A$5:$A$34)"]];
instructions.getRange("E5").formulas = [["=COUNTIF('Review Queue'!$E$5:$E$34,D5)"]];
instructions.getRange("E5:E8").fillDown();
instructions.getRange("E9").formulas = [["=SUM(E6:E8)"]];
instructions.getRange("D4:E9").format.borders = { preset: "insideHorizontal", style: "thin", color: c.border };
instructions.getRange("E4:E9").format.numberFormat = "0";
instructions.getRange("A:A").format.columnWidth = 20;
instructions.getRange("B:B").format.columnWidth = 83;
instructions.getRange("C:C").format.columnWidth = 3;
instructions.getRange("D:D").format.columnWidth = 18;
instructions.getRange("E:E").format.columnWidth = 11;

queue.mergeCells("A1:J1");
queue.getRange("A1").values = [["Review Queue：30 题审核队列"]];
queue.getRange("A1:J1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 15 }, horizontalAlignment: "center", verticalAlignment: "center" };
queue.mergeCells("A2:J2");
queue.getRange("A2").values = [["先到 Evidence Reader 按 Review ID 查看全部原文，再填写黄色列 E/F/H；只有发现证据 ID 需要调整时才修改 G。"]];
queue.getRange("A2:J2").format = { fill: c.paleBlue, font: { color: c.navy }, wrapText: true };
queue.getRange("A4:J4").values = [["Review ID", "题型", "Question", "Proposed Gold chunk IDs", "Status", "Revised Question（仅 Revise）", "Final Gold chunk IDs", "Reviewer Note", "证据行数", "旧测试集重叠检查"]];
queue.getRange(`A5:J${4 + queueRows.length}`).values = queueRows;
for (let i = 0; i < queueRows.length; i += 1) {
  const row = i + 5;
  queue.getRange(`I${row}`).formulas = [[`=COUNTIF('Evidence Reader'!$A$5:$A$${4 + evidenceRows.length},A${row})`]];
}
const queueTable = queue.tables.add(`A4:J${4 + queueRows.length}`, true, "BM25EnrichmentReviewQueue");
queueTable.style = "TableStyleMedium2";
queue.getRange(`E5:E${4 + queueRows.length}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };
for (const column of ["E", "F", "H"]) queue.getRange(`${column}5:${column}${4 + queueRows.length}`).format.fill = c.yellow;
queue.getRange(`G5:G${4 + queueRows.length}`).format.fill = c.yellow;
queue.getRange(`D5:D${4 + queueRows.length}`).format.fill = c.paleBlue;
queue.getRange(`J5:J${4 + queueRows.length}`).format.fill = c.purple;
queue.getRange(`A5:J${4 + queueRows.length}`).format.verticalAlignment = "top";
queue.getRange(`B5:J${4 + queueRows.length}`).format.wrapText = true;
queue.getRange(`A5:J${4 + queueRows.length}`).format.rowHeight = 92;
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: c.green, font: { bold: true, color: "#166534" } } });
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: c.orange, font: { bold: true, color: "#9A3412" } } });
queue.getRange(`E5:E${4 + queueRows.length}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: c.red, font: { bold: true, color: "#991B1B" } } });
queue.freezePanes.freezeRows(4);
queue.freezePanes.freezeColumns(2);
const qWidths = [16, 20, 66, 48, 14, 62, 48, 56, 11, 18];
"ABCDEFGHIJ".split("").forEach((col, i) => { queue.getRange(`${col}:${col}`).format.columnWidth = qWidths[i]; });

evidence.mergeCells("A1:K1");
evidence.getRange("A1").values = [["Evidence Reader：冻结原文阅读区"]];
evidence.getRange("A1:K1").format = { fill: c.navy, font: { bold: true, color: c.white, size: 15 }, horizontalAlignment: "center" };
evidence.mergeCells("A2:K2");
evidence.getRange("A2").values = [["按 Review ID 过滤。Original Source Passage 是主要证据；表格题同时阅读 Table Source Text。Table Summary 仅供理解，不作为证据。"]];
evidence.getRange("A2:K2").format = { fill: c.paleBlue, font: { color: c.navy }, wrapText: true };
evidence.getRange("A4:K4").values = [["Review ID", "题型", "Question", "证据顺序", "Chunk ID", "Document", "Heading / Parent Context", "Original Source Passage", "Table Source Text（原始证据）", "Table Summary（仅供参考）", "Frozen Source File"]];
evidence.getRange(`A5:K${4 + evidenceRows.length}`).values = evidenceRows;
const evidenceTable = evidence.tables.add(`A4:K${4 + evidenceRows.length}`, true, "BM25EnrichmentEvidenceReader");
evidenceTable.style = "TableStyleMedium2";
evidence.getRange(`A5:K${4 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`B5:K${4 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A5:K${4 + evidenceRows.length}`).format.rowHeight = 128;
evidence.getRange(`H5:H${4 + evidenceRows.length}`).format.fill = c.paleBlue;
evidence.getRange(`I5:I${4 + evidenceRows.length}`).format.fill = c.green;
evidence.getRange(`J5:J${4 + evidenceRows.length}`).format.fill = c.purple;
evidence.freezePanes.freezeRows(4);
evidence.freezePanes.freezeColumns(2);
const eWidths = [16, 20, 58, 11, 38, 20, 44, 92, 82, 62, 58];
"ABCDEFGHIJK".split("").forEach((col, i) => { evidence.getRange(`${col}:${col}`).format.columnWidth = eWidths[i]; });

await fs.mkdir(outputDir, { recursive: true });
const inspections = [];
inspections.push((await wb.inspect({ kind: "table", range: "Review Queue!A1:J10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 10 })).ndjson);
inspections.push((await wb.inspect({ kind: "table", range: "Evidence Reader!A1:K10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 11 })).ndjson);
inspections.push((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" })).ndjson);
await fs.writeFile(path.join(outputDir, "workbook_inspection.ndjson"), inspections.join("\n"), "utf8");

for (const [sheetName, range, fileName] of [
  ["审核说明", "A1:F11", "preview_审核说明.png"],
  ["Review Queue", "A1:J10", "preview_review_queue.png"],
  ["Evidence Reader", "A1:K9", "preview_evidence_reader.png"],
]) {
  const image = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await image.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, queueRows: queueRows.length, evidenceRows: evidenceRows.length }, null, 2));

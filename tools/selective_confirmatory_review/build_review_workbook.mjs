import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "../..");
const inputPath = path.join(root, "outputs/selective_source_chunk_reranker_confirmatory_review_2026-07-16/review_payload.json");
const outputDir = path.join(root, "outputs/selective_source_chunk_reranker_confirmatory_review_2026-07-16");
const outputPath = path.join(outputDir, "选择性重排_30题全新确认集_带原文盲审表_2026-07-16.xlsx");
const pack = JSON.parse(await fs.readFile(inputPath, "utf8"));

const workbook = Workbook.create();
const instructions = workbook.worksheets.add("说明");
const queue = workbook.worksheets.add("Review Queue");
const reader = workbook.worksheets.add("Evidence Reader");

const navy = "#17365D";
const blue = "#D9EAF7";
const pale = "#F4F7FA";
const green = "#E2F0D9";
const amber = "#FFF2CC";
const red = "#FCE4D6";
const border = "#B8C4D1";

instructions.showGridLines = false;
instructions.getRange("A1:F1").merge();
instructions.getRange("A1").values = [["选择性重排：30题全新确认集盲审说明"]];
instructions.getRange("A1:F1").format = {
  fill: navy, font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center", verticalAlignment: "center",
};
instructions.getRange("A1:F1").format.rowHeight = 34;
const notes = [
  ["目的", "这30题与既有90题没有问题文本重叠，用于最终确认BM25默认、表格门控重排策略。"],
  ["盲审", "候选段落已按固定种子打乱；表中不显示BM25、向量、重排方法、分数或排名。"],
  ["步骤1", "在 Review Queue 按 Review ID 查看问题。"],
  ["步骤2", "在 Evidence Reader 筛选相同 Review ID，阅读该题的全部匿名候选原文。"],
  ["步骤3", "若至少一段原文可以直接支持问题，状态选 Confirmed，并在 Gold Passage IDs 填写所有支持段落编号，例如 P03; P08。"],
  ["Revise", "问题基本合理但措辞超出证据、范围过宽或需要改写时选择 Revise，并在 Revision Note 写明建议。"],
  ["Exclude", "没有候选段落能够支持问题，或问题本身不适合作为检索题时选择 Exclude。"],
  ["注意", "不要根据常识判断，只判断表中冻结原文能否支持问题。跨文档题通常需要两个或以上Passage共同支持。"],
];
instructions.getRange(`A3:B${notes.length + 2}`).values = notes;
instructions.getRange(`A3:A${notes.length + 2}`).format = { fill: blue, font: { bold: true, color: navy }, verticalAlignment: "top" };
instructions.getRange(`B3:B${notes.length + 2}`).format = { fill: pale, wrapText: true, verticalAlignment: "top" };
instructions.getRange(`A3:B${notes.length + 2}`).format.borders = { preset: "all", style: "thin", color: border };
instructions.getRange("A:A").format.columnWidth = 16;
instructions.getRange("B:B").format.columnWidth = 95;
instructions.getRange(`A3:B${notes.length + 2}`).format.rowHeight = 42;
instructions.freezePanes.freezeRows(1);

queue.showGridLines = false;
const queueHeaders = [["Review ID", "Query Slice", "Question", "Status", "Gold Passage IDs", "Revision Note"]];
const queueRows = pack.questions.map((question) => [
  question.annotation_id, question.query_slice, question.query, "Pending", "", "",
]);
queue.getRange(`A1:F${queueRows.length + 1}`).values = [...queueHeaders, ...queueRows];
queue.getRange("A1:F1").format = {
  fill: navy, font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
};
queue.getRange(`A2:F${queueRows.length + 1}`).format = { verticalAlignment: "top", wrapText: true };
queue.getRange(`A1:F${queueRows.length + 1}`).format.borders = { preset: "inside", style: "thin", color: "#D9E1E8" };
queue.getRange(`D2:D${queueRows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] },
};
queue.getRange(`D2:D${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: green, font: { color: "#375623", bold: true } } });
queue.getRange(`D2:D${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: amber, font: { color: "#7F6000", bold: true } } });
queue.getRange(`D2:D${queueRows.length + 1}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: red, font: { color: "#9C0006", bold: true } } });
queue.tables.add(`A1:F${queueRows.length + 1}`, true, "ReviewQueueTable");
queue.getRange("A:A").format.columnWidth = 15;
queue.getRange("B:B").format.columnWidth = 20;
queue.getRange("C:C").format.columnWidth = 72;
queue.getRange("D:D").format.columnWidth = 16;
queue.getRange("E:E").format.columnWidth = 24;
queue.getRange("F:F").format.columnWidth = 55;
queue.getRange(`A2:F${queueRows.length + 1}`).format.rowHeight = 58;
queue.freezePanes.freezeRows(1);
queue.freezePanes.freezeColumns(2);

reader.showGridLines = false;
const readerHeaders = [["Review ID", "Passage ID", "Document", "Heading", "Original Source Passage", "Frozen Source File"]];
const readerRows = [];
for (const question of pack.questions) {
  for (const passage of question.passages) {
    readerRows.push([
      question.annotation_id, passage.passage_id, passage.doc_id, passage.heading,
      passage.original_source_passage, passage.frozen_source_file,
    ]);
  }
}
reader.getRange(`A1:F${readerRows.length + 1}`).values = [...readerHeaders, ...readerRows];
reader.getRange("A1:F1").format = {
  fill: navy, font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
};
reader.getRange(`A2:F${readerRows.length + 1}`).format = { verticalAlignment: "top", wrapText: true };
reader.getRange(`A1:F${readerRows.length + 1}`).format.borders = { preset: "inside", style: "thin", color: "#D9E1E8" };
reader.tables.add(`A1:F${readerRows.length + 1}`, true, "EvidenceReaderTable");
reader.getRange("A:A").format.columnWidth = 15;
reader.getRange("B:B").format.columnWidth = 12;
reader.getRange("C:C").format.columnWidth = 26;
reader.getRange("D:D").format.columnWidth = 46;
reader.getRange("E:E").format.columnWidth = 105;
reader.getRange("F:F").format.columnWidth = 42;
reader.getRange(`A2:F${readerRows.length + 1}`).format.rowHeight = 92;
reader.freezePanes.freezeRows(1);
reader.freezePanes.freezeColumns(2);

await fs.mkdir(outputDir, { recursive: true });
const previewRanges = [
  ["说明", `A1:B${notes.length + 2}`, "preview_说明.png"],
  ["Review Queue", "A1:F12", "preview_Review_Queue.png"],
  ["Evidence Reader", "A1:F16", "preview_Evidence_Reader_top.png"],
  ["Evidence Reader", `A${Math.max(2, Math.floor(readerRows.length / 2))}:F${Math.max(16, Math.floor(readerRows.length / 2) + 14)}`, "preview_Evidence_Reader_middle.png"],
];
for (const [sheetName, range, fileName] of previewRanges) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
const check = await workbook.inspect({ kind: "table", range: "Review Queue!A1:F8", include: "values,formulas", tableMaxRows: 8, tableMaxCols: 6 });
await fs.writeFile(path.join(outputDir, "workbook_inspect.ndjson"), check.ndjson, "utf8");
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.writeFile(path.join(outputDir, "formula_error_scan.ndjson"), errors.ndjson, "utf8");
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(JSON.stringify({ outputPath, questionCount: pack.questions.length, passageCount: readerRows.length }, null, 2));

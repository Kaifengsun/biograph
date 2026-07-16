import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const disagreementPath = process.argv[2];
const reportPath = process.argv[3];
const outputPath = process.argv[4];
if (!disagreementPath || !reportPath || !outputPath) {
  throw new Error("usage: node build_adjudication_workbook.mjs <disagreements.json> <report.json> <output.xlsx>");
}
const disagreements = JSON.parse(await fs.readFile(disagreementPath, "utf8"));
const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
const outputDir = path.dirname(outputPath);
const previewDir = path.join(outputDir, "qa_previews_adjudication");

const COLORS = {
  navy: "#17365D",
  blue: "#D9EAF7",
  input: "#FFF2CC",
  pale: "#F4F7FA",
  green: "#E2F0D9",
  red: "#FCE4D6",
  white: "#FFFFFF",
  border: "#B7C9DC",
  text: "#1F2937",
};
const questionLabels = ["Answerable", "Needs Revision", "Invalid"];
const completenessLabels = ["Complete", "Incomplete", "Unclear"];
const passageLabels = ["Sufficient", "Required Component", "Context Only", "Not Supporting", "Unclear"];

function title(sheet, heading, subtitle, columns) {
  sheet.showGridLines = false;
  const last = String.fromCharCode(64 + columns);
  sheet.getRange(`A1:${last}1`).merge();
  sheet.getRange("A1").values = [[heading]];
  sheet.getRange("A1").format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white, size: 16 }, rowHeight: 30 };
  sheet.getRange(`A2:${last}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = { fill: COLORS.blue, font: { italic: true, color: COLORS.text }, wrapText: true, rowHeight: 34 };
}

function tableStyle(sheet, fullRange, headerRange) {
  fullRange.format = { wrapText: true, verticalAlignment: "top", font: { color: COLORS.text, size: 10 }, borders: { preset: "all", style: "thin", color: COLORS.border } };
  headerRange.format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white, size: 10 }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, rowHeight: 36, borders: { preset: "all", style: "thin", color: COLORS.border } };
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    const column = String.fromCharCode(65 + index);
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  });
}

function addOverview(workbook) {
  const sheet = workbook.worksheets.add("操作与统计");
  title(sheet, "双人标注分歧联合裁决", "仅处理会影响最终题目资格或核心 Gold 的分歧；黄色单元格由两位审核者讨论后共同填写。", 5);
  const core = report.agreement.passage_core_binary;
  const rows = [
    ["项目", "结果", "解释", "需处理", "操作"],
    ["问题级一致率", report.agreement.question_status.exact_agreement, "58/60 题初始判断一致", report.counts.question_disagreements, "到“问题级裁决”填写最终状态与完整性"],
    ["核心 Gold 一致率", core.exact_agreement, "Sufficient/Required Component 合并为 Gold", report.counts.core_passage_disagreements, "到“核心证据裁决”填写 Final Passage Label"],
    ["Cohen's κ", core.cohen_kappa, "核心 Gold 二分类，未仲裁初始标签", "-", "论文报告该初始一致性，不用裁决后标签重算替代"],
    ["Gwet AC1", core.gwet_ac1, "对高一致率和类别不平衡更稳定", "-", "与 κ 同时报告"],
    ["Positive agreement", core.positive_agreement, "双方对 Gold 的正一致率", "-", "作为补充指标"],
    ["A 漏标", report.counts.missing_passages_a, "不是意见分歧，但必须补齐", report.counts.missing_passages_a, "已放入“核心证据裁决”"],
  ];
  sheet.getRange(`A4:E${3 + rows.length}`).values = rows;
  tableStyle(sheet, sheet.getRange(`A4:E${3 + rows.length}`), sheet.getRange("A4:E4"));
  sheet.getRange("B5:B9").setNumberFormat("0.000");
  sheet.getRange("B10").setNumberFormat("0");
  setWidths(sheet, [27, 16, 54, 14, 58]);

  const instructions = [
    ["联合裁决步骤"],
    ["1. 两位审核者只讨论本工作簿列出的项目，不修改此前独立完成的原始文件。"],
    ["2. 先完成“问题级裁决”，再完成“核心证据裁决”。"],
    ["3. 最终标签必须依据 Frozen Source Passage，而不是依据某位审核者身份。"],
    ["4. 若无法达成一致，选择 Unresolved；该题或片段将按预注册规则从正式指标中排除或作为 unjudged 处理。"],
    ["5. 只填写黄色列，不修改 A/B 初始标签和原文。"],
  ];
  sheet.getRange(`A13:E${12 + instructions.length}`).merge(true);
  sheet.getRange(`A13:A${12 + instructions.length}`).values = instructions;
  sheet.getRange(`A13:E${12 + instructions.length}`).format = { wrapText: true, fill: COLORS.pale, borders: { preset: "all", style: "thin", color: COLORS.border }, rowHeight: 28 };
  sheet.getRange("A13:E13").format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white }, borders: { preset: "all", style: "thin", color: COLORS.border } };
  sheet.freezePanes.freezeRows(4);
}

function addQuestionAdjudication(workbook) {
  const sheet = workbook.worksheets.add("问题级裁决");
  title(sheet, "问题级裁决", "两题存在 Answerable/Complete 与 Needs Revision/Incomplete 分歧。请共同确定最终判断。", 12);
  const headers = [["序号", "Review ID", "题型", "Question", "A Status", "A Completeness", "A Note", "B Status", "B Completeness", "B Note", "Final Status*", "Final Completeness*"]];
  const rows = disagreements.question_disagreements.map((row, index) => [
    index + 1, row.query_id, row.query_slice, row.question,
    row.a.question_status, row.a.evidence_set_completeness, row.a.reviewer_note,
    row.b.question_status, row.b.evidence_set_completeness, row.b.reviewer_note,
    "", "",
  ]);
  sheet.getRange(`A4:L${4 + rows.length}`).values = [...headers, ...rows];
  tableStyle(sheet, sheet.getRange(`A4:L${4 + rows.length}`), sheet.getRange("A4:L4"));
  sheet.getRange(`K5:L${4 + rows.length}`).format.fill = COLORS.input;
  sheet.getRange(`K5:K${4 + rows.length}`).dataValidation = { rule: { type: "list", values: [...questionLabels, "Unresolved"] } };
  sheet.getRange(`L5:L${4 + rows.length}`).dataValidation = { rule: { type: "list", values: [...completenessLabels, "Unresolved"] } };
  setWidths(sheet, [7, 18, 20, 68, 18, 20, 46, 18, 20, 46, 20, 22]);
  sheet.getRange(`A5:L${4 + rows.length}`).format.rowHeight = 88;
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
}

function addPassageAdjudication(workbook) {
  const sheet = workbook.worksheets.add("核心证据裁决");
  title(sheet, "核心证据裁决", "31 条核心 Gold/非 Gold 分歧，加 1 条 A 漏标。请逐行依据冻结原文确定最终 Passage Label。", 14);
  const headers = [["序号", "Review ID", "题型", "Question", "Passage ID", "Source Document", "Heading", "Frozen Source Passage", "A Label", "A Note", "B Label", "B Note", "原因", "Final Passage Label*"]];
  const rows = disagreements.passage_disagreements.map((row, index) => [
    index + 1, row.query_id, row.query_slice, row.question, row.passage_id,
    row.source_document, row.heading, row.frozen_source_passage,
    row.a_label || "[Missing]", row.a_note, row.b_label || "[Missing]", row.b_note,
    row.reason, "",
  ]);
  sheet.getRange(`A4:N${4 + rows.length}`).values = [...headers, ...rows];
  tableStyle(sheet, sheet.getRange(`A4:N${4 + rows.length}`), sheet.getRange("A4:N4"));
  sheet.getRange(`N5:N${4 + rows.length}`).format.fill = COLORS.input;
  sheet.getRange(`N5:N${4 + rows.length}`).dataValidation = { rule: { type: "list", values: [...passageLabels, "Unresolved"] } };
  sheet.getRange(`I5:I${4 + rows.length}`).format.fill = COLORS.blue;
  sheet.getRange(`K5:K${4 + rows.length}`).format.fill = COLORS.green;
  sheet.getRange(`M5:M${4 + rows.length}`).format.fill = COLORS.red;
  setWidths(sheet, [7, 18, 20, 55, 16, 24, 34, 86, 20, 40, 20, 40, 24, 24]);
  sheet.getRange(`A5:N${4 + rows.length}`).format.rowHeight = 96;
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
}

function addLabelGuide(workbook) {
  const sheet = workbook.worksheets.add("标签说明");
  title(sheet, "联合裁决标签说明", "最终标签定义与初始独立标注保持一致。", 3);
  const rows = [
    ["字段", "标签", "定义"],
    ["Question", "Answerable", "冻结候选原文可以完整回答当前问题。"],
    ["Question", "Needs Revision", "主题有效，但题干范围、前提或措辞需要修订。"],
    ["Question", "Invalid", "问题包含错误前提或无法通过有限修订成立。"],
    ["Completeness", "Complete", "候选集合包含完整回答所需的全部证据。"],
    ["Completeness", "Incomplete", "存在部分证据，但缺少重要组成部分。"],
    ["Passage", "Sufficient", "该片段单独足以完整回答问题。"],
    ["Passage", "Required Component", "该片段是多片段联合回答中不可缺少的一部分。"],
    ["Passage", "Context Only", "提供背景，但不是回答所必需的核心证据。"],
    ["Passage", "Not Supporting", "不能支持该问题的答案。"],
    ["Any", "Unresolved", "两位审核者讨论后仍无法达成一致。"],
  ];
  sheet.getRange(`A4:C${3 + rows.length}`).values = rows;
  tableStyle(sheet, sheet.getRange(`A4:C${3 + rows.length}`), sheet.getRange("A4:C4"));
  setWidths(sheet, [24, 26, 82]);
  sheet.freezePanes.freezeRows(4);
}

const workbook = Workbook.create();
addOverview(workbook);
addQuestionAdjudication(workbook);
addPassageAdjudication(workbook);
addLabelGuide(workbook);
await fs.mkdir(outputDir, { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const inspection = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
if (!JSON.stringify(inspection).includes("核心证据裁决")) throw new Error("workbook inspection failed");
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["操作与统计", "问题级裁决", "核心证据裁决", "标签说明"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.9, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
console.log(outputPath);

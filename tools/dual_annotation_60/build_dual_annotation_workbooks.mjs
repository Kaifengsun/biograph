import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const registryPath = process.argv[2] || path.join(root, "outputs/dual_annotation_60_2026-07-15/dual_annotation_60_registry.json");
const outputDir = process.argv[3] || path.dirname(registryPath);
const previewDir = path.join(outputDir, "qa_previews");
const registry = JSON.parse(await fs.readFile(registryPath, "utf8"));

const COLORS = {
  navy: "#17365D",
  blue: "#D9EAF7",
  pale: "#F4F7FA",
  input: "#FFF2CC",
  border: "#B7C9DC",
  white: "#FFFFFF",
  text: "#1F2937",
  green: "#E2F0D9",
};

const questionLabels = ["Answerable", "Needs Revision", "Invalid"];
const completenessLabels = ["Complete", "Incomplete", "Unclear"];
const passageLabels = ["Sufficient", "Required Component", "Context Only", "Not Supporting", "Unclear"];

function shuffled(items, seedText) {
  const values = [...items];
  let seed = 2166136261;
  for (const char of seedText) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619) >>> 0;
  function random() {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return (seed >>> 0) / 4294967296;
  }
  for (let i = values.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [values[i], values[j]] = [values[j], values[i]];
  }
  return values;
}

function applyTitle(sheet, title, subtitle, width) {
  sheet.showGridLines = false;
  const last = String.fromCharCode(64 + width);
  sheet.getRange(`A1:${last}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    rowHeight: 30,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${last}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = {
    fill: COLORS.blue,
    font: { color: COLORS.text, italic: true },
    wrapText: true,
    rowHeight: 34,
    verticalAlignment: "center",
  };
}

function styleTable(sheet, range, headerRange) {
  range.format = {
    font: { color: COLORS.text, size: 10 },
    verticalAlignment: "top",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  headerRange.format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    rowHeight: 34,
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
}

function addInstructions(workbook, reviewer = null) {
  const sheet = workbook.worksheets.add("操作说明");
  const role = reviewer ? `审核者 ${reviewer}` : "项目协调者";
  applyTitle(sheet, "60题独立双人证据标注", `${role}使用说明。请在开始前完整阅读本页。`, 4);
  const rows = [
    ["步骤", "操作", "必须遵守", "说明"],
    [1, "独立完成", "不要查看另一位审核者的文件，也不要讨论任何题目的判断。", "Reviewer A 为作者审核者；Reviewer B 为外部领域审核者。"],
    [2, "先判问题", "在“问题审核”页填写黄色单元格。", "Question Status 判断题目是否可由候选原文回答；Evidence Set Completeness 判断候选证据集合是否完整。"],
    [3, "再判证据", "在“证据审核”页逐条阅读，并填写 Passage Label。", "即使已找到充分证据，也请完成该题全部候选片段，避免只标容易命中的证据。"],
    [4, "核心证据", "Sufficient 与 Required Component 均会进入核心 Gold。", "Sufficient 表示该片段单独足够；Required Component 表示它是联合回答不可缺少的一部分。"],
    [5, "保留编号", "不要修改 Review ID、Passage ID、题目、原文、工作表名称或行顺序。", "只填写黄色列。"],
    [6, "一次返回", "完成三个批次后，将本人三份文件一起返回。", "不要在完成前交换或合并文件。"],
  ];
  sheet.getRange(`A4:D${3 + rows.length}`).values = rows;
  styleTable(sheet, sheet.getRange(`A4:D${3 + rows.length}`), sheet.getRange("A4:D4"));
  sheet.getRange("A5:A10").format.horizontalAlignment = "center";
  sheet.getRange("A:A").format.columnWidth = 10;
  sheet.getRange("B:B").format.columnWidth = 19;
  sheet.getRange("C:C").format.columnWidth = 53;
  sheet.getRange("D:D").format.columnWidth = 48;
  sheet.freezePanes.freezeRows(4);
  return sheet;
}

function addLabelGuide(workbook) {
  const sheet = workbook.worksheets.add("标签说明");
  applyTitle(sheet, "标签判定说明", "遇到边界情况时请以本页定义为准，并在 Reviewer Note 中简短说明。", 3);
  const rows = [
    ["字段", "标签", "判定标准"],
    ["Question Status", "Answerable", "候选冻结原文中存在足以回答该问题的证据。"],
    ["Question Status", "Needs Revision", "主题合理，但措辞、范围或限定条件需要修改后才能严谨回答。"],
    ["Question Status", "Invalid", "问题包含源文没有的前提、无法由候选证据支持，或不适合作为检索评价题。"],
    ["Evidence Set Completeness", "Complete", "候选集合已经包含完整回答所需的全部证据。"],
    ["Evidence Set Completeness", "Incomplete", "存在部分支持，但还缺少回答所需的重要证据。"],
    ["Evidence Set Completeness", "Unclear", "无法可靠判断候选集合是否完整。"],
    ["Passage Label", "Sufficient", "该片段单独即可完整、直接回答问题。"],
    ["Passage Label", "Required Component", "该片段单独不够，但在多片段联合回答中不可缺少。"],
    ["Passage Label", "Context Only", "提供背景或解释，但不是回答结论所必需的证据。"],
    ["Passage Label", "Not Supporting", "不能支持该问题的答案。"],
    ["Passage Label", "Unclear", "文本含义或与问题的关系无法可靠判断。"],
  ];
  sheet.getRange(`A4:C${3 + rows.length}`).values = rows;
  styleTable(sheet, sheet.getRange(`A4:C${3 + rows.length}`), sheet.getRange("A4:C4"));
  sheet.getRange("A:A").format.columnWidth = 28;
  sheet.getRange("B:B").format.columnWidth = 24;
  sheet.getRange("C:C").format.columnWidth = 80;
  sheet.freezePanes.freezeRows(4);
  return sheet;
}

function addQuestionReview(workbook, queries, reviewer, batch) {
  const sheet = workbook.worksheets.add("问题审核");
  applyTitle(sheet, `问题审核：${reviewer} / Batch ${batch}`, "请先填写黄色列。不要因为找到了一个看似相关的片段就自动判为 Answerable。", 8);
  const headers = [["序号", "Review ID", "题型", "Question", "Question Status*", "Evidence Set Completeness*", "Reviewer Note", "完成检查"]];
  const rows = queries.map((query, index) => [
    index + 1, query.query_id, query.query_slice, query.query, "", "", "", "",
  ]);
  sheet.getRange(`A4:H${4 + rows.length}`).values = [...headers, ...rows];
  styleTable(sheet, sheet.getRange(`A4:H${4 + rows.length}`), sheet.getRange("A4:H4"));
  sheet.getRange(`E5:G${4 + rows.length}`).format.fill = COLORS.input;
  sheet.getRange(`E5:E${4 + rows.length}`).dataValidation = { rule: { type: "list", values: questionLabels } };
  sheet.getRange(`F5:F${4 + rows.length}`).dataValidation = { rule: { type: "list", values: completenessLabels } };
  for (let row = 5; row <= 4 + rows.length; row += 1) {
    sheet.getRange(`H${row}`).formulas = [[`=IF(AND(E${row}<>"",F${row}<>""),"OK","待填写")`]];
  }
  sheet.getRange(`H5:H${4 + rows.length}`).format.fill = COLORS.pale;
  const widths = [8, 18, 22, 78, 20, 25, 45, 13];
  widths.forEach((width, index) => { sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width; });
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}

function addEvidenceReview(workbook, queries, reviewer, batch) {
  const sheet = workbook.worksheets.add("证据审核");
  applyTitle(sheet, `证据审核：${reviewer} / Batch ${batch}`, "每题的候选原文顺序已独立随机化。请完成全部候选片段，不要只标第一条可用证据。", 10);
  const rows = [];
  let ordinal = 1;
  for (const query of queries) {
    const passages = shuffled(query.candidate_passages, `${registry.seed}:${reviewer}:${query.query_id}:passages`);
    for (const passage of passages) {
      rows.push([
        ordinal, query.query_id, query.query_slice, query.query, passage.blind_passage_id,
        passage.source_document, passage.heading, passage.content, "", "",
      ]);
      ordinal += 1;
    }
  }
  const headers = [["序号", "Review ID", "题型", "Question", "Passage ID", "Source Document", "Heading", "Frozen Source Passage", "Passage Label*", "Reviewer Note"]];
  sheet.getRange(`A4:J${4 + rows.length}`).values = [...headers, ...rows];
  styleTable(sheet, sheet.getRange(`A4:J${4 + rows.length}`), sheet.getRange("A4:J4"));
  sheet.getRange(`I5:J${4 + rows.length}`).format.fill = COLORS.input;
  sheet.getRange(`I5:I${4 + rows.length}`).dataValidation = { rule: { type: "list", values: passageLabels } };
  const widths = [8, 18, 20, 56, 16, 26, 38, 92, 22, 40];
  widths.forEach((width, index) => { sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width; });
  sheet.getRange(`A5:J${4 + rows.length}`).format.rowHeight = 68;
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}

async function exportAndVerify(workbook, filename, sheetNames) {
  const outputPath = path.join(outputDir, filename);
  const blob = await SpreadsheetFile.exportXlsx(workbook);
  await blob.save(outputPath);
  const inspection = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
  if (!inspection || !JSON.stringify(inspection).includes("操作说明")) throw new Error(`inspection failed for ${filename}`);
  await fs.mkdir(path.join(previewDir, filename.replace(/\.xlsx$/i, "")), { recursive: true });
  for (const sheetName of sheetNames) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.8, format: "png" });
    const bytes = new Uint8Array(await preview.arrayBuffer());
    await fs.writeFile(path.join(previewDir, filename.replace(/\.xlsx$/i, ""), `${sheetName}.png`), bytes);
  }
  return outputPath;
}

async function buildReviewerWorkbook(reviewer, batch, canonicalQueries) {
  const queries = shuffled(canonicalQueries, `${registry.seed}:${reviewer}:${batch}:queries`);
  const workbook = Workbook.create();
  addInstructions(workbook, reviewer);
  addQuestionReview(workbook, queries, reviewer, batch);
  addEvidenceReview(workbook, queries, reviewer, batch);
  addLabelGuide(workbook);
  const filename = `Reviewer_${reviewer}_Batch_${batch}_20题_独立审核.xlsx`;
  return exportAndVerify(workbook, filename, ["操作说明", "问题审核", "证据审核", "标签说明"]);
}

async function buildMasterWorkbook() {
  const workbook = Workbook.create();
  addInstructions(workbook, null);
  const summary = workbook.worksheets.add("60题总览");
  applyTitle(summary, "60题总览", "本表用于确认题目分批与进度，不包含检索方法、真实 chunk ID 或预设答案。", 6);
  const queries = [...registry.queries].sort((a, b) => a.batch.localeCompare(b.batch) || a.query_id.localeCompare(b.query_id));
  const rows = queries.map((query) => [query.batch, query.query_id, query.query_slice, query.query, query.candidate_passages.length, ""]);
  summary.getRange(`A4:F${4 + rows.length}`).values = [["Batch", "Review ID", "题型", "Question", "候选片段数", "协调备注"], ...rows];
  styleTable(summary, summary.getRange(`A4:F${4 + rows.length}`), summary.getRange("A4:F4"));
  summary.getRange(`F5:F${4 + rows.length}`).format.fill = COLORS.input;
  [10, 18, 22, 85, 15, 38].forEach((width, index) => { summary.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width; });
  summary.freezePanes.freezeRows(4);

  const protocol = workbook.worksheets.add("协议与返回清单");
  applyTitle(protocol, "协议与返回清单", "正式分析只使用两位审核者在讨论前独立完成的初始标签。", 4);
  const protocolRows = [
    ["项目", "固定内容", "A", "B"],
    ["身份", "A=作者审核者；B=外部领域审核者", "作者", "外部专家"],
    ["批次", "每人3份，每份20题", "01 / 02 / 03", "01 / 02 / 03"],
    ["独立性", "完成前不得互看、讨论或合并", "必须", "必须"],
    ["返回", "各自完成三份后一次性返回", "3份", "3份"],
    ["后续", "Codex 合并初始标签、计算一致性并生成分歧裁决表", "不提前裁决", "不提前裁决"],
  ];
  protocol.getRange(`A4:D${3 + protocolRows.length}`).values = protocolRows;
  styleTable(protocol, protocol.getRange(`A4:D${3 + protocolRows.length}`), protocol.getRange("A4:D4"));
  [22, 66, 24, 24].forEach((width, index) => { protocol.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width; });
  addLabelGuide(workbook);
  return exportAndVerify(workbook, "双人标注_60题_总控文件.xlsx", ["操作说明", "60题总览", "协议与返回清单", "标签说明"]);
}

await fs.mkdir(outputDir, { recursive: true });
const outputs = [await buildMasterWorkbook()];
for (const reviewer of ["A", "B"]) {
  for (const batch of ["01", "02", "03"]) {
    const queries = registry.queries.filter((query) => query.batch === batch);
    if (queries.length !== 20) throw new Error(`batch ${batch} contains ${queries.length} queries`);
    outputs.push(await buildReviewerWorkbook(reviewer, batch, queries));
  }
}
console.log(JSON.stringify({ outputs }, null, 2));

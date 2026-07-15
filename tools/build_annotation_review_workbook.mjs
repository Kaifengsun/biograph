import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json";
const outputDir = "outputs";
const outputPath = `${outputDir}/three_path_annotation_review_2026-07-11.xlsx`;
const previewPath = `${outputDir}/three_path_annotation_review_2026-07-11.png`;

const pack = JSON.parse(await fs.readFile(inputPath, "utf8"));
const quotas = {
  single_clause: 20,
  cross_document: 20,
  document_structure: 7,
  table: 12,
  supply_chain_evidence_path: 1,
};

function joined(values) {
  return (values || []).join("; ");
}

function reviewPriority(row) {
  const review = row.llm_assisted_review || {};
  const graphPaths = (row.retrieval_candidate_graph_paths || []).length;
  return [
    review.insufficient_evidence ? 0 : 1,
    graphPaths ? 0 : 1,
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

const activeRows = pack.queries.filter((row) => row.review_status !== "excluded");
const selected = [];
for (const [slice, quota] of Object.entries(quotas)) {
  selected.push(...activeRows.filter((row) => row.query_slice === slice).sort(comparePriority).slice(0, quota));
}
if (selected.length !== 60) throw new Error(`Expected 60 review rows, got ${selected.length}`);
const excluded = pack.queries.filter((row) => row.review_status === "excluded");
const selectedInsufficientCount = selected.filter((row) => row.llm_assisted_review?.insufficient_evidence).length;

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Overview");
const queue = workbook.worksheets.add("Review Queue");
const all = workbook.worksheets.add("All Candidates");
const excludedSheet = workbook.worksheets.add("Excluded");
for (const sheet of [overview, queue, all, excludedSheet]) sheet.showGridLines = false;

overview.getRange("A1:F1").merge();
overview.getRange("A1").values = [["Three-Path Retrieval Evidence Review"]];
overview.getRange("A2:F2").merge();
overview.getRange("A2").values = [["Candidate-only workbook. LLM suggestions are aids; enter gold evidence only after source review."]];
overview.getRange("A4:F6").values = [
  ["Review queue", "LLM insufficient", "Pending review", "Formal status", "Source pack", "Review rule"],
  ["=COUNTA('Review Queue'!A2:A61)", selectedInsufficientCount, "=COUNTIF('Review Queue'!I2:I61,\"Pending\")", "Not formal", "2026-07-11 LLM-assisted pack", "Confirm direct source evidence before marking Confirmed"],
  ["Target: 60", "Prioritize these first", "Editable column I", "No metrics until labels freeze", "Build5 + R2/R3 + graph paths", "Do not accept connected-but-irrelevant graph paths"],
];
overview.getRange("A8:F13").values = [
  ["Workflow", "Instruction", "", "", "", ""],
  ["1", "Read the question and LLM rationale.", "", "", "", ""],
  ["2", "Check the candidate chunk IDs against the frozen source text.", "", "", "", ""],
  ["3", "Set status to Confirmed, Revise, or Exclude.", "", "", "", ""],
  ["4", "For Confirmed, fill Gold evidence chunk IDs and optional accepted graph path nodes.", "", "", "", ""],
  ["5", "Only Confirmed rows are candidates for the later frozen formal set.", "", "", "", ""],
];

const headers = [
  "Review ID", "Slice", "Question", "LLM suggested evidence chunk IDs", "LLM says insufficient", "LLM rationale",
  "All candidate evidence chunk IDs", "Graph path candidates", "Reviewer status", "Gold evidence chunk IDs", "Accepted graph path node IDs", "Reviewer note",
];
queue.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
const queueValues = selected.map((row) => [
  row.annotation_id,
  row.query_slice,
  row.query,
  joined(row.llm_assisted_review?.direct_support_chunk_ids),
  Boolean(row.llm_assisted_review?.insufficient_evidence),
  row.llm_assisted_review?.rationale || "",
  joined(row.candidate_evidence_chunk_ids),
  (row.retrieval_candidate_graph_paths || []).map((path) => path.join(" -> ")).join("\n"),
  "Pending",
  "",
  "",
  "",
]);
queue.getRangeByIndexes(1, 0, queueValues.length, headers.length).values = queueValues;
queue.tables.add(`A1:L${queueValues.length + 1}`, true, "ReviewQueueTable");
queue.getRange(`I2:I${queueValues.length + 1}`).dataValidation = { rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] } };

const allHeaders = ["Annotation ID", "Slice", "Question", "LLM suggested evidence", "Insufficient", "Candidate count", "Graph path count", "Review status", "Exclusion reason"];
all.getRangeByIndexes(0, 0, 1, allHeaders.length).values = [allHeaders];
const allValues = pack.queries.map((row) => [
  row.annotation_id, row.query_slice, row.query, joined(row.llm_assisted_review?.direct_support_chunk_ids),
  Boolean(row.llm_assisted_review?.insufficient_evidence), (row.candidate_evidence_chunk_ids || []).length,
  (row.retrieval_candidate_graph_paths || []).length, row.review_status, row.exclusion_reason || "",
]);
all.getRangeByIndexes(1, 0, allValues.length, allHeaders.length).values = allValues;
all.tables.add(`A1:I${allValues.length + 1}`, true, "AllCandidatesTable");

const excludedHeaders = ["Annotation ID", "Slice", "Question", "Exclusion reason", "Candidate evidence IDs"];
excludedSheet.getRangeByIndexes(0, 0, 1, excludedHeaders.length).values = [excludedHeaders];
const excludedValues = excluded.map((row) => [row.annotation_id, row.query_slice, row.query, row.exclusion_reason, joined(row.candidate_evidence_chunk_ids)]);
excludedSheet.getRangeByIndexes(1, 0, excludedValues.length, excludedHeaders.length).values = excludedValues;
excludedSheet.tables.add(`A1:E${excludedValues.length + 1}`, true, "ExcludedTable");

const titleFormat = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center", verticalAlignment: "center" };
overview.getRange("A1:F1").format = titleFormat;
overview.getRange("A2:F2").format = { fill: "#E8F1F5", font: { italic: true, color: "#17465E" }, wrapText: true };
overview.getRange("A4:F4").format = { fill: "#2A6F97", font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
overview.getRange("A5:F5").format = { fill: "#F5FAFC", font: { bold: true }, horizontalAlignment: "center", wrapText: true };
overview.getRange("A8:F8").format = { fill: "#2A6F97", font: { bold: true, color: "#FFFFFF" } };
overview.getRange("A4:F6").format.borders = { preset: "all", style: "thin", color: "#C9D9E3" };
overview.getRange("A8:F13").format.borders = { preset: "outside", style: "thin", color: "#C9D9E3" };
overview.getRange("A1:F13").format.wrapText = true;
overview.getRange("A1:F13").format.verticalAlignment = "center";
overview.getRange("A1:F1").format.rowHeight = 28;
overview.getRange("A2:F2").format.rowHeight = 34;
overview.getRange("A1:A13").format.columnWidth = 18;
overview.getRange("B1:B13").format.columnWidth = 28;
overview.getRange("C1:C13").format.columnWidth = 22;
overview.getRange("D1:D13").format.columnWidth = 22;
overview.getRange("E1:E13").format.columnWidth = 25;
overview.getRange("F1:F13").format.columnWidth = 42;

for (const sheet of [queue, all, excludedSheet]) {
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A1:Z1").format = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
  sheet.getRange("A1:Z1").format.rowHeight = 28;
}
queue.freezePanes.freezeColumns(2);
queue.getRange(`A2:L${queueValues.length + 1}`).format.wrapText = true;
queue.getRange(`A2:L${queueValues.length + 1}`).format.verticalAlignment = "top";
queue.getRange(`E2:E${queueValues.length + 1}`).format.numberFormat = [["General"]];
queue.getRange(`A1:A${queueValues.length + 1}`).format.columnWidth = 16;
queue.getRange(`B1:B${queueValues.length + 1}`).format.columnWidth = 22;
queue.getRange(`C1:C${queueValues.length + 1}`).format.columnWidth = 42;
queue.getRange(`D1:D${queueValues.length + 1}`).format.columnWidth = 34;
queue.getRange(`E1:E${queueValues.length + 1}`).format.columnWidth = 14;
queue.getRange(`F1:F${queueValues.length + 1}`).format.columnWidth = 55;
queue.getRange(`G1:G${queueValues.length + 1}`).format.columnWidth = 42;
queue.getRange(`H1:H${queueValues.length + 1}`).format.columnWidth = 50;
queue.getRange(`I1:I${queueValues.length + 1}`).format.columnWidth = 16;
queue.getRange(`J1:J${queueValues.length + 1}`).format.columnWidth = 34;
queue.getRange(`K1:K${queueValues.length + 1}`).format.columnWidth = 45;
queue.getRange(`L1:L${queueValues.length + 1}`).format.columnWidth = 42;
queue.getRange(`A2:L${queueValues.length + 1}`).format.rowHeight = 80;
queue.getRange(`I2:I${queueValues.length + 1}`).conditionalFormats.add("containsText", { text: "Confirmed", format: { fill: "#D9EAD3", font: { color: "#2E6B2E", bold: true } } });
queue.getRange(`I2:I${queueValues.length + 1}`).conditionalFormats.add("containsText", { text: "Revise", format: { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } } });
queue.getRange(`I2:I${queueValues.length + 1}`).conditionalFormats.add("containsText", { text: "Exclude", format: { fill: "#F4CCCC", font: { color: "#990000", bold: true } } });

all.getRange(`A2:I${allValues.length + 1}`).format.wrapText = true;
all.getRange(`A1:A${allValues.length + 1}`).format.columnWidth = 18;
all.getRange(`B1:B${allValues.length + 1}`).format.columnWidth = 22;
all.getRange(`C1:C${allValues.length + 1}`).format.columnWidth = 54;
all.getRange(`D1:D${allValues.length + 1}`).format.columnWidth = 36;
all.getRange(`E1:I${allValues.length + 1}`).format.columnWidth = 18;
excludedSheet.getRange(`A2:E${excludedValues.length + 1}`).format.wrapText = true;
excludedSheet.getRange("A1:A10").format.columnWidth = 18;
excludedSheet.getRange("B1:B10").format.columnWidth = 22;
excludedSheet.getRange("C1:C10").format.columnWidth = 58;
excludedSheet.getRange("D1:D10").format.columnWidth = 36;
excludedSheet.getRange("E1:E10").format.columnWidth = 48;

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Review Queue", range: "A1:L16", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath, reviewRows: selected.length, excludedRows: excluded.length }));

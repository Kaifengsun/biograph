import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [payloadPath, outputPath, previewDir] = process.argv.slice(2);
if (!payloadPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build_revision_confirmation_workbook.mjs <payload.json> <output.xlsx> <preview-dir>");
}

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const questions = new Map(payload.questions.map((question) => [question.annotation_id, question]));
const revisions = [
  {
    sourceId: "CONF-TB03",
    revisionId: "CONF-TB03__R1",
    revisedQuestion: "What types of impurity thresholds are listed in Attachment 1 for the ≤ 2 g/day category?",
    passageIds: ["P02"],
    rationale: "The frozen table header preserves the category and the three threshold types, but not their numerical values.",
  },
  {
    sourceId: "CONF-TB07",
    revisionId: "CONF-TB07__R1",
    revisedQuestion: "Which performance characteristics are identified as being described in the ATP?",
    passageIds: ["P14"],
    rationale: "The excerpt lists the characteristics but does not preserve their detailed criteria.",
  },
  {
    sourceId: "CONF-TB08",
    revisionId: "CONF-TB08__R1",
    revisedQuestion: "What identification threshold is specified in Example 2 for a 1.9 g maximum daily dose?",
    passageIds: ["P01"],
    rationale: "The excerpt directly states the identification threshold for Example 2.",
  },
  {
    sourceId: "CONF-CD01",
    revisionId: "CONF-CD01__R1",
    revisedQuestion: "How does ICH Q9 describe the role of quality risk management in an effective pharmaceutical quality system and commercial manufacturing?",
    passageIds: ["P08"],
    rationale: "The revised question removes the unsupported demand for substantive ICH Q10 requirements.",
  },
  {
    sourceId: "CONF-CD02",
    revisionId: "CONF-CD02__R1",
    revisedQuestion: "What lifecycle validation requirements does EMA GMP Annex 11 set for computerized systems?",
    passageIds: ["P11"],
    rationale: "The revised question is limited to the directly preserved Annex 11 validation requirements.",
  },
  {
    sourceId: "CONF-CD04",
    revisionId: "CONF-CD04__R1",
    revisedQuestion: "How does ICH Q10 knowledge management support ongoing process validation and monitoring described in the FDA quality systems CGMP guidance?",
    passageIds: ["P09", "P07", "P10"],
    rationale: "The source attribution is corrected to the FDA quality systems CGMP guidance, with ICH Q10 and FDA passages serving as joint evidence.",
  },
];

const workbook = Workbook.create();
const queue = workbook.worksheets.add("Review Queue");
const reader = workbook.worksheets.add("Evidence Reader");
queue.showGridLines = false;
reader.showGridLines = false;

const queueRows = [[
  "Revision ID", "Query Slice", "Original Question", "Revised Question",
  "Proposed Gold Passage IDs", "Status", "Revision Rationale", "Reviewer Note",
]];
const readerRows = [[
  "Revision ID", "Passage ID", "Document", "Heading", "Original Source Passage", "Frozen Source File",
]];

for (const revision of revisions) {
  const question = questions.get(revision.sourceId);
  if (!question) throw new Error(`Missing source question ${revision.sourceId}`);
  queueRows.push([
    revision.revisionId,
    question.query_slice,
    question.query,
    revision.revisedQuestion,
    revision.passageIds.join("; "),
    "Pending",
    revision.rationale,
    "",
  ]);
  for (const passageId of revision.passageIds) {
    const passage = question.passages.find((item) => item.passage_id === passageId);
    if (!passage) throw new Error(`Missing ${revision.sourceId} ${passageId}`);
    readerRows.push([
      revision.revisionId,
      passage.passage_id,
      passage.doc_id,
      passage.heading,
      passage.original_source_passage,
      passage.frozen_source_file,
    ]);
  }
}

queue.getRange(`A1:H${queueRows.length}`).values = queueRows;
reader.getRange(`A1:F${readerRows.length}`).values = readerRows;

const headerFormat = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#163A5A" },
};
queue.getRange("A1:H1").format = headerFormat;
reader.getRange("A1:F1").format = headerFormat;
queue.getRange(`A2:H${queueRows.length}`).format = {
  verticalAlignment: "top",
  wrapText: true,
  borders: { insideHorizontal: { style: "thin", color: "#D9E2F3" } },
};
reader.getRange(`A2:F${readerRows.length}`).format = {
  verticalAlignment: "top",
  wrapText: true,
  borders: { insideHorizontal: { style: "thin", color: "#D9E2F3" } },
};
queue.getRange(`F2:F${queueRows.length}`).dataValidation = {
  rule: { type: "list", values: ["Pending", "Confirmed", "Revise", "Exclude"] },
};
queue.getRange(`F2:F${queueRows.length}`).conditionalFormats.add("containsText", {
  text: "Confirmed", format: { fill: "#E2F0D9", font: { color: "#375623", bold: true } },
});
queue.getRange(`F2:F${queueRows.length}`).conditionalFormats.add("containsText", {
  text: "Revise", format: { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } },
});
queue.getRange(`F2:F${queueRows.length}`).conditionalFormats.add("containsText", {
  text: "Exclude", format: { fill: "#FCE4D6", font: { color: "#9C0006", bold: true } },
});

queue.freezePanes.freezeRows(1);
queue.freezePanes.freezeColumns(2);
reader.freezePanes.freezeRows(1);
reader.freezePanes.freezeColumns(2);
queue.getRange("A:A").format.columnWidth = 19;
queue.getRange("B:B").format.columnWidth = 18;
queue.getRange("C:D").format.columnWidth = 52;
queue.getRange("E:E").format.columnWidth = 25;
queue.getRange("F:F").format.columnWidth = 14;
queue.getRange("G:H").format.columnWidth = 44;
queue.getRange(`1:${queueRows.length}`).format.autofitRows();
reader.getRange("A:A").format.columnWidth = 19;
reader.getRange("B:B").format.columnWidth = 12;
reader.getRange("C:C").format.columnWidth = 22;
reader.getRange("D:D").format.columnWidth = 35;
reader.getRange("E:E").format.columnWidth = 95;
reader.getRange("F:F").format.columnWidth = 29;
reader.getRange(`1:${readerRows.length}`).format.autofitRows();

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range] of [["Review Queue", `A1:H${queueRows.length}`], ["Evidence Reader", `A1:F${readerRows.length}`]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replace(/\s/g, "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
await fs.writeFile(path.join(previewDir, "formula_error_scan.ndjson"), errors.ndjson, "utf8");
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(JSON.stringify({ outputPath, revisions: revisions.length, passages: readerRows.length - 1 }, null, 2));

import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, payloadPath, outputPath] = process.argv.slice(2);
if (!inputPath || !payloadPath || !outputPath) {
  throw new Error("Usage: node validate_reviewed_workbook.mjs <reviewed.xlsx> <payload.json> <output.json>");
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const rows = workbook.worksheets.getItem("Review Queue").getUsedRange(true).values;
const headers = rows[0];
const records = rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const questions = new Map(payload.questions.map((question) => [question.annotation_id, question]));

const splitPassageIds = (value) => String(value || "")
  .split(/[;,；，\s]+/)
  .map((item) => item.trim().toUpperCase())
  .filter(Boolean);

const statusCounts = {};
const validationErrors = [];
const normalized = records.map((record) => {
  const reviewId = String(record["Review ID"] || "").trim();
  const status = String(record.Status || "").trim();
  const passageIds = splitPassageIds(record["Gold Passage IDs"]);
  statusCounts[status] = (statusCounts[status] || 0) + 1;
  const question = questions.get(reviewId);
  if (!question) {
    validationErrors.push(`${reviewId}: unknown Review ID`);
    return { reviewId, status, passageIds, revisionNote: record["Revision Note"] || "" };
  }
  const validPassageIds = new Set(question.passages.map((passage) => passage.passage_id));
  const invalidPassageIds = passageIds.filter((passageId) => !validPassageIds.has(passageId));
  if (invalidPassageIds.length) {
    validationErrors.push(`${reviewId}: invalid Passage IDs ${invalidPassageIds.join(", ")}`);
  }
  if (status === "Confirmed" && passageIds.length === 0) {
    validationErrors.push(`${reviewId}: Confirmed without Gold Passage IDs`);
  }
  if (status === "Revise" && !record["Revision Note"]) {
    validationErrors.push(`${reviewId}: Revise without Revision Note`);
  }
  return {
    reviewId,
    querySlice: record["Query Slice"],
    question: record.Question,
    status,
    passageIds,
    chunkIds: passageIds.map((passageId) => question.passages.find((passage) => passage.passage_id === passageId)?.chunk_id).filter(Boolean),
    revisionNote: record["Revision Note"] || "",
  };
});

const output = {
  sourceWorkbook: inputPath,
  recordCount: normalized.length,
  statusCounts,
  validationErrors,
  readyForFreeze: normalized.length === payload.question_count
    && validationErrors.length === 0
    && normalized.every((record) => record.status === "Confirmed" || record.status === "Exclude"),
  records: normalized,
};
await fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf8");
console.log(JSON.stringify({
  recordCount: output.recordCount,
  statusCounts: output.statusCounts,
  validationErrorCount: validationErrors.length,
  readyForFreeze: output.readyForFreeze,
  revisedIds: normalized.filter((record) => record.status === "Revise").map((record) => record.reviewId),
}, null, 2));

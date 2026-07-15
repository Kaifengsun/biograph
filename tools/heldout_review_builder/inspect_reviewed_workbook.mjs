import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const inputPath = process.env.REVIEWED_WORKBOOK || "D:/Downloads/adaptive_text_first_heldout_review_2026-07-15_reviewed.xlsx";
const outputDir = process.env.REVIEW_AUDIT_OUTPUT || path.join(projectRoot, "outputs/heldout_review_2026-07-15/reviewed_audit");

await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheetCheck = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 3000 });
const queueCheck = await workbook.inspect({
  kind: "table",
  range: "Review Queue!A1:K40",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 11,
  tableMaxCellChars: 2000,
  maxChars: 200000,
});
const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});

const queue = workbook.worksheets.getItem("Review Queue");
const rows = queue.getRange("A4:K34").values;
await fs.writeFile(
  path.join(outputDir, "review_queue_values.json"),
  JSON.stringify({ inputPath, rows }, null, 2),
  "utf8",
);
await fs.writeFile(
  path.join(outputDir, "inspect.ndjson"),
  [sheetCheck.ndjson, queueCheck.ndjson, errorCheck.ndjson].join("\n"),
  "utf8",
);

for (const [sheetName, range, fileName] of [
  ["Protocol", "A1:H10", "reviewed_protocol.png"],
  ["Review Queue", "A1:K12", "reviewed_queue.png"],
  ["Evidence Reader", "A1:H10", "reviewed_evidence.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

console.log(JSON.stringify({ inputPath, outputDir, sheetCheck: sheetCheck.ndjson, errorCheck: errorCheck.ndjson }, null, 2));

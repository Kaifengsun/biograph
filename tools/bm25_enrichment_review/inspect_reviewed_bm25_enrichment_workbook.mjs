import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const inputPath = process.env.REVIEWED_WORKBOOK || "D:/Downloads/BM25与语料富化消融_30题带原文简化审核表_2026-07-15_已审核.xlsx";
const outputDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15/reviewed_audit");

await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheetCheck = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 3000 });
const queueCheck = await workbook.inspect({
  kind: "table",
  range: "Review Queue!A1:J40",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 10,
  tableMaxCellChars: 4000,
  maxChars: 220000,
});
const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
const queue = workbook.worksheets.getItem("Review Queue");
const rows = queue.getRange("A4:J34").values;
await fs.writeFile(path.join(outputDir, "review_queue_values.json"), JSON.stringify({ inputPath, rows }, null, 2), "utf8");
await fs.writeFile(path.join(outputDir, "inspect.ndjson"), [sheetCheck.ndjson, queueCheck.ndjson, errorCheck.ndjson].join("\n"), "utf8");

for (const [sheetName, range, fileName] of [
  ["审核说明", "A1:F11", "reviewed_审核说明.png"],
  ["Review Queue", "A1:J12", "reviewed_queue.png"],
  ["Evidence Reader", "A1:K9", "reviewed_evidence.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

console.log(JSON.stringify({ inputPath, outputDir, sheets: sheetCheck.ndjson, errors: errorCheck.ndjson }, null, 2));

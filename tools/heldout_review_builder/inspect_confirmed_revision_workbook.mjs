import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const inputPath = process.env.CONFIRMED_REVISION_WORKBOOK || "D:/Downloads/adaptive_text_first_heldout_revision_round_2026-07-15_confirmed.xlsx";
const outputDir = process.env.REVISION_CONFIRM_AUDIT_OUTPUT || path.join(projectRoot, "outputs/heldout_review_2026-07-15/revision_confirmed_audit");

await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheetCheck = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 3000 });
const queueCheck = await workbook.inspect({
  kind: "table",
  range: "Revision Queue!A1:J8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 10,
  tableMaxCellChars: 2500,
  maxChars: 30000,
});
const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
const queue = workbook.worksheets.getItem("Revision Queue");
const rows = queue.getRange("A4:J8").values;
await fs.writeFile(path.join(outputDir, "revision_queue_values.json"), JSON.stringify({ inputPath, rows }, null, 2), "utf8");
await fs.writeFile(path.join(outputDir, "inspect.ndjson"), [sheetCheck.ndjson, queueCheck.ndjson, errorCheck.ndjson].join("\n"), "utf8");
for (const [sheetName, range, fileName] of [
  ["Instructions", "A1:F8", "confirmed_instructions.png"],
  ["Revision Queue", "A1:J8", "confirmed_queue.png"],
  ["Evidence Reader", "A1:H10", "confirmed_evidence.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
console.log(JSON.stringify({ inputPath, outputDir, sheetCheck: sheetCheck.ndjson, errorCheck: errorCheck.ndjson }, null, 2));

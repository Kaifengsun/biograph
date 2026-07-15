import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const inputPath = process.env.CONFIRMED_REVISION_WORKBOOK || "D:/Downloads/BM25与语料富化消融_8题修订二次确认表_2026-07-15_已确认.xlsx";
const outputDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15/revision_confirmed_audit");
await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheetCheck = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 3000 });
const queueCheck = await workbook.inspect({ kind: "table", range: "Revision Queue!A1:H13", include: "values,formulas", tableMaxRows: 13, tableMaxCols: 8, tableMaxCellChars: 4000, maxChars: 100000 });
const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
const rows = workbook.worksheets.getItem("Revision Queue").getRange("A4:H12").values;
await fs.writeFile(path.join(outputDir, "revision_queue_values.json"), JSON.stringify({ inputPath, rows }, null, 2), "utf8");
await fs.writeFile(path.join(outputDir, "inspect.ndjson"), [sheetCheck.ndjson, queueCheck.ndjson, errorCheck.ndjson].join("\n"), "utf8");
for (const [sheetName, range, fileName] of [["确认说明", "A1:E7", "confirmed_确认说明.png"], ["Revision Queue", "A1:H13", "confirmed_queue.png"], ["Evidence Reader", "A1:H9", "confirmed_evidence.png"]]) {
  const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await image.arrayBuffer()));
}
console.log(JSON.stringify({ inputPath, outputDir, sheets: sheetCheck.ndjson, errors: errorCheck.ndjson }, null, 2));

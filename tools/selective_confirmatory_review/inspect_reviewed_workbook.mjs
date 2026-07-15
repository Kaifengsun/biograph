import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node inspect_reviewed_workbook.mjs <input.xlsx> <output.json>");
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheetSummary = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 5000,
});

const output = { sheetSummary: sheetSummary.ndjson, sheets: {} };
for (const sheetName of ["说明", "Review Queue", "Evidence Reader"]) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange(true);
  output.sheets[sheetName] = {
    address: used.address,
    values: used.values,
    formulas: used.formulas,
  };
}

await fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf8");

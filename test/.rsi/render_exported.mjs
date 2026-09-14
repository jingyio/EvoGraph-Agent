import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const internal = path.dirname(fileURLToPath(import.meta.url));
const directory = path.dirname(internal);
const specs = JSON.parse(await fs.readFile(path.join(internal, 'data.json'), 'utf8'));
for (const spec of specs) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(directory, spec.path)));
  for (const [name, rows] of Object.entries(spec.tables)) {
    const lastColumn = String.fromCharCode(64 + Object.keys(rows[0]).length);
    const blob = await workbook.render({ sheetName: name, range: `A1:${lastColumn}6`, scale: 1 });
    await fs.writeFile(path.join(internal, 'previews', `${path.basename(path.dirname(spec.path))}-${path.basename(spec.path, '.xlsx')}-${name}.png`),
      new Uint8Array(await blob.arrayBuffer()));
  }
}

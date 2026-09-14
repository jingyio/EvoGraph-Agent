import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const internal = path.dirname(fileURLToPath(import.meta.url));
const output = path.dirname(internal);
const specs = JSON.parse(await fs.readFile(path.join(internal, 'data.json'), 'utf8'));
const previews = path.join(internal, 'previews');
await fs.mkdir(previews, { recursive: true });
for (const spec of specs) {
  const workbook = Workbook.create();
  for (const [name, rows] of Object.entries(spec.tables)) {
    const sheet = workbook.worksheets.add(name);
    const fields = Object.keys(rows[0]);
    const values = [fields, ...rows.map(row => fields.map(field =>
      typeof row[field] === 'string' ? `'${row[field]}` : row[field] ?? null))];
    const range = sheet.getRangeByIndexes(0, 0, values.length, fields.length);
    fields.forEach((field, col) => {
      if (rows.every(row => row[field] == null || typeof row[field] === 'string')) {
        sheet.getRangeByIndexes(0, col, values.length, 1).setNumberFormat('@');
      }
    });
    range.values = values;
    range.format.font = { name: 'Arial', size: 11, color: '#222222' };
    range.format.rowHeight = 25;
    sheet.getRangeByIndexes(0, 0, 1, fields.length).format = {
      fill: '#293F49', font: { bold: true, color: '#FFFFFF' }, rowHeight: 30,
    };
    sheet.showGridLines = false;
    sheet.freezePanes.freezeRows(1);
    fields.forEach((field, col) => {
      const cells = sheet.getRangeByIndexes(0, col, values.length, 1);
      const longest = Math.max(field.length, ...rows.map(row => String(row[field] ?? '').length));
      cells.format.columnWidth = Math.min(65, Math.max(20, longest + 3));
      if (longest > 62) {
        cells.format.wrapText = true;
      }
      if (rows.some(row => typeof row[field] === 'number')) {
        sheet.getRangeByIndexes(1, col, rows.length, 1).setNumberFormat('#,##0');
      }
    });
    range.format.autofitRows();
  }
  workbook.recalculate();
  for (const [name, rows] of Object.entries(spec.tables)) {
    const col = String.fromCharCode(64 + Object.keys(rows[0]).length);
    const preview = await workbook.render({ sheetName: name, range: `A1:${col}${Math.min(rows.length + 1, 6)}`, scale: 1 });
    await fs.writeFile(path.join(previews, `${path.basename(path.dirname(spec.path))}-${path.basename(spec.path, '.xlsx')}-${name}.png`),
      new Uint8Array(await preview.arrayBuffer()));
  }
  const target = path.join(output, spec.path);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
  await fs.rename(`${target}.inspect.ndjson`, path.join(internal, `${path.basename(path.dirname(spec.path))}-${path.basename(spec.path)}.inspect.ndjson`));
  console.log(spec.path, Object.entries(spec.tables).map(([name, rows]) => `${name}:${rows.length}`).join(' '));
}

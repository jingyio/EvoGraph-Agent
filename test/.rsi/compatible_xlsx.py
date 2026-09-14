"""Use equivalent relative OOXML relationship paths for the current importer."""
from io import BytesIO
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


directory = Path(__file__).resolve().parents[1]
specs = json.loads((directory / '.rsi/data.json').read_text())
main_ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
for spec in specs:
    path = directory / spec['path']
    tables = list(spec['tables'].values())
    output = BytesIO()
    with ZipFile(path) as source, ZipFile(output, 'w') as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == 'xl/_rels/workbook.xml.rels':
                root = ET.fromstring(content)
                for rel in root:
                    value = rel.get('Target', '')
                    if value.startswith('/xl/') and rel.get('TargetMode') != 'External':
                        rel.set('Target', value[len('/xl/'):])
                content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            elif entry.filename.startswith('xl/worksheets/sheet') and entry.filename.endswith('.xml'):
                index = int(Path(entry.filename).stem.removeprefix('sheet')) - 1
                rows = tables[index]
                fields = list(rows[0])
                root = ET.fromstring(content)
                # Restore literal text that the exporter coerces to dates or quote-prefixed values.
                for cell in root.findall(f'.//{{{main_ns}}}c'):
                    reference = cell.attrib['r']
                    column = ord(reference[0]) - ord('A')
                    row = int(reference[1:]) - 2
                    if row >= 0 and isinstance(value := rows[row].get(fields[column]), str):
                        for child in list(cell):
                            cell.remove(child)
                        cell.set('t', 'inlineStr')
                        inline = ET.SubElement(cell, f'{{{main_ns}}}is')
                        text = ET.SubElement(inline, f'{{{main_ns}}}t')
                        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                        text.text = value
                content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            target.writestr(entry, content)
    path.write_bytes(output.getvalue())

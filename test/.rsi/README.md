# Preparation audit

None of these internal files is an Agent input. See `../使用说明.txt`.
`provenance.json` preserves raw cache hashes, selected IDs and exclusion counts.
`data.json` is the source-value export; `verification.json` holds final workbook hashes and checks.
The directory name `test` describes a manual trial kit, not the frozen benchmark test split.

Preparation reads cached public records only, excludes the frozen database and existing workspace IDs,
then selects remaining train-partition records by fixed hash order. No model results or gold are consulted.
Base uses the first 12 records; extension adds four records. No values are invented or changed.

Build order (cwd is repository root): `prepare_inputs.py`, `build_workbooks.mjs`, `compatible_xlsx.py`,
`render_exported.mjs`, `verify_inputs.py`. Python preparation and verification need `PYTHONPATH=.`.
Workbook authoring/rendering uses bundled artifact-tool; `node_modules` is a local ignored symlink.
The OOXML compatibility step makes relationship targets relative and preserves literal source strings:
the current importer skips absolute targets and the exporter otherwise coerces ISO dates to numeric serials.
Final saved XLSX values are checked through the actual upload parser, then all six uploads and task creations
are checked in a temporary isolated WorkspaceManager. No Agent, model or experience update is involved.

Rebuilding overwrites these input files. Preserve user edits before explicitly rebuilding.

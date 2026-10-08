# Hardware Watch

A local hackathon prototype for SU Hardware Program inventory monitoring, reconciliation, and departure-return planning. Open **http://127.0.0.1:8765** while the server is running.

## Run

On this Mac, double-click `start.command`, or run it from Terminal. It uses the available Codex Python runtime when no project virtual environment exists.

Requires Python 3.10 or newer. For a fresh clone:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The repository contains source code only. The local SQLite database, uploaded exports, and screenshots are excluded from Git. A fresh clone starts empty; import exports through the Data sources screen. This app binds to localhost and has no authentication; it is for local demonstrations. Use synthetic data for public demos. No notifications, purchases, source-system writes, or external AI calls occur.

## Demo walkthrough

1. Overview: compare reported stock across the two export dates. These are historical observations, not live monitoring.
2. Reconciliation: select a billing rejection, expand source rows, and read its order/inventory/invoice/billing timeline. Change it to Investigating, assign an owner, and save notes. Resolution requires a documented disposition.
3. Inventory: select a model, review stock and observed deployments by ship-to location, then change lead-time/buffer assumptions. Recommendations are scenario estimates requiring a human review.
4. Offboarding: use the explicitly synthetic departure examples and save a demo return checklist. No actual departures are asserted and no messages are sent. Demo checklist storage is browser-local.
5. Data sources: download original files or import additional .xlsx/.csv exports. Source format and export date are validated; duplicate files do not duplicate records. Monitoring recalculates after import.

## Import formats

Choose a source type and the actual extraction/run date. Upload one single-sheet export at a time. Inventory is treated as a complete snapshot within a consistent scope. Partial snapshots or different filters can distort counts and movements; the UI calls this limitation out. Reconciliation outputs are not input exports.

Supported exports: inventory (`serial_number`, `model`, `install_status`); custom/bulk orders; PO/AP invoice report; AP summary; EAM's Success/Warning/Error line sections; manual billing. Original columns are preserved in row-level evidence. For EAM, one principal asset row per billing ID is used; split-account continuation rows are not new assets.

Departure CSV header:

```csv
person_id,person_name,departure_date,manager,asset_serial
employee-123,Example Person,2026-11-01,Program Manager,EXPLICIT-ASSET-SERIAL
```

An actual person-ID join requires an inventory assignee ID field (`assigned_to.user_name` or `assigned_to.sys_id`). The supplied inventory lacks it. An optional asset_serial provides an explicit link from the departure file; the UI identifies that method. Imported departure return plans are read-only in this version; demo checklists are editable.

## Rules and limitations

- Original exports are copied into `data/uploads`; every import retains SHA-256, type, source date, sheet, and row cells.
- Inventory matches exact serials after trimming and uppercasing; it does not merge similar serials or model variants. Order ship-to is a location proxy. Reported stock excludes known assignees but cannot exclude unprovided reservations or inspection holds.
- Observed demand counts matched In stock → In use transitions. It does not capture fulfilled-and-returned activity between snapshots, transfers, unmet requests, or newly appearing historical assets. The scenario uses observation rate × (lead days + buffer days), minus reported stock and estimated timely inbound supply. Canceled/requested orders are excluded, and overdue/missing ETAs do not count as timely supply.
- Rejections remain open until an equal-amount (within $1.50) later EAM success matches serial, REQ, and RITM, or a person records a disposition. The tolerance is provisional. Manual CHARGE/CREDIT input alone does not establish posting or resolve a rejection.
- Deployment-without-billing flags use a 30-day default grace period and limited supplied billing coverage. They are investigation candidates, not claims of unpaid revenue. Program fees and posted recovery are not modeled yet.
- Saved decisions persist in SQLite. Material changes in exception description/amount reopen a resolved candidate; unchanged evidence preserves its disposition. Historical decisions remain stored even when later success removes a candidate from the current list.
- Imported AP summaries are retained and downloadable; automated allocation-to-invoice tie-outs and pricing discrepancy rules remain a next iteration. Asset timelines currently use the PO-linked invoice allocation report. No full return/retirement or refresh scheduling engine exists yet.
- To load the supplied July/August export layout explicitly into an empty database, run `python app.py --seed-folder "/path/to/Hardware Management"`. Startup otherwise does not import files automatically. Preloaded inventory dates are Aug 14 / Sep 14, 2026; August order exports are Sep 8, EAM Jul 28 / Aug 28, and manual batches Jul 29 / Aug 26. This app does not treat folder months as extraction dates.

## Validate

```sh
.venv/bin/python -m unittest -v test_engine.py
```

Tests cover duplicate imports, rejected invalid schemas, stock movements, canceled/requested inbound supply, unknown ETAs, billing error/success behavior, manual input versus posting, and missing serials. Tests use synthetic fixtures and require no private exports.

Source: `app.py` (local server), `engine.py` (parsers/rules), `static/` (interface). Data stays in this application folder. No build step or Node installation is needed.

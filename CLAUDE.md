# CLAUDE.md — Project root context

CMPT 354 (Database Systems) library DBMS project. SQLite database, built via two
Jupyter notebooks, consumed by a CLI app and a Flask web app. Full schema/table
reference lives in `library_webapp/CLAUDE.md` — this file covers root-level
project structure, tooling, and conventions not covered there.

## File structure

```
library_schema.ipynb    # DDL: creates all tables, indexes, triggers, seeds lookup tables
library_populate.ipynb  # Faker-generated sample data (run AFTER library_schema.ipynb)
library.db              # SQLite db used by library_app.py (CLI)
library-2.db            # Stray tracked file, unreferenced by any code — not kept in sync
library_app.py          # CLI app, reads ./library.db
library_webapp/
  app.py                 # Flask app, reads ./library_webapp/library.db (separate copy)
  library.db
  CLAUDE.md              # Full schema reference, business rules, template/design system docs
```

**Two separate `library.db` copies exist** (root and `library_webapp/`) — they are
NOT the same file and are not auto-synced. After regenerating the root `library.db`,
manually `cp library.db library_webapp/library.db` if the web app also needs the update.

## Environment / tooling

- Managed with `uv` (`pyproject.toml` + `.venv`), **not pip** — `.venv` has no `pip`
  module installed, so use `uv add <pkg>` / `uv run <cmd>`.
- `faker`, `nbconvert`, and `ipykernel` were added as dev dependencies specifically to
  execute the notebooks headlessly:
  ```bash
  uv run jupyter nbconvert --to notebook --execute --inplace library_schema.ipynb
  uv run jupyter nbconvert --to notebook --execute --inplace library_populate.ipynb
  ```
  Must run in this order — `library_populate.ipynb` assumes the schema/lookup tables
  already exist.

## Rebuilding the database from scratch

1. Delete `library.db` (and `library_webapp/library.db` if the web app needs it too) —
   the notebooks use `CREATE TABLE IF NOT EXISTS`, so they won't wipe existing data on
   their own.
2. Run `library_schema.ipynb`, then `library_populate.ipynb` (via `uv run jupyter
   nbconvert ... --execute --inplace`, or interactively).
3. Copy the resulting root `library.db` into `library_webapp/library.db` if needed.

## Data model decisions specific to this project (not generic BCNF design)

- **Single library.** The schema supports multiple libraries (`Library` table,
  `library_id` FK everywhere), but this project's populated data intentionally has
  exactly **one** row: `library_id=1, name='SFU Library', address='8888 University
  Dr W, Burnaby, BC V5A 1S6'`. All Personnel/Item/Member/Room rows are allocated to
  it. Don't reintroduce multi-library sample data without being asked — the CLI and
  web app both already handle N libraries fine (they query `Library` dynamically), so
  no app code depends on there being exactly one.

- **`Acquisition_Status` is a procurement pipeline, not an acquisition source.**
  Values are `Not Yet Ordered`, `Ordered`, `Acquired` (previously `Purchased`,
  `Donated`, `Transferred` — changed on request). The donate-item flow in both
  `library_app.py` and `library_webapp/app.py` inserts new `Item` rows with
  acquisition status looked up by `status_name='Acquired'` (previously
  `'Donated'`) — if this enum changes again, grep both files for
  `Acquisition_Status WHERE status_name=` and update the hardcoded value.

# CLAUDE.md — Library DBMS Project Context

This file gives Claude Code full context on the CMPT 354 library database project.
Place it in the root of the `library_webapp/` folder (alongside `app.py`).

---

## Project overview

A library Database Management System built for **CMPT 354 (Database Systems)** at SFU.
The project spans schema design, normalization, population, a CLI app, and a Flask web app.
The database is **SQLite**, stored in `library.db`.

---

## File structure

```
project-root/
├── library.db                  # SQLite database (populated)
├── library_schema.ipynb        # Step 4: DDL — creates all 23 tables, indexes, triggers
├── library_populate.ipynb      # Step 5: Faker-generated data, ≥10 rows per table
├── library_app.py              # Step 6a: CLI application (8 operations)
└── library_webapp/             # Step 6b: Flask web application
    ├── app.py                  # All 8 Flask routes
    ├── requirements.txt        # flask==3.1.3, gunicorn==22.0.0
    ├── Dockerfile              # For Google Cloud Run deployment
    ├── .dockerignore
    ├── README.md               # Local run + Cloud Run deploy instructions
    ├── CLAUDE.md               # ← this file
    └── templates/
        ├── base.html           # Shared layout, nav, CSS variables, flash messages
        ├── index.html          # Home dashboard (8 action cards)
        ├── items.html          # 1. Find an item (keyword + genre search)
        ├── borrow.html         # 2. Borrow an item
        ├── return.html         # 3. Return a borrowed item (with auto-fine logic)
        ├── donate.html         # 4. Donate an item
        ├── events.html         # 5. Find an event
        ├── register.html       # 6. Register for an event
        ├── volunteer.html      # 7. Volunteer for the library
        └── help.html           # 8. Ask for help from a librarian
```

---

## Database schema — all 23 relations

Derived from the E/R diagram via standard translation rules (Step 3, BCNF verified).

### Lookup / reference tables
```sql
Type(type_id PK, type_name UNIQUE)
Acquisition_Status(acquisition_status_id PK, status_name UNIQUE)
Copy_Status(copy_status_id PK, status_name UNIQUE)
Member_Status(member_status_id PK, status_name UNIQUE)
Request_Status(request_status_id PK, status_name UNIQUE)
Audience(audience_id PK, audience_type UNIQUE)
```

### Core entity tables
```sql
Library(library_id PK, name, address)
-- Populated data has exactly ONE row (library_id=1, 'SFU Library'); schema
-- supports multiple libraries but this project intentionally seeds only one.

Personnel(personnel_id PK, first_name, last_name, email UNIQUE, phone,
          role, start_date, salary CHECK(>=0),
          library_id FK→Library NOT NULL)

Item(item_id PK, title, publication_year CHECK(1000-9999), genre,
     library_id FK→Library NOT NULL,
     type_id FK→Type NOT NULL,
     acquisition_status_id FK→Acquisition_Status NOT NULL)

Author(author_id PK, first_name, last_name)

Item_Copy(item_copy_id PK, date_obtained,
          item_id FK→Item NOT NULL,
          copy_status_id FK→Copy_Status NOT NULL)

Member(member_id PK, first_name, last_name, email UNIQUE,
       library_id FK→Library NOT NULL,
       member_status_id FK→Member_Status NOT NULL)

Volunteer(member_id PK/FK→Member, start_date, availability)
-- ISA: Volunteer IS-A Member

Room(room_id PK, room_name, capacity CHECK(>0),
     library_id FK→Library NOT NULL)

Event(event_id PK, title, date, event_type,
      room_id FK→Room NOT NULL)
```

### Relationship / transaction tables
```sql
Written_By(item_id FK→Item, author_id FK→Author)     -- PK(item_id, author_id)
Targets(event_id FK→Event, audience_id FK→Audience)  -- PK(event_id, audience_id)

Registers_For(member_id FK→Member, event_id FK→Event,
              registration_date)                       -- PK(member_id, event_id)

Loan(loan_id PK, loan_date, due_date, returned_date NULL,
     member_id FK→Member NOT NULL,
     item_copy_id FK→Item_Copy NOT NULL,
     CHECK(due_date >= loan_date),
     CHECK(returned_date IS NULL OR returned_date >= loan_date))

Fine(loan_id FK→Loan, fine_type, amount CHECK(>0))    -- PK(loan_id, fine_type)

Payment(payment_id PK, date, amount CHECK(>0),
        loan_id FK→Fine(loan_id),
        fine_type FK→Fine(fine_type))                  -- composite FK

Donates(item_copy_id PK/FK→Item_Copy,
        member_id FK→Member NOT NULL,
        donation_date)

Help_Request(help_request_id PK, request_date, description,
             member_id FK→Member NOT NULL,
             personnel_id FK→Personnel NULL,           -- nullable: unassigned
             request_status_id FK→Request_Status NOT NULL)
```

---

## Triggers (8 total)

| Name | Table | When | Purpose |
|------|-------|------|---------|
| `trg_loan_insert_copy_status` | Loan | AFTER INSERT | Marks copy "Checked Out" |
| `trg_loan_return_copy_status` | Loan | AFTER UPDATE returned_date | Marks copy "Available" |
| `trg_loan_prevent_unavailable` | Loan | BEFORE INSERT | Blocks loan if copy not Available |
| `trg_loan_prevent_suspended_member` | Loan | BEFORE INSERT | Blocks loan for non-Active members |
| `trg_payment_no_overpay` | Payment | BEFORE INSERT | Cumulative payments ≤ fine amount |
| `trg_event_no_room_double_book` | Event | BEFORE INSERT | One event per room per date |
| `trg_event_capacity_check` | Registers_For | BEFORE INSERT | Registrations ≤ room capacity |
| `trg_volunteer_must_be_member` | Volunteer | BEFORE INSERT | Volunteer must exist in Member |

---

## Seeded reference data

```
Type:               Book, DVD, Magazine, Audiobook, E-Book
Acquisition_Status: Not Yet Ordered, Ordered, Acquired
Copy_Status:        Available, Checked Out, Lost, Damaged, Under Repair
Member_Status:      Active, Suspended, Expired
Request_Status:     Open, In Progress, Resolved, Closed
Audience:           Children, Teens, Adults, Seniors, General
```

---

## Flask app — `app.py`

### Key patterns

```python
# DB connection — per-request via Flask g, FK enforcement on
def get_db():
    g.db = sqlite3.connect(DB_PATH)
    g.db.row_factory = sqlite3.Row
    g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

# Read helper
def query(sql, params=()):     # → list[Row]
def query_one(sql, params=()):  # → Row | None

# Write helper (commits immediately)
def mutate(sql, params=()):    # → lastrowid
```

### Routes

| Route | Method(s) | Operation |
|-------|-----------|-----------|
| `/` | GET | Home dashboard |
| `/items` | GET | 1. Find an item (keyword + genre filter) |
| `/borrow` | GET, POST | 2. Borrow an item |
| `/return` | GET, POST | 3. Return a borrowed item |
| `/donate` | GET, POST | 4. Donate an item |
| `/events` | GET | 5. Find an event |
| `/register` | GET, POST | 6. Register for an event |
| `/volunteer` | GET, POST | 7. Volunteer |
| `/help` | GET, POST | 8. Ask for help |

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `library-dev-secret` | Flask session signing |
| `DB_PATH` | `./library.db` | Path to SQLite file |
| `PORT` | `5000` | HTTP port (Cloud Run injects `8080`) |
| `FLASK_DEBUG` | `0` | Set to `1` for auto-reload locally |

### Context processor
`inject_globals()` runs on every request and injects `libraries`, `item_types`,
and `today` into every template automatically — no need to pass them per route.

---

## Templates — design system

Defined entirely in `base.html` via CSS custom properties:

```css
--ink:       #1a1a2e   /* primary text */
--ink-soft:  #4a4a6a   /* secondary text, labels */
--rule:      #d8d4c8   /* borders, dividers */
--parchment: #f7f4ee   /* page background */
--page:      #ffffff   /* card background */
--accent:    #2d6a4f   /* primary green (buttons, focus) */
--accent-lt: #d8ede3   /* success badge background */
--warm:      #c77c3a   /* warning / overdue accent */
--error:     #b33a2e   /* error state */
```

Fonts: **Lora** (serif, headings) + **Inter** (sans, body/UI).

### Flash message categories
Use exactly these category strings in `flash(msg, category)`:
- `"success"` — green
- `"error"` — red
- `"warning"` — amber (used for overdue fines)
- `"info"` — blue

### Shared CSS classes
- `.card` — white box with border and shadow
- `.form-grid` — 2-column responsive grid (`.single` = 1 column)
- `.form-group` — label + input stack (`.span2` = full width)
- `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-sm`
- `.badge`, `.badge-green`, `.badge-grey`, `.badge-warm`
- `.table-wrap` + `table` — styled data table
- `.empty-state` — centred no-results block

---

## Business rules (enforced by triggers + app logic)

1. Only **Active** members may borrow items or volunteer
2. A copy must have `Copy_Status.status_name = 'Available'` to be loaned
3. Returning an item auto-sets `returned_date`; copy flips back to Available
4. Late returns auto-generate an `Overdue` fine at **$0.25/day**
5. Payment total across all payments for a fine cannot exceed `Fine.amount`
6. A room can host at most one event per calendar date
7. Event registrations are capped at `Room.capacity`
8. A volunteer must already exist as a Member row
9. `personnel_id` in `Help_Request` is NULL until a librarian is assigned
10. All dates stored as ISO-8601 strings (`YYYY-MM-DD`) — SQLite has no DATE type

---

## Running locally

```bash
cd library_webapp
pip install -r requirements.txt
# Copy library.db into this folder first
python app.py
# → http://localhost:5000
```

---

## Deploying to Google Cloud Run

```bash
# Build and push image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/library-app

# Deploy
gcloud run deploy library-app \
  --image gcr.io/YOUR_PROJECT_ID/library-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=your-secret-key-here
```

**SQLite + Cloud Run caveat:** the `.db` file is baked into the image — writes
don't survive redeployments. The production upgrade path is **Cloud SQL
(PostgreSQL)**: swap `sqlite3.connect()` for a `psycopg2` connection and rewrite
triggers as PostgreSQL functions.

---

## Normalization notes (Step 3)

All 23 relations are in **BCNF**. Most were cleared by shortcut:
- Two-attribute relations → automatically BCNF
- Single surrogate key, no competing determinant → BCNF
- Composite-key relations with no non-key attributes → BCNF

`Fine(loan_id, fine_type, amount)` has composite PK `(loan_id, fine_type)` because
one loan can incur multiple fine types (Overdue, Damaged, Lost) with different amounts.
`Payment` carries a composite FK referencing both columns of `Fine`'s PK.

`email` is a natural candidate key on both `Personnel` and `Member` (enforced with
`UNIQUE` constraint) but does not cause a BCNF violation since it determines the
entire row, not a proper subset.

"""
Library Database Application — CMPT 354 Step 6
================================================
CLI menu-driven app for library users.
Run:  python library_app.py
Requires library.db (built in Steps 4 & 5).
"""

import sqlite3
import os
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "library.db")

# ── DB connection ──────────────────────────────────────────────────────────────

def get_connection():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row          # column access by name
    con.execute("PRAGMA foreign_keys = ON;")
    return con

# ── Helpers ────────────────────────────────────────────────────────────────────

def divider(title=""):
    width = 54
    if title:
        print(f"\n{'─' * 4} {title} {'─' * (width - len(title) - 6)}")
    else:
        print("─" * width)

def prompt(label, required=True):
    while True:
        val = input(f"  {label}: ").strip()
        if val or not required:
            return val
        print("  ✗ This field is required.")

def choose(label, options):
    """Display a numbered list and return the chosen item."""
    print(f"\n  {label}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    while True:
        raw = input("  Enter number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  ✗ Invalid choice.")

def print_rows(rows, cols=None):
    """Pretty-print a list of sqlite3.Row objects."""
    if not rows:
        print("  (no results)")
        return
    keys = cols or rows[0].keys()
    col_widths = {k: max(len(str(k)), max(len(str(r[k] or "")) for r in rows)) for k in keys}
    header = "  " + "  ".join(str(k).ljust(col_widths[k]) for k in keys)
    print(header)
    print("  " + "  ".join("─" * col_widths[k] for k in keys))
    for row in rows:
        print("  " + "  ".join(str(row[k] or "").ljust(col_widths[k]) for k in keys))

# ── 1. Find an item ────────────────────────────────────────────────────────────

def find_item():
    divider("1 · Find an Item")
    keyword = prompt("Search by title keyword (or press Enter to list all)", required=False)
    genre   = prompt("Filter by genre (or press Enter to skip)", required=False)

    query = """
        SELECT i.item_id,
               i.title,
               i.publication_year AS year,
               i.genre,
               t.type_name        AS type,
               a.status_name      AS acq_status,
               l.name             AS library,
               GROUP_CONCAT(au.first_name || ' ' || au.last_name, ', ') AS authors,
               SUM(CASE WHEN cs.status_name = 'Available' THEN 1 ELSE 0 END) AS copies_available
        FROM   Item i
        JOIN   Type              t  ON t.type_id               = i.type_id
        JOIN   Acquisition_Status a ON a.acquisition_status_id = i.acquisition_status_id
        JOIN   Library           l  ON l.library_id            = i.library_id
        LEFT JOIN Written_By     wb ON wb.item_id              = i.item_id
        LEFT JOIN Author         au ON au.author_id            = wb.author_id
        LEFT JOIN Item_Copy      ic ON ic.item_id              = i.item_id
        LEFT JOIN Copy_Status    cs ON cs.copy_status_id       = ic.copy_status_id
        WHERE  1=1
    """
    params = []
    if keyword:
        query += " AND i.title LIKE ?"
        params.append(f"%{keyword}%")
    if genre:
        query += " AND i.genre LIKE ?"
        params.append(f"%{genre}%")
    query += " GROUP BY i.item_id ORDER BY i.title"

    with get_connection() as con:
        rows = con.execute(query, params).fetchall()

    print_rows(rows, cols=["item_id", "title", "year", "genre", "type", "authors", "copies_available", "library"])

# ── 2. Borrow an item ─────────────────────────────────────────────────────────

def borrow_item():
    divider("2 · Borrow an Item")
    member_id = prompt("Your member ID")
    item_id   = prompt("Item ID to borrow")

    with get_connection() as con:
        # Check member exists and is Active
        member = con.execute(
            """SELECT m.member_id, m.first_name, ms.status_name
               FROM Member m JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
               WHERE m.member_id = ?""", (member_id,)
        ).fetchone()
        if not member:
            print("  ✗ Member ID not found.")
            return
        if member["status_name"] != "Active":
            print(f"  ✗ Your account status is '{member['status_name']}'. Only Active members can borrow.")
            return

        # Find an available copy
        copy = con.execute(
            """SELECT ic.item_copy_id, i.title
               FROM Item_Copy ic
               JOIN Item      i  ON i.item_id        = ic.item_id
               JOIN Copy_Status cs ON cs.copy_status_id = ic.copy_status_id
               WHERE i.item_id = ? AND cs.status_name = 'Available'
               LIMIT 1""", (item_id,)
        ).fetchone()
        if not copy:
            print("  ✗ No available copies for that item right now.")
            return

        loan_date = date.today()
        due_date  = loan_date + timedelta(days=21)

        try:
            con.execute(
                """INSERT INTO Loan (loan_date, due_date, returned_date, member_id, item_copy_id)
                   VALUES (?, ?, NULL, ?, ?)""",
                (loan_date.isoformat(), due_date.isoformat(), member_id, copy["item_copy_id"])
            )
            con.commit()
            print(f"\n  ✓ Loan created for '{copy['title']}'")
            print(f"    Loan date : {loan_date}")
            print(f"    Due date  : {due_date}  (21 days)")
        except sqlite3.IntegrityError as e:
            print(f"  ✗ Could not create loan: {e}")

# ── 3. Return a borrowed item ─────────────────────────────────────────────────

def return_item():
    divider("3 · Return a Borrowed Item")
    member_id = prompt("Your member ID")

    with get_connection() as con:
        loans = con.execute(
            """SELECT l.loan_id, i.title, ic.item_copy_id, l.loan_date, l.due_date
               FROM   Loan l
               JOIN   Item_Copy ic ON ic.item_copy_id = l.item_copy_id
               JOIN   Item      i  ON i.item_id       = ic.item_id
               WHERE  l.member_id = ? AND l.returned_date IS NULL
               ORDER  BY l.due_date""", (member_id,)
        ).fetchall()

        if not loans:
            print("  ✗ No outstanding loans found for this member.")
            return

        print_rows(loans, cols=["loan_id", "title", "loan_date", "due_date"])
        loan_id = prompt("\n  Enter Loan ID to return")

        loan = next((l for l in loans if str(l["loan_id"]) == loan_id), None)
        if not loan:
            print("  ✗ Loan ID not found in your active loans.")
            return

        return_date = date.today()
        try:
            con.execute(
                "UPDATE Loan SET returned_date = ? WHERE loan_id = ?",
                (return_date.isoformat(), loan_id)
            )
            con.commit()
            print(f"\n  ✓ '{loan['title']}' returned on {return_date}.")

            # Check if late — auto-create Overdue fine
            due = date.fromisoformat(loan["due_date"])
            if return_date > due:
                days_late  = (return_date - due).days
                fine_amount = round(days_late * 0.25, 2)
                try:
                    con.execute(
                        "INSERT INTO Fine (loan_id, fine_type, amount) VALUES (?, 'Overdue', ?)",
                        (loan_id, fine_amount)
                    )
                    con.commit()
                    print(f"  ⚠  Item was {days_late} day(s) late. Overdue fine: ${fine_amount:.2f}")
                except sqlite3.IntegrityError:
                    pass   # fine already exists
            else:
                print("  ✓ Returned on time — no fine.")
        except sqlite3.IntegrityError as e:
            print(f"  ✗ Error: {e}")

# ── 4. Donate an item ─────────────────────────────────────────────────────────

def donate_item():
    divider("4 · Donate an Item")
    member_id = prompt("Your member ID")

    TYPES = None
    STATUSES = None
    with get_connection() as con:
        member = con.execute("SELECT member_id, first_name FROM Member WHERE member_id=?", (member_id,)).fetchone()
        if not member:
            print("  ✗ Member ID not found.")
            return
        TYPES   = [(r["type_id"],   r["type_name"])   for r in con.execute("SELECT type_id, type_name FROM Type")]
        donated_status_id = con.execute(
            "SELECT acquisition_status_id FROM Acquisition_Status WHERE status_name='Donated'"
        ).fetchone()["acquisition_status_id"]
        available_status_id = con.execute(
            "SELECT copy_status_id FROM Copy_Status WHERE status_name='Available'"
        ).fetchone()["copy_status_id"]
        library_ids = [(r["library_id"], r["name"]) for r in con.execute("SELECT library_id, name FROM Library")]

    print(f"\n  Hello, {member['first_name']}! Please describe the item you're donating.")
    title = prompt("Title")
    pub_year = prompt("Publication year (e.g. 2019)", required=False) or None
    genre  = prompt("Genre (e.g. Fiction)", required=False) or None

    type_labels  = [f"{tid} — {tn}" for tid, tn in TYPES]
    chosen_type  = choose("Item type:", type_labels)
    type_id      = TYPES[type_labels.index(chosen_type)][0]

    lib_labels   = [f"{lid} — {ln}" for lid, ln in library_ids]
    chosen_lib   = choose("Donate to which library?", lib_labels)
    library_id   = library_ids[lib_labels.index(chosen_lib)][0]

    today = date.today().isoformat()

    with get_connection() as con:
        try:
            cur = con.execute(
                """INSERT INTO Item (title, publication_year, genre, library_id, type_id, acquisition_status_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (title, pub_year, genre, library_id, type_id, donated_status_id)
            )
            item_id = cur.lastrowid

            cur2 = con.execute(
                """INSERT INTO Item_Copy (date_obtained, item_id, copy_status_id)
                   VALUES (?, ?, ?)""",
                (today, item_id, available_status_id)
            )
            copy_id = cur2.lastrowid

            con.execute(
                """INSERT INTO Donates (item_copy_id, member_id, donation_date) VALUES (?, ?, ?)""",
                (copy_id, member_id, today)
            )
            con.commit()
            print(f"\n  ✓ Thank you for your donation! Item ID: {item_id}, Copy ID: {copy_id}")
        except sqlite3.IntegrityError as e:
            print(f"  ✗ Donation failed: {e}")

# ── 5. Find an event ──────────────────────────────────────────────────────────

def find_event():
    divider("5 · Find an Event")
    keyword   = prompt("Search by event title keyword (or press Enter for all)", required=False)
    from_date = prompt("From date YYYY-MM-DD (or press Enter to skip)", required=False)

    query = """
        SELECT e.event_id,
               e.title,
               e.date,
               e.event_type,
               r.room_name,
               r.capacity,
               l.name AS library,
               COUNT(rf.member_id) AS registered,
               r.capacity - COUNT(rf.member_id) AS spots_left,
               GROUP_CONCAT(DISTINCT a.audience_type) AS audience
        FROM   Event e
        JOIN   Room  r ON r.room_id   = e.room_id
        JOIN   Library l ON l.library_id = r.library_id
        LEFT JOIN Registers_For rf ON rf.event_id = e.event_id
        LEFT JOIN Targets tg ON tg.event_id = e.event_id
        LEFT JOIN Audience a ON a.audience_id = tg.audience_id
        WHERE  1=1
    """
    params = []
    if keyword:
        query += " AND e.title LIKE ?"
        params.append(f"%{keyword}%")
    if from_date:
        query += " AND e.date >= ?"
        params.append(from_date)
    query += " GROUP BY e.event_id ORDER BY e.date"

    with get_connection() as con:
        rows = con.execute(query, params).fetchall()

    print_rows(rows, cols=["event_id", "title", "date", "event_type", "room_name", "library", "spots_left", "audience"])

# ── 6. Register for an event ──────────────────────────────────────────────────

def register_for_event():
    divider("6 · Register for an Event")
    member_id = prompt("Your member ID")
    event_id  = prompt("Event ID to register for")

    with get_connection() as con:
        member = con.execute("SELECT member_id, first_name FROM Member WHERE member_id=?", (member_id,)).fetchone()
        if not member:
            print("  ✗ Member ID not found.")
            return

        event = con.execute(
            """SELECT e.event_id, e.title, e.date, r.capacity,
                      COUNT(rf.member_id) AS registered
               FROM Event e
               JOIN Room r ON r.room_id = e.room_id
               LEFT JOIN Registers_For rf ON rf.event_id = e.event_id
               WHERE e.event_id = ?
               GROUP BY e.event_id""", (event_id,)
        ).fetchone()
        if not event:
            print("  ✗ Event not found.")
            return

        already = con.execute(
            "SELECT 1 FROM Registers_For WHERE member_id=? AND event_id=?", (member_id, event_id)
        ).fetchone()
        if already:
            print("  ✗ You are already registered for this event.")
            return

        try:
            con.execute(
                """INSERT INTO Registers_For (member_id, event_id, registration_date)
                   VALUES (?, ?, ?)""",
                (member_id, event_id, date.today().isoformat())
            )
            con.commit()
            print(f"\n  ✓ Registered for '{event['title']}' on {event['date']}.")
        except sqlite3.IntegrityError as e:
            # Trigger T7 fires here if capacity is exceeded
            print(f"  ✗ Registration failed: {e}")

# ── 7. Volunteer for the library ──────────────────────────────────────────────

def volunteer():
    divider("7 · Volunteer for the Library")
    member_id = prompt("Your member ID")

    with get_connection() as con:
        member = con.execute(
            """SELECT m.member_id, m.first_name, ms.status_name
               FROM Member m JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
               WHERE m.member_id = ?""", (member_id,)
        ).fetchone()
        if not member:
            print("  ✗ Member ID not found.")
            return
        if member["status_name"] != "Active":
            print(f"  ✗ Your account is '{member['status_name']}'. Only Active members can volunteer.")
            return

        existing = con.execute("SELECT 1 FROM Volunteer WHERE member_id=?", (member_id,)).fetchone()
        if existing:
            print("  ✗ You are already registered as a volunteer.")
            return

    SLOTS = ["Weekday mornings", "Weekday afternoons", "Weekends", "Flexible"]
    availability = choose("Your availability:", SLOTS)

    with get_connection() as con:
        try:
            con.execute(
                "INSERT INTO Volunteer (member_id, start_date, availability) VALUES (?, ?, ?)",
                (member_id, date.today().isoformat(), availability)
            )
            con.commit()
            print(f"\n  ✓ Thank you, {member['first_name']}! You're now registered as a volunteer.")
            print(f"    Availability: {availability}")
        except sqlite3.IntegrityError as e:
            print(f"  ✗ Could not register: {e}")

# ── 8. Ask for help ───────────────────────────────────────────────────────────

def ask_for_help():
    divider("8 · Ask for Help from a Librarian")
    member_id = prompt("Your member ID")

    with get_connection() as con:
        member = con.execute("SELECT member_id, first_name FROM Member WHERE member_id=?", (member_id,)).fetchone()
        if not member:
            print("  ✗ Member ID not found.")
            return

    print(f"\n  Hello, {member['first_name']}. Please describe your request.")
    description = prompt("Description of your request")

    with get_connection() as con:
        open_status_id = con.execute(
            "SELECT request_status_id FROM Request_Status WHERE status_name='Open'"
        ).fetchone()["request_status_id"]

        try:
            cur = con.execute(
                """INSERT INTO Help_Request (request_date, description, member_id, personnel_id, request_status_id)
                   VALUES (?, ?, ?, NULL, ?)""",
                (date.today().isoformat(), description, member_id, open_status_id)
            )
            con.commit()
            print(f"\n  ✓ Help request #{cur.lastrowid} submitted. A librarian will follow up with you.")
        except sqlite3.IntegrityError as e:
            print(f"  ✗ Could not submit request: {e}")

# ── Main menu ─────────────────────────────────────────────────────────────────

MENU = [
    ("Find an item in the library",       find_item),
    ("Borrow an item",                     borrow_item),
    ("Return a borrowed item",             return_item),
    ("Donate an item to the library",      donate_item),
    ("Find an event in the library",       find_event),
    ("Register for an event",              register_for_event),
    ("Volunteer for the library",          volunteer),
    ("Ask for help from a librarian",      ask_for_help),
]

def main():
    if not os.path.exists(DB_PATH):
        print(f"✗ Database not found at {DB_PATH}")
        print("  Run library_schema.ipynb and library_populate.ipynb first.")
        return

    while True:
        print("\n╔══════════════════════════════════════════════════════╗")
        print("║           Library Database Application               ║")
        print("╠══════════════════════════════════════════════════════╣")
        for i, (label, _) in enumerate(MENU, 1):
            print(f"║  {i}.  {label:<49}║")
        print("║  0.  Exit                                            ║")
        print("╚══════════════════════════════════════════════════════╝")

        choice = input("\nSelect an option: ").strip()
        if choice == "0":
            print("\n  Goodbye!\n")
            break
        elif choice.isdigit() and 1 <= int(choice) <= len(MENU):
            MENU[int(choice) - 1][1]()
        else:
            print("  ✗ Invalid option. Please enter a number from the menu.")

if __name__ == "__main__":
    main()

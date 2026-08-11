"""
Library Web Application — CMPT 354 Step 6
Flask + SQLite, deployable to Google Cloud Run.
"""

import os
import sqlite3
from datetime import date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, g, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "library-dev-secret")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "library.db"))

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql, params=()):
    return get_db().execute(sql, params).fetchall()

def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()

def mutate(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid

# ── Auth ───────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "member_id" not in session:
            flash("Please log in to access this page.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── Context: lookup data used in forms ────────────────────────────────────────

@app.context_processor
def inject_globals():
    try:
        libraries = query("SELECT library_id, name FROM Library ORDER BY name")
        types     = query("SELECT type_id, type_name FROM Type ORDER BY type_name")
    except Exception:
        libraries, types = [], []

    current_member = None
    if "member_id" in session:
        try:
            current_member = query_one(
                """SELECT m.member_id, m.first_name, m.last_name, ms.status_name
                   FROM Member m
                   JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
                   WHERE m.member_id = ?""", (session["member_id"],)
            )
        except Exception:
            pass

    return dict(libraries=libraries, item_types=types, today=date.today().isoformat(),
                current_member=current_member)

# ── Login / Logout ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "member_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        member = query_one(
            """SELECT m.member_id, m.first_name, m.last_name, ms.status_name
               FROM Member m
               JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
               WHERE LOWER(m.email) = ?""", (email,)
        )
        if not member:
            flash("No member account found with that email address.", "error")
            return redirect(url_for("login"))
        session["member_id"] = member["member_id"]
        flash(f"Welcome back, {member['first_name']}!", "success")
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ── Home ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── 1. Find an item ───────────────────────────────────────────────────────────

@app.route("/items")
def items():
    keyword = request.args.get("keyword", "").strip()
    genre   = request.args.get("genre",   "").strip()

    sql = """
        SELECT i.item_id,
               i.title,
               i.publication_year AS year,
               i.genre,
               t.type_name        AS type,
               l.name             AS library,
               GROUP_CONCAT(DISTINCT au.first_name || ' ' || au.last_name) AS authors,
               COUNT(DISTINCT CASE WHEN cs.status_name = 'Available' THEN ic.item_copy_id END) AS copies_available
        FROM   Item i
        JOIN   Type              t  ON t.type_id               = i.type_id
        JOIN   Library           l  ON l.library_id            = i.library_id
        LEFT JOIN Written_By     wb ON wb.item_id              = i.item_id
        LEFT JOIN Author         au ON au.author_id            = wb.author_id
        LEFT JOIN Item_Copy      ic ON ic.item_id              = i.item_id
        LEFT JOIN Copy_Status    cs ON cs.copy_status_id       = ic.copy_status_id
        WHERE  1=1
    """
    params = []
    if keyword:
        sql += " AND i.title LIKE ?"
        params.append(f"%{keyword}%")
    if genre:
        sql += " AND i.genre LIKE ?"
        params.append(f"%{genre}%")
    sql += " GROUP BY i.item_id ORDER BY i.title"

    results = query(sql, params)
    genres  = [r[0] for r in query("SELECT DISTINCT genre FROM Item WHERE genre IS NOT NULL ORDER BY genre")]
    return render_template("items.html", results=results, genres=genres,
                           keyword=keyword, selected_genre=genre)

# ── 2. Borrow an item ─────────────────────────────────────────────────────────

@app.route("/borrow", methods=["GET", "POST"])
@login_required
def borrow():
    if request.method == "POST":
        member_id = session["member_id"]
        item_id   = request.form.get("item_id", "").strip()

        member = query_one(
            """SELECT m.member_id, m.first_name, ms.status_name
               FROM Member m JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
               WHERE m.member_id = ?""", (member_id,)
        )
        if member["status_name"] != "Active":
            flash(f"Your account is '{member['status_name']}'. Only Active members can borrow.", "error")
            return redirect(url_for("borrow"))

        copy = query_one(
            """SELECT ic.item_copy_id, i.title
               FROM Item_Copy ic
               JOIN Item       i  ON i.item_id         = ic.item_id
               JOIN Copy_Status cs ON cs.copy_status_id = ic.copy_status_id
               WHERE i.item_id = ? AND cs.status_name = 'Available'
               LIMIT 1""", (item_id,)
        )
        if not copy:
            flash("No available copies for that item right now.", "error")
            return redirect(url_for("borrow"))

        loan_date = date.today()
        due_date  = loan_date + timedelta(days=21)
        try:
            mutate(
                """INSERT INTO Loan (loan_date, due_date, returned_date, member_id, item_copy_id)
                   VALUES (?, ?, NULL, ?, ?)""",
                (loan_date.isoformat(), due_date.isoformat(), member_id, copy["item_copy_id"])
            )
            flash(f"'{copy['title']}' borrowed successfully! Due back by {due_date}.", "success")
        except sqlite3.IntegrityError as e:
            flash(f"Could not borrow: {e}", "error")
        return redirect(url_for("items"))

    return redirect(url_for("items"))

# ── 3. Return an item ─────────────────────────────────────────────────────────

@app.route("/return", methods=["GET", "POST"])
@login_required
def return_item():
    member_id = session["member_id"]

    if request.method == "POST":
        loan_id = request.form.get("loan_id")
        loan = query_one(
            "SELECT loan_id, due_date FROM Loan WHERE loan_id=? AND member_id=? AND returned_date IS NULL",
            (loan_id, member_id)
        )
        if not loan:
            flash("Loan not found or already returned.", "error")
        else:
            return_date = date.today()
            mutate("UPDATE Loan SET returned_date=? WHERE loan_id=?",
                   (return_date.isoformat(), loan_id))
            due = date.fromisoformat(loan["due_date"])
            if return_date > due:
                days_late   = (return_date - due).days
                fine_amount = round(days_late * 0.25, 2)
                try:
                    mutate("INSERT INTO Fine (loan_id, fine_type, amount) VALUES (?, 'Overdue', ?)",
                           (loan_id, fine_amount))
                    flash(f"Returned! Item was {days_late} day(s) late — overdue fine: ${fine_amount:.2f}.", "warning")
                except sqlite3.IntegrityError:
                    flash("Returned! (Fine already recorded.)", "success")
            else:
                flash("Item returned on time — no fine.", "success")
        return redirect(url_for("return_item"))

    loans = query(
        """SELECT l.loan_id, i.title, l.loan_date, l.due_date
           FROM   Loan l
           JOIN   Item_Copy ic ON ic.item_copy_id = l.item_copy_id
           JOIN   Item      i  ON i.item_id       = ic.item_id
           WHERE  l.member_id = ? AND l.returned_date IS NULL
           ORDER  BY l.due_date""", (member_id,)
    )
    return render_template("return.html", loans=loans)

# ── 4. Donate an item ─────────────────────────────────────────────────────────

@app.route("/donate", methods=["GET", "POST"])
@login_required
def donate():
    if request.method == "POST":
        member_id  = session["member_id"]
        title      = request.form.get("title",     "").strip()
        pub_year   = request.form.get("pub_year",  "").strip() or None
        genre      = request.form.get("genre",     "").strip() or None
        type_id    = request.form.get("type_id",   "").strip()
        library_id = request.form.get("library_id","").strip()

        donated_status = query_one(
            "SELECT acquisition_status_id FROM Acquisition_Status WHERE status_name='Donated'"
        )
        available_status = query_one(
            "SELECT copy_status_id FROM Copy_Status WHERE status_name='Available'"
        )
        today = date.today().isoformat()

        db = get_db()
        try:
            cur = db.execute(
                """INSERT INTO Item (title, publication_year, genre, library_id, type_id, acquisition_status_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (title, pub_year, genre, library_id, type_id, donated_status["acquisition_status_id"])
            )
            item_id = cur.lastrowid
            cur2 = db.execute(
                "INSERT INTO Item_Copy (date_obtained, item_id, copy_status_id) VALUES (?, ?, ?)",
                (today, item_id, available_status["copy_status_id"])
            )
            copy_id = cur2.lastrowid
            db.execute(
                "INSERT INTO Donates (item_copy_id, member_id, donation_date) VALUES (?, ?, ?)",
                (copy_id, member_id, today)
            )
            db.commit()
            flash(f"Thank you for donating '{title}'! It's now in our catalogue.", "success")
        except sqlite3.IntegrityError as e:
            db.rollback()
            flash(f"Donation failed: {e}", "error")
        return redirect(url_for("donate"))

    return render_template("donate.html")

# ── 5. Find an event ──────────────────────────────────────────────────────────

@app.route("/events")
def events():
    keyword   = request.args.get("keyword",   "").strip()
    from_date = request.args.get("from_date", "").strip()

    sql = """
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
        JOIN   Room    r  ON r.room_id    = e.room_id
        JOIN   Library l  ON l.library_id = r.library_id
        LEFT JOIN Registers_For rf ON rf.event_id   = e.event_id
        LEFT JOIN Targets        tg ON tg.event_id  = e.event_id
        LEFT JOIN Audience        a  ON a.audience_id = tg.audience_id
        WHERE  1=1
    """
    params = []
    if keyword:
        sql += " AND e.title LIKE ?"
        params.append(f"%{keyword}%")
    if from_date:
        sql += " AND e.date >= ?"
        params.append(from_date)
    sql += " GROUP BY e.event_id ORDER BY e.date"

    results = query(sql, params)
    return render_template("events.html", results=results,
                           keyword=keyword, from_date=from_date)

# ── 6. Register for an event ──────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "POST":
        member_id = session["member_id"]
        event_id  = request.form.get("event_id", "").strip()

        event = query_one(
            """SELECT e.event_id, e.title, e.date, r.capacity,
                      COUNT(rf.member_id) AS registered
               FROM Event e
               JOIN Room r ON r.room_id = e.room_id
               LEFT JOIN Registers_For rf ON rf.event_id = e.event_id
               WHERE e.event_id = ?
               GROUP BY e.event_id""", (event_id,)
        )
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for("register"))

        already = query_one(
            "SELECT 1 FROM Registers_For WHERE member_id=? AND event_id=?", (member_id, event_id)
        )
        if already:
            flash("You are already registered for this event.", "info")
            return redirect(url_for("register"))

        try:
            mutate(
                "INSERT INTO Registers_For (member_id, event_id, registration_date) VALUES (?,?,?)",
                (member_id, event_id, date.today().isoformat())
            )
            flash(f"Registered for '{event['title']}' on {event['date']}.", "success")
        except sqlite3.IntegrityError as e:
            flash(f"Registration failed: {e}", "error")
        return redirect(url_for("register"))

    event_list = query(
        """SELECT e.event_id, e.title, e.date, e.event_type,
                  r.capacity - COUNT(rf.member_id) AS spots_left
           FROM Event e
           JOIN Room r ON r.room_id = e.room_id
           LEFT JOIN Registers_For rf ON rf.event_id = e.event_id
           GROUP BY e.event_id
           HAVING spots_left > 0
           ORDER BY e.date"""
    )
    return render_template("register.html", event_list=event_list)

# ── 7. Volunteer ──────────────────────────────────────────────────────────────

@app.route("/volunteer", methods=["GET", "POST"])
@login_required
def volunteer():
    if request.method == "POST":
        member_id    = session["member_id"]
        availability = request.form.get("availability", "").strip()

        member = query_one(
            """SELECT m.member_id, m.first_name, ms.status_name
               FROM Member m JOIN Member_Status ms ON ms.member_status_id = m.member_status_id
               WHERE m.member_id = ?""", (member_id,)
        )
        if member["status_name"] != "Active":
            flash(f"Your account is '{member['status_name']}'. Only Active members can volunteer.", "error")
            return redirect(url_for("volunteer"))

        existing = query_one("SELECT 1 FROM Volunteer WHERE member_id=?", (member_id,))
        if existing:
            flash("You are already registered as a volunteer.", "info")
            return redirect(url_for("volunteer"))

        try:
            mutate(
                "INSERT INTO Volunteer (member_id, start_date, availability) VALUES (?,?,?)",
                (member_id, date.today().isoformat(), availability)
            )
            flash(f"Thank you, {member['first_name']}! You're now registered as a volunteer.", "success")
        except sqlite3.IntegrityError as e:
            flash(f"Could not register: {e}", "error")
        return redirect(url_for("volunteer"))

    return render_template("volunteer.html")

# ── 8. Ask for help ───────────────────────────────────────────────────────────

@app.route("/help", methods=["GET", "POST"])
@login_required
def ask_help():
    if request.method == "POST":
        member_id   = session["member_id"]
        description = request.form.get("description", "").strip()

        open_status = query_one(
            "SELECT request_status_id FROM Request_Status WHERE status_name='Open'"
        )
        try:
            req_id = mutate(
                """INSERT INTO Help_Request (request_date, description, member_id, personnel_id, request_status_id)
                   VALUES (?,?,?,NULL,?)""",
                (date.today().isoformat(), description, member_id, open_status["request_status_id"])
            )
            flash(f"Help request #{req_id} submitted. A librarian will be in touch.", "success")
        except sqlite3.IntegrityError as e:
            flash(f"Could not submit: {e}", "error")
        return redirect(url_for("ask_help"))

    return render_template("help.html")

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")

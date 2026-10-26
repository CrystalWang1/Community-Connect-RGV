"""SQLite sample data. Replace fictional listings with verified local records."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).with_name("resources.db")

SAMPLES = [
    ("Neighborhood Pantry Demo", "Food", "Weekly grocery pickup for households. Check availability before visiting.", "Offers grocery pickup for families. Call ahead to confirm hours and requirements.", "100 Demo Plaza", "McAllen", "TX", "78501", "(000) 000-0000", "Weekdays, 9 AM–3 PM", 1, None),
    ("Community Wellness Demo", "Health", "Basic health screenings and information sessions for residents.", "Offers basic health screenings and help finding follow-up care.", "200 Demo Plaza", "McAllen", "TX", "78501", "(000) 000-0000", "Mon–Thu, 10 AM–4 PM", 1, None),
    ("Homework Club Demo", "Student", "After-school homework support for grades 3–8; registration is requested.", "Homework help for grades 3–8 after school. Registration requested.", "300 Demo Plaza", "McAllen", "TX", "78504", "(000) 000-0000", "School days, 3–6 PM", 1, None),
    ("Family Park Demo", "Parks", "Outdoor playground and walking area. Some organized activities may charge a fee.", "A park with a playground and walking paths. Check activity fees separately.", "400 Demo Plaza", "McAllen", "TX", "78501", "(000) 000-0000", "Daily, 7 AM–8 PM", 1, None),
    ("Weekend Nature Walk Demo", "Events", "A guided family nature walk. Registration is requested.", "A free guided family nature walk. Sign up before going.", "500 Demo Plaza", "McAllen", "TX", "78501", "(000) 000-0000", "10 AM–noon", 1, 5),
    ("Brownsville Food Shelf Demo", "Food", "Pantry support for local households; supplies vary.", "Offers pantry supplies. Call first to check availability.", "100 Sample Street", "Brownsville", "TX", "78520", "(000) 000-0000", "Tue–Fri, 9 AM–2 PM", 1, None),
    ("Brownsville Arts Day Demo", "Events", "Family art activities and a community workshop.", "An afternoon of art activities for families. Some materials may cost extra.", "200 Sample Street", "Brownsville", "TX", "78520", "(000) 000-0000", "1–4 PM", 0, 12),
    ("Edinburg Youth Center Demo", "Student", "Tutoring, games, and supervised enrichment for school-age children.", "After-school tutoring and supervised activities for children.", "100 Example Avenue", "Edinburg", "TX", "78539", "(000) 000-0000", "School days, 3–6 PM", 1, None),
    ("Edinburg Screening Day Demo", "Events", "Community health screening event; advance registration preferred.", "Free health screening event. Register in advance if possible.", "200 Example Avenue", "Edinburg", "TX", "78539", "(000) 000-0000", "9 AM–1 PM", 1, 25),
]


SCHEMA = """CREATE TABLE resources (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    description TEXT NOT NULL, summary TEXT NOT NULL, address TEXT NOT NULL,
    city TEXT NOT NULL, state TEXT NOT NULL, zip TEXT NOT NULL,
    phone TEXT NOT NULL, hours TEXT NOT NULL, free INTEGER NOT NULL,
    event_date TEXT, link TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'approved', event_end_date TEXT)"""

EXPECTED_COLUMNS = [
    "id", "name", "category", "description", "summary", "address",
    "city", "state", "zip", "phone", "hours", "free", "event_date",
    "link", "status",
]


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with connect() as connection:
        connection.execute(SCHEMA.replace("CREATE TABLE resources", "CREATE TABLE IF NOT EXISTS resources"))

        # If resources.db already existed from an older schema (e.g. missing the
        # "link" or "status" columns), rebuild it instead of erroring later when read.
        existing_columns = [col[1] for col in connection.execute("PRAGMA table_info(resources)")]
        # Add new fields without deleting existing resources or submissions.
        for column, definition in {
            "summary": "TEXT NOT NULL DEFAULT ''",
            "link": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'approved'",
            "event_end_date": "TEXT",
        }.items():
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE resources ADD COLUMN {column} {definition}")

        if connection.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0:
            connection.executemany("""INSERT INTO resources
                (name, category, description, summary, address, city, state, zip, phone, hours, free, event_date, link, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(*record[:-1], (date.today() + timedelta(days=record[-1])).isoformat() if record[-1] is not None else None, "", "approved") for record in SAMPLES])


def load_resources():
    """Approved listings only — what the public page shows."""
    with connect() as connection:
        return connection.execute(
            "SELECT * FROM resources WHERE status = 'approved' ORDER BY city, category, name"
        ).fetchall()


def load_pending():
    """Submissions waiting for review, newest first."""
    with connect() as connection:
        return connection.execute(
            "SELECT * FROM resources WHERE status = 'pending' ORDER BY id DESC"
        ).fetchall()


def add_resource(name, category, description, summary, address, city, state, zip_code, phone, hours, free, event_date, link, event_end_date=None):
    """Insert a user-submitted resource/event as pending, awaiting approval."""
    with connect() as connection:
        connection.execute(
            """INSERT INTO resources
                (name, category, description, summary, address, city, state, zip, phone, hours, free, event_date, link, event_end_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (name, category, description, summary, address, city, state, zip_code, phone, hours, int(free), event_date, link, event_end_date),
        )


def set_status(resource_id, status):
    """status: 'approved' or 'rejected'."""
    from auth import require_admin
    require_admin()
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError("Invalid status")
    with connect() as connection:
        connection.execute("UPDATE resources SET status = ? WHERE id = ?", (status, resource_id))


def load_admin_resources():
    from auth import require_admin
    require_admin()
    with connect() as connection:
        return connection.execute("SELECT * FROM resources ORDER BY id DESC").fetchall()


def update_resource(resource_id, **fields):
    from auth import require_admin
    require_admin()
    allowed = {"name", "category", "summary", "description", "address", "city", "state", "zip", "phone", "hours", "free", "link", "event_date", "event_end_date"}
    if not fields or not set(fields) <= allowed:
        raise ValueError("Invalid resource fields")
    assignments = ", ".join(f"{field}=?" for field in fields)
    with connect() as connection:
        connection.execute(f"UPDATE resources SET {assignments} WHERE id=?", (*fields.values(), resource_id))


def delete_resource(resource_id):
    from auth import require_admin
    require_admin()
    with connect() as connection:
        connection.execute("DELETE FROM resources WHERE id=?", (resource_id,))
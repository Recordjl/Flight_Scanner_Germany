"""SQLite price history, committed back to the repo by GitHub Actions."""
import json
import sqlite3

from .config import ROOT

DB_PATH = ROOT / "data" / "history.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fares (
    run_date TEXT, key TEXT, kind TEXT, source TEXT, program TEXT, cabin TEXT,
    origin TEXT, destination TEXT, depart_date TEXT, return_date TEXT,
    seats INTEGER, price REAL, taxes REAL, payload TEXT
);
CREATE INDEX IF NOT EXISTS fares_key ON fares(key);
CREATE TABLE IF NOT EXISTS seen_posts (url TEXT PRIMARY KEY, first_seen TEXT);
"""


class Store:
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def previous_low(self, key):
        row = self.db.execute("SELECT MIN(price) FROM fares WHERE key = ?", (key,)).fetchone()
        return row[0]

    def best_ever(self, kind, cabin):
        row = self.db.execute(
            "SELECT MIN(price) FROM fares WHERE kind = ? AND cabin = ?", (kind, cabin)
        ).fetchone()
        return row[0]

    def save(self, run_date, fares):
        self.db.executemany(
            "INSERT INTO fares VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_date, f.key, f.kind, f.source, f.program, f.cabin, f.origin, f.destination,
              f.depart_date, f.return_date, f.seats, f.price_per_person, f.taxes_per_person,
              json.dumps(f.to_dict())) for f in fares],
        )
        self.db.commit()

    def is_new_post(self, url, run_date):
        cur = self.db.execute(
            "INSERT OR IGNORE INTO seen_posts VALUES (?, ?)", (url, run_date)
        )
        self.db.commit()
        return cur.rowcount == 1

    def close(self):
        self.db.close()

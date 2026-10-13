"""
Database helpers.

Flask handles one web request at a time per thread. The usual pattern is:
open one SQLite connection the first time a request needs it, keep it on
Flask's `g` object (a per-request scratchpad), and close it when the request
ends. These helpers do exactly that.
"""
import sqlite3
from pathlib import Path

from flask import g

# Keep all file paths relative to this file, so the app works no matter
# which folder you start it from.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "access.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def connect():
    """Open a new SQLite connection with the settings we always want."""
    conn = sqlite3.connect(DATABASE_PATH)
    # Rows come back like dicts: row["name"] instead of row[1].
    conn.row_factory = sqlite3.Row
    # SQLite does NOT enforce foreign keys unless you switch them on, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return this web request's connection, opening it on first use."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exception=None):
    """Close the connection at the end of a web request (registered in app.py)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(conn):
    """Create the tables from schema.sql (drops existing tables first)."""
    conn.executescript(SCHEMA_PATH.read_text())

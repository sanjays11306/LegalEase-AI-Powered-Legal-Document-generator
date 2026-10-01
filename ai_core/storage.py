"""Saved drafts (SQLite, standard library only).

Every query is scoped to an `owner` so one user can never read or delete another user's documents.
The database path comes from LEGALEASE_DB (default: data/legalease.db next to the project).

Privacy note: drafts contain names, addresses and amounts. Keep the file out of git (see .gitignore),
back it up, and put it on an encrypted disk when deployed.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, NamedTuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'English',
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    effective_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner, updated_at DESC);
CREATE TABLE IF NOT EXISTS usage (
    owner TEXT NOT NULL,
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, day, kind)
);
"""


class SavedDoc(NamedTuple):
    id: int
    doc_type: str
    language: str
    title: str
    text: str
    details: dict
    effective_date: str
    created_at: str
    updated_at: str


def db_path() -> Path:
    p = Path(os.getenv("LEGALEASE_DB", "") or Path(__file__).resolve().parent.parent / "data" / "legalease.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """One short-lived connection per operation (safe with Streamlit threads and several workers)."""
    con = sqlite3.connect(db_path(), timeout=10, isolation_level=None)   # autocommit; we BEGIN explicitly
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        yield con
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: sqlite3.Row) -> SavedDoc:
    return SavedDoc(r["id"], r["doc_type"], r["language"], r["title"], r["text"], json.loads(r["details"] or "{}"),
                    r["effective_date"], r["created_at"], r["updated_at"])


def make_title(text: str, details: dict | None = None, doc_type: str = "") -> str:
    """'Lease Agreement - Asha Rao & Ravi Kumar' (falls back to the first line of the text)."""
    d = details or {}
    names = " & ".join(n for n in (d.get("party1_name"), d.get("party2_name")) if n)
    first = next((l.strip().strip("*# ") for l in text.split("\n") if l.strip()), "Untitled document")
    return f"{doc_type or first} - {names}"[:120] if names else (doc_type or first)[:120]


def save_document(owner: str, doc_type: str, text: str, details: dict | None = None, language: str = "English",
                  effective_date: str = "", doc_id: int | None = None, title: str = "") -> int:
    """Insert a new draft, or update `doc_id` if it belongs to `owner`. Returns the document id."""
    if not text.strip():
        raise ValueError("Refusing to save an empty document.")
    title = title or make_title(text, details, doc_type)
    blob = json.dumps(details or {}, ensure_ascii=False)
    with connect() as con:
        if doc_id is not None:
            cur = con.execute("UPDATE documents SET text=?, title=?, details=?, language=?, effective_date=?, updated_at=? "
                              "WHERE id=? AND owner=?", (text, title, blob, language, effective_date, _now(), doc_id, owner))
            if cur.rowcount:
                return doc_id
        cur = con.execute("INSERT INTO documents (owner, doc_type, language, title, text, details, effective_date, "
                          "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                          (owner, doc_type, language, title, text, blob, effective_date, _now(), _now()))
        return int(cur.lastrowid)


def list_documents(owner: str, limit: int = 100) -> list[SavedDoc]:
    with connect() as con:
        rows = con.execute("SELECT * FROM documents WHERE owner=? ORDER BY updated_at DESC, id DESC LIMIT ?",
                           (owner, limit)).fetchall()
    return [_row(r) for r in rows]


def get_document(owner: str, doc_id: int) -> SavedDoc | None:
    with connect() as con:
        r = con.execute("SELECT * FROM documents WHERE id=? AND owner=?", (doc_id, owner)).fetchone()
    return _row(r) if r else None


def delete_document(owner: str, doc_id: int) -> bool:
    with connect() as con:
        return con.execute("DELETE FROM documents WHERE id=? AND owner=?", (doc_id, owner)).rowcount > 0

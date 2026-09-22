"""Stockage SQLite de l'historique des runs."""
import json
import os
import sqlite3
import time
from contextlib import closing

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs.db")
MAX_RUNS_KEPT = 2000  # purge des plus anciens pour que la base ne grossisse pas sans fin

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api             TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    created_at      REAL    NOT NULL,
    status          TEXT    NOT NULL,
    passed          INTEGER NOT NULL,
    failed          INTEGER NOT NULL,
    errors          INTEGER NOT NULL,
    total           INTEGER NOT NULL,
    error_rate      REAL    NOT NULL,
    availability    REAL    NOT NULL,
    latency_ms_avg  REAL,
    latency_ms_p95  REAL,
    duration_ms     INTEGER,
    trigger         TEXT,
    payload         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
"""

SUMMARY_COLUMNS = ("id, api, timestamp, created_at, status, passed, failed, errors, total, "
                   "error_rate, availability, latency_ms_avg, latency_ms_p95, duration_ms, trigger")


def db_path():
    return os.environ.get("ATELIER_DB_PATH") or DEFAULT_DB_PATH


def _connect():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_connect()) as conn, conn:
        conn.executescript(SCHEMA)


def save_run(run, trigger="manual"):
    init_db()
    s = run["summary"]
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO runs (api, timestamp, created_at, status, passed, failed, errors, total, "
            "error_rate, availability, latency_ms_avg, latency_ms_p95, duration_ms, trigger, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run["api"], run["timestamp"], time.time(), s["status"], s["passed"], s["failed"],
             s["errors"], s["total"], s["error_rate"], s["availability"], s["latency_ms_avg"],
             s["latency_ms_p95"], run.get("duration_ms"), trigger,
             json.dumps(run, ensure_ascii=False)),
        )
        run_id = cur.lastrowid
        conn.execute("DELETE FROM runs WHERE id <= ?", (run_id - MAX_RUNS_KEPT,))
    return run_id


def list_runs(limit=50):
    """Résumés des derniers runs, du plus récent au plus ancien."""
    init_db()
    with closing(_connect()) as conn:
        rows = conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM runs ORDER BY id DESC LIMIT ?",
                            (limit,)).fetchall()
    return [dict(r) for r in rows]


def _full(row):
    if row is None:
        return None
    run = json.loads(row["payload"])
    run.update(id=row["id"], created_at=row["created_at"], trigger=row["trigger"])
    return run


def get_run(run_id):
    init_db()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _full(row)


def get_last_run():
    init_db()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return _full(row)


def export_runs(limit=500):
    """Runs complets (avec le détail des tests) pour l'export JSON."""
    init_db()
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_full(r) for r in rows]


def count_runs():
    init_db()
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

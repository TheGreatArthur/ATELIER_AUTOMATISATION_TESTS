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

-- Créneau anti-spam partagé entre tous les workers web (une seule ligne, id = 1).
CREATE TABLE IF NOT EXISTS run_slot (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    claimed_at  REAL    NOT NULL
);
INSERT OR IGNORE INTO run_slot (id, claimed_at)
    SELECT 1, COALESCE(MAX(created_at), 0) FROM runs;
"""

SUMMARY_COLUMNS = ("id, api, timestamp, created_at, status, passed, failed, errors, total, "
                   "error_rate, availability, latency_ms_avg, latency_ms_p95, duration_ms, trigger")

_initialized = set()  # bases déjà initialisées dans ce process (évite un CREATE à chaque requête)


def db_path():
    return os.environ.get("ATELIER_DB_PATH") or DEFAULT_DB_PATH


def _connect():
    path = db_path()
    fresh = path not in _initialized or not os.path.exists(path)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    if fresh:
        with conn:
            conn.executescript(SCHEMA)
        _initialized.add(path)
    return conn


def init_db():
    _connect().close()


# ------------------------------------------------------------------ anti-spam
def claim_run_slot(min_interval_s):
    """Réserve atomiquement le droit de lancer un run.

    Renvoie (True, 0) si le créneau est pris, sinon (False, secondes à attendre).
    Un seul UPDATE conditionnel : sûr même avec plusieurs workers/process.
    """
    now = time.time()
    with closing(_connect()) as conn, conn:
        cur = conn.execute("UPDATE run_slot SET claimed_at = ? WHERE id = 1 AND claimed_at <= ?",
                           (now, now - min_interval_s))
        if cur.rowcount == 1:
            return True, 0.0
        claimed = conn.execute("SELECT claimed_at FROM run_slot WHERE id = 1").fetchone()[0]
    return False, claimed + min_interval_s - now


def mark_run_slot():
    """Les runs planifiés passent toujours, mais repoussent le prochain run manuel."""
    with closing(_connect()) as conn, conn:
        conn.execute("UPDATE run_slot SET claimed_at = ? WHERE id = 1", (time.time(),))


def seconds_until_next_run(min_interval_s):
    with closing(_connect()) as conn:
        claimed = conn.execute("SELECT claimed_at FROM run_slot WHERE id = 1").fetchone()[0]
    return max(0.0, claimed + min_interval_s - time.time())


# ----------------------------------------------------------------------- runs
def save_run(run, trigger="manual"):
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


def list_runs(limit=50, since=None):
    """Résumés des derniers runs (du plus récent au plus ancien), optionnellement depuis `since` (epoch)."""
    with closing(_connect()) as conn:
        rows = conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM runs WHERE created_at >= ? "
                            "ORDER BY id DESC LIMIT ?", (since or 0, limit)).fetchall()
    return [dict(r) for r in rows]


def period_stats(since=None):
    """Agrégats QoS sur une période : nombre de runs, % de runs UP, moyennes."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS runs, "
            "       SUM(status = 'UP') AS up, "
            "       AVG(availability) AS availability, "
            "       AVG(error_rate) AS error_rate, "
            "       AVG(latency_ms_avg) AS latency_ms_avg, "
            "       AVG(latency_ms_p95) AS latency_ms_p95, "
            "       MAX(latency_ms_p95) AS latency_ms_p95_max "
            "FROM runs WHERE created_at >= ?", (since or 0,)).fetchone()
    stats = dict(row)
    stats["up_ratio"] = (stats["up"] or 0) / stats["runs"] if stats["runs"] else None
    return stats


def _full(row):
    if row is None:
        return None
    run = json.loads(row["payload"])
    run.update(id=row["id"], created_at=row["created_at"], trigger=row["trigger"])
    return run


def get_run(run_id):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _full(row)


def get_last_run():
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return _full(row)


def export_runs(limit=500, since=None):
    """Runs complets (avec le détail des tests) pour l'export JSON."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM runs WHERE created_at >= ? ORDER BY id DESC LIMIT ?",
                            (since or 0, limit)).fetchall()
    return [_full(r) for r in rows]


def count_runs():
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

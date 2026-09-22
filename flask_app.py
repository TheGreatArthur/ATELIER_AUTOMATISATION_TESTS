import json
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, abort, jsonify, render_template, request
from markupsafe import Markup, escape

import storage
from tester import runner
from tester.tests import API_NAME, TESTS

app = Flask(__name__)

MIN_SECONDS_BETWEEN_RUNS = int(os.environ.get("MIN_SECONDS_BETWEEN_RUNS", 300))  # anti-spam : 1 run / 5 min
STALE_AFTER_S = int(os.environ.get("STALE_AFTER_S", 26 * 3600))  # tâche quotidienne + marge
TRIGGERS = {"http", "dashboard", "cron", "github-actions", "scheduled-task"}
_run_lock = threading.Lock()


# ------------------------------------------------------------- helpers Jinja
STATUS_ICONS = {"UP": "✓", "PASS": "✓", "DEGRADED": "!", "ERROR": "!", "DOWN": "✕", "FAIL": "✕"}


@app.template_filter("dt")
def format_datetime(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return iso or "—"


@app.context_processor
def template_helpers():
    def status_badge(status):
        icon = STATUS_ICONS.get(status, "?")
        return Markup(f'<span class="badge s-{escape(status)}"><i aria-hidden="true">{icon}</i>'
                      f'{escape(status)}</span>')

    def pct(value, digits=1):
        return "—" if value is None else f"{value * 100:.{digits}f} %".replace(".", ",")

    def ms(value):
        return "—" if value is None else f"{round(value)} ms"

    def sec(value_ms):
        return "—" if value_ms is None else f"{value_ms / 1000:.1f} s".replace(".", ",")

    return {"status_badge": status_badge, "pct": pct, "ms": ms, "sec": sec}


def execute_run(trigger):
    """Lance un run en respectant l'anti-spam. Renvoie (payload, code HTTP)."""
    last = storage.get_last_run()
    if last:
        wait = MIN_SECONDS_BETWEEN_RUNS - (time.time() - last["created_at"])
        if wait > 0:
            return {"error": "rate_limited",
                    "message": f"Un run a déjà eu lieu il y a moins de {MIN_SECONDS_BETWEEN_RUNS} s.",
                    "retry_after_s": int(wait) + 1,
                    "last_run_id": last["id"]}, 429
    if not _run_lock.acquire(blocking=False):
        return {"error": "run_in_progress", "message": "Un run est déjà en cours."}, 409
    try:
        run = runner.run_all()
        run["id"] = storage.save_run(run, trigger=trigger)
        run["trigger"] = trigger
        return run, 201
    finally:
        _run_lock.release()


@app.get("/")
def consignes():
    return render_template("consignes.html")


@app.route("/run", methods=["GET", "POST"])
def run():
    trigger = request.args.get("trigger", "http")
    payload, code = execute_run(trigger=trigger if trigger in TRIGGERS else "http")
    resp = jsonify(payload)
    resp.status_code = code
    if code == 429:
        resp.headers["Retry-After"] = str(payload["retry_after_s"])
    return resp


@app.get("/dashboard")
def dashboard():
    runs = storage.list_runs(limit=50)
    run_id = request.args.get("run", type=int)
    selected = storage.get_run(run_id) if run_id else storage.get_last_run()
    if run_id and selected is None:
        abort(404)
    chart = [{"id": r["id"], "t": r["timestamp"], "avg": r["latency_ms_avg"],
              "p95": r["latency_ms_p95"], "err": r["error_rate"], "status": r["status"]}
             for r in reversed(runs)]
    return render_template("dashboard.html", api=API_NAME, run=selected, runs=runs,
                           chart=chart, is_latest=bool(runs) and selected is not None
                           and selected["id"] == runs[0]["id"],
                           tests_count=len(TESTS), min_interval=MIN_SECONDS_BETWEEN_RUNS)


@app.get("/api/runs")
def api_runs():
    limit = min(request.args.get("limit", 50, type=int), 500)
    runs = storage.list_runs(limit=limit)
    return jsonify({"api": API_NAME, "count": len(runs), "runs": runs})


@app.get("/api/runs/latest")
def api_last_run():
    run = storage.get_last_run()
    if run is None:
        return jsonify({"error": "no_run", "message": "Aucun run enregistré."}), 404
    return jsonify(run)


@app.get("/api/runs/<int:run_id>")
def api_run(run_id):
    run = storage.get_run(run_id)
    if run is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(run)


@app.get("/export.json")
def export_json():
    limit = min(request.args.get("limit", 500, type=int), 2000)
    body = json.dumps({"api": API_NAME,
                       "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "runs": storage.export_runs(limit=limit)},
                      ensure_ascii=False, indent=2)
    filename = f"runs_{API_NAME.lower()}_{datetime.now():%Y%m%d_%H%M}.json"
    return Response(body, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/health")
def health():
    """État de santé de la solution de monitoring (et non de l'API testée)."""
    now = time.time()
    checks = {}
    try:
        last = storage.get_last_run()
        checks["database"] = {"ok": True, "runs": storage.count_runs()}
    except Exception as e:
        checks["database"] = {"ok": False, "error": str(e)}
        return jsonify({"status": "down", "checks": checks}), 503

    if last is None:
        checks["last_run"] = {"ok": False, "message": "aucun run enregistré"}
    else:
        age = round(now - last["created_at"])
        checks["last_run"] = {
            "ok": age <= STALE_AFTER_S,
            "id": last["id"],
            "timestamp": last["timestamp"],
            "age_s": age,
            "stale": age > STALE_AFTER_S,
            "api_status": last["summary"]["status"],
            "error_rate": last["summary"]["error_rate"],
            "latency_ms_p95": last["summary"]["latency_ms_p95"],
        }
    status = "ok" if all(c["ok"] for c in checks.values()) else "degraded"
    return jsonify({"status": status, "api": API_NAME, "tests": len(TESTS),
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "checks": checks})


if __name__ == "__main__":
    # utile en local uniquement
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

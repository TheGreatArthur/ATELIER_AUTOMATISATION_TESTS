"""Tests des routes Flask avec une base SQLite temporaire et un runner factice."""
import os
import tempfile
import unittest
from unittest import mock

os.environ["ATELIER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_runs.db")

import flask_app  # noqa: E402
import storage  # noqa: E402
from tester.metrics import summarize  # noqa: E402


def fake_run():
    tests = [{"id": "T01", "name": "t", "category": "Contrat", "status": "PASS", "details": "ok",
              "http_status": 200, "latency_ms": 120, "requests": 1}]
    calls = [{"url": "u", "status": 200, "latency_ms": 120.0, "attempt": 1, "error": None}]
    return {"api": "Open-Meteo", "timestamp": "2026-09-22T10:00:00+02:00", "duration_ms": 300,
            "summary": summarize(tests, calls), "tests": tests, "calls": calls}


class AppTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(storage.db_path()):
            os.remove(storage.db_path())
        self.client = flask_app.app.test_client()

    def test_empty_state(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/api/runs/latest").status_code, 404)
        health = self.client.get("/health").get_json()
        self.assertEqual(health["status"], "degraded")
        self.assertTrue(health["checks"]["database"]["ok"])

    @mock.patch("tester.runner.run_all", side_effect=fake_run)
    def test_run_then_antispam(self, _):
        first = self.client.post("/run?trigger=dashboard")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.get_json()["trigger"], "dashboard")

        second = self.client.get("/run")
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)

        self.assertEqual(storage.count_runs(), 1)

    @mock.patch("tester.runner.run_all", side_effect=fake_run)
    def test_unknown_trigger_is_normalised(self, _):
        self.assertEqual(self.client.post("/run?trigger=<script>").get_json()["trigger"], "http")

    def test_pages_and_exports_with_history(self):
        ids = [storage.save_run(fake_run(), trigger="cron") for _ in range(3)]

        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Open-Meteo", page.data)
        self.assertEqual(self.client.get(f"/dashboard?run={ids[0]}").status_code, 200)
        self.assertEqual(self.client.get("/dashboard?run=99999").status_code, 404)

        self.assertEqual(self.client.get("/api/runs").get_json()["count"], 3)
        self.assertEqual(self.client.get("/api/runs/latest").get_json()["id"], ids[-1])
        self.assertEqual(self.client.get(f"/api/runs/{ids[1]}").get_json()["id"], ids[1])

        export = self.client.get("/export.json")
        self.assertIn("attachment", export.headers["Content-Disposition"])
        self.assertEqual(len(export.get_json()["runs"]), 3)

        health = self.client.get("/health").get_json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["checks"]["last_run"]["api_status"], "UP")
        self.assertEqual(health["version"], flask_app.VERSION)

    def test_period_filter(self):
        old = storage.save_run(fake_run(), trigger="cron")
        recent = storage.save_run(fake_run(), trigger="cron")
        with storage._connect() as conn:  # vieillit artificiellement le premier run de 10 jours
            conn.execute("UPDATE runs SET created_at = created_at - 10 * 86400 WHERE id = ?", (old,))

        week = self.client.get("/api/runs?period=7d").get_json()
        self.assertEqual([r["id"] for r in week["runs"]], [recent])
        self.assertEqual(week["stats"]["runs"], 1)
        self.assertEqual(self.client.get("/api/runs?period=all").get_json()["count"], 2)
        self.assertEqual(self.client.get("/api/runs?period=nimporte").get_json()["period"], "7d")
        self.assertEqual(len(self.client.get("/export.json?period=24h").get_json()["runs"]), 1)
        page = self.client.get("/dashboard?period=30d")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'aria-current="true">30 jours', page.data)

    def test_security_and_cache_headers(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("Disallow: /run", self.client.get("/robots.txt").get_data(as_text=True))


class RunSlotTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(storage.db_path()):
            os.remove(storage.db_path())

    def test_slot_is_exclusive_until_interval_elapsed(self):
        self.assertEqual(storage.claim_run_slot(300), (True, 0.0))
        allowed, wait = storage.claim_run_slot(300)
        self.assertFalse(allowed)
        self.assertGreater(wait, 290)
        self.assertTrue(storage.claim_run_slot(0)[0])  # intervalle nul : toujours libre

    def test_scheduled_run_pushes_back_manual_runs(self):
        storage.init_db()
        self.assertEqual(storage.seconds_until_next_run(300), 0)
        storage.mark_run_slot()
        self.assertGreater(storage.seconds_until_next_run(300), 290)
        self.assertFalse(storage.claim_run_slot(300)[0])

    def test_slot_initialised_from_existing_history(self):
        # base d'une version précédente : des runs, mais pas encore de table run_slot
        storage.save_run(fake_run())
        with storage._connect() as conn:
            conn.execute("DROP TABLE run_slot")
        storage._initialized.clear()
        self.assertGreater(storage.seconds_until_next_run(300), 290)  # créneau = dernier run


if __name__ == "__main__":
    unittest.main()

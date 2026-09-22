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


if __name__ == "__main__":
    unittest.main()

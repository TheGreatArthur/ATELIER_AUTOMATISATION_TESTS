"""Tests unitaires du client HTTP contre un faux serveur local (aucun accès Internet).

Vérifie la robustesse : timeout, 1 retry max, backoff sur 429 (Retry-After) et 5xx,
pas de retry sur les 4xx attendus, quota de requêtes par run.
"""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tester.client import ApiClient, BudgetExceeded


class FakeApi(BaseHTTPRequestHandler):
    hits = {}

    def log_message(self, *args):
        pass

    def _send(self, code, payload, headers=None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        n = FakeApi.hits[path] = FakeApi.hits.get(path, 0) + 1
        if path == "/ok":
            self._send(200, {"ok": True})
        elif path == "/flaky":            # 503 puis 200
            self._send(503, {"error": True}) if n == 1 else self._send(200, {"ok": True})
        elif path == "/down":             # toujours 500
            self._send(500, {"error": True})
        elif path == "/limited":          # 429 avec Retry-After puis 200
            self._send(429, {"error": True}, {"Retry-After": "2"}) if n == 1 else self._send(200, {"ok": True})
        elif path == "/limited-long":     # Retry-After énorme : doit être plafonné
            self._send(429, {"error": True}, {"Retry-After": "3600"})
        elif path == "/slow":
            time.sleep(0.6)
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": True, "reason": "Not Found"})


class ClientRobustnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeApi.hits.clear()
        self.sleeps = []
        self.client = ApiClient(timeout_s=0.3, sleep=self.sleeps.append)

    def test_success_no_retry_and_latency_measured(self):
        resp = self.client.get(self.base + "/ok", {"q": "x"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.attempts, 1)
        self.assertEqual(resp.json(), {"ok": True})
        self.assertIn("application/json", resp.content_type)
        self.assertGreater(resp.latency_ms, 0)
        self.assertEqual(self.sleeps, [])

    def test_retry_once_on_5xx_then_success(self):
        resp = self.client.get(self.base + "/flaky")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.attempts, 2)
        self.assertEqual(len(self.sleeps), 1)

    def test_at_most_one_retry(self):
        resp = self.client.get(self.base + "/down")
        self.assertEqual(resp.status, 500)
        self.assertEqual(resp.attempts, 2)
        self.assertEqual(FakeApi.hits["/down"], 2)

    def test_429_honours_retry_after(self):
        resp = self.client.get(self.base + "/limited")
        self.assertEqual(resp.status, 200)
        self.assertEqual(self.sleeps, [2.0])

    def test_429_backoff_is_capped(self):
        resp = self.client.get(self.base + "/limited-long")
        self.assertEqual(resp.status, 429)
        self.assertEqual(self.sleeps, [5.0])

    def test_expected_4xx_is_not_retried(self):
        resp = self.client.get(self.base + "/unknown")
        self.assertEqual(resp.status, 404)
        self.assertEqual(resp.attempts, 1)
        self.assertEqual(resp.json()["reason"], "Not Found")

    def test_timeout_is_reported_and_retried_once(self):
        resp = self.client.get(self.base + "/slow")
        self.assertIsNone(resp.status)
        self.assertEqual(resp.error, "timeout")
        self.assertEqual(resp.attempts, 2)
        self.assertLess(resp.latency_ms, 600)

    def test_network_error_is_reported(self):
        resp = self.client.get("http://127.0.0.1:9/")  # port "discard", rien n'écoute
        self.assertIsNone(resp.status)
        self.assertTrue(resp.error.startswith("network"))

    def test_request_budget(self):
        client = ApiClient(max_requests=3, sleep=lambda s: None)
        for _ in range(3):
            client.get(self.base + "/ok")
        with self.assertRaises(BudgetExceeded):
            client.get(self.base + "/ok")


if __name__ == "__main__":
    unittest.main()

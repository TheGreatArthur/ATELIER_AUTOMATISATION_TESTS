"""Tests unitaires des métriques QoS et du runner (sans réseau)."""
import unittest

from tester.client import ApiResponse, BudgetExceeded
from tester.metrics import percentile, summarize
from tester.runner import run_all


def call(status=200, latency=100.0, attempt=1, error=None):
    return {"url": "x", "status": status, "latency_ms": latency, "attempt": attempt, "error": error}


class PercentileTest(unittest.TestCase):
    def test_nearest_rank(self):
        values = list(range(1, 21))            # 1..20
        self.assertEqual(percentile(values, 95), 19)
        self.assertEqual(percentile(values, 50), 10)
        self.assertEqual(percentile([42], 95), 42)
        self.assertIsNone(percentile([], 95))


class SummaryTest(unittest.TestCase):
    def test_all_pass_is_up(self):
        s = summarize([{"status": "PASS"}] * 6, [call(latency=v) for v in (100, 200, 300)])
        self.assertEqual(s["status"], "UP")
        self.assertEqual(s["error_rate"], 0.0)
        self.assertEqual(s["availability"], 1.0)
        self.assertEqual(s["latency_ms_avg"], 200)
        self.assertEqual(s["latency_ms_p95"], 300)

    def test_expected_4xx_count_as_available(self):
        s = summarize([{"status": "PASS"}], [call(400), call(404)])
        self.assertEqual(s["availability"], 1.0)

    def test_failures_and_outages_degrade(self):
        results = [{"status": "PASS"}] * 4 + [{"status": "FAIL"}, {"status": "ERROR"}]
        calls = [call(), call(503, attempt=1), call(200, attempt=2), call(None, error="timeout"),
                 call(429)]
        s = summarize(results, calls)
        self.assertEqual(s["status"], "DEGRADED")
        self.assertAlmostEqual(s["error_rate"], 0.333)
        self.assertEqual(s["availability"], 0.6)  # 503 + timeout sur 5 requêtes
        self.assertEqual((s["http_5xx"], s["timeouts"], s["http_429"], s["retries"]), (1, 1, 1, 1))
        self.assertTrue(any("429" in note for note in s["interpretation"]))

    def test_nothing_passes_is_down(self):
        s = summarize([{"status": "FAIL"}] * 3, [call(None, error="timeout")] * 3)
        self.assertEqual(s["status"], "DOWN")
        self.assertIsNone(s["latency_ms_p95"])


class FakeClient:
    """Client factice : renvoie toujours la même réponse et trace les appels."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(call(latency=50.0))
        return ApiResponse(url, 200, {"content-type": "application/json"}, b"{}", 50.0, 1)


class RunnerTest(unittest.TestCase):
    def test_run_structure_and_statuses(self):
        def ok(ctx):
            ctx.client.get("u")
            return "fine"

        def ko(ctx):
            raise AssertionError("champ manquant")

        def bug(ctx):
            raise KeyError("oops")

        def budget(ctx):
            raise BudgetExceeded("quota")

        tests = [{"id": f"T0{i}", "name": f.__name__, "category": "c", "func": f}
                 for i, f in enumerate((ok, ko, bug, budget), 1)]
        run = run_all(client=FakeClient(), tests=tests)

        self.assertEqual({"api", "timestamp", "duration_ms", "summary", "tests", "calls"}, set(run))
        self.assertEqual([t["status"] for t in run["tests"]], ["PASS", "FAIL", "ERROR", "ERROR"])
        self.assertEqual(run["tests"][0]["latency_ms"], 50)
        self.assertEqual(run["tests"][0]["http_status"], 200)
        self.assertEqual(run["tests"][1]["details"], "champ manquant")
        self.assertEqual(run["summary"]["passed"], 1)
        self.assertEqual(run["summary"]["status"], "DEGRADED")

    def test_real_suite_has_at_least_six_tests(self):
        from tester.tests import TESTS
        self.assertGreaterEqual(len(TESTS), 6)
        self.assertEqual(len({t["id"] for t in TESTS}), len(TESTS))


if __name__ == "__main__":
    unittest.main()

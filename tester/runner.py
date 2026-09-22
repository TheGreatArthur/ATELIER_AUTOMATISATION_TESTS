"""Exécute la suite de tests et produit un run (dict sérialisable en JSON)."""
import time
from datetime import datetime, timezone
from statistics import mean

from .client import ApiClient, BudgetExceeded
from .metrics import summarize
from .tests import API_NAME, TESTS, TestContext

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Paris")
except Exception:  # tzdata absent : on reste en UTC
    LOCAL_TZ = timezone.utc


def now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def run_test(test, ctx):
    client = ctx.client
    first_call = len(client.calls)
    ctx.reused = None
    try:
        details = test["func"](ctx) or "OK"
        status = "PASS"
    except AssertionError as e:
        status, details = "FAIL", str(e) or "assertion échouée"
    except BudgetExceeded as e:
        status, details = "ERROR", f"test non exécuté : {e}"
    except Exception as e:  # un bug de test ne doit jamais casser tout le run
        status, details = "ERROR", f"{type(e).__name__}: {e}"

    calls = client.calls[first_call:]
    answered = [c["latency_ms"] for c in calls if c["status"] is not None]
    if calls:
        http_status = calls[-1]["status"]
    else:
        http_status = ctx.reused.status if ctx.reused else None
    return {
        "id": test["id"],
        "name": test["name"],
        "category": test["category"],
        "status": status,
        "details": details,
        "http_status": http_status,
        "latency_ms": round(mean(answered)) if answered else None,
        "requests": len(calls),  # 0 = réponse partagée (cache) avec un test précédent
    }


def run_all(client=None, tests=None):
    client = client or ApiClient()
    tests = TESTS if tests is None else tests
    ctx = TestContext(client)

    timestamp = now_iso()
    started = time.perf_counter()
    results = [run_test(t, ctx) for t in tests]

    return {
        "api": API_NAME,
        "timestamp": timestamp,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "summary": summarize(results, client.calls),
        "tests": results,
        "calls": client.calls,
    }

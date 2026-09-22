"""Calcul des indicateurs QoS d'un run et de leur interprétation."""
import math
from statistics import mean

LATENCY_GOOD_MS = 500      # p95 en dessous : excellente
LATENCY_OK_MS = 1500       # p95 en dessous : acceptable, au-delà : dégradée


def percentile(values, pct):
    """Percentile par la méthode du rang le plus proche (nearest-rank)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(results, calls):
    """Construit le bloc "summary" d'un run.

    results : résultats des tests  [{"status": "PASS"|"FAIL"|"ERROR", ...}]
    calls   : tentatives HTTP       [{"status": int|None, "latency_ms": float, "attempt": int, "error": str|None}]
    """
    total = len(results)
    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)
    errors = sum(r["status"] == "ERROR" for r in results)

    answered = [c for c in calls if c["status"] is not None]
    latencies = [c["latency_ms"] for c in answered]
    http_5xx = sum(c["status"] >= 500 for c in answered)
    http_429 = sum(c["status"] == 429 for c in answered)
    timeouts = sum(c["error"] == "timeout" for c in calls)
    network_errors = sum(bool(c["error"]) and c["error"] != "timeout" for c in calls)
    unavailable = http_5xx + timeouts + network_errors

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "error_rate": round((failed + errors) / total, 3) if total else 0.0,
        "requests": len(calls),
        "retries": sum(c["attempt"] > 1 for c in calls),
        "http_429": http_429,
        "http_5xx": http_5xx,
        "timeouts": timeouts,
        "network_errors": network_errors,
        # disponibilité = part des requêtes ayant obtenu une réponse exploitable
        # (les 4xx attendus des tests d'erreur comptent comme "disponible")
        "availability": round(1 - unavailable / len(calls), 3) if calls else 0.0,
        "latency_ms_avg": round(mean(latencies)) if latencies else None,
        "latency_ms_p95": round(percentile(latencies, 95)) if latencies else None,
        "latency_ms_min": round(min(latencies)) if latencies else None,
        "latency_ms_max": round(max(latencies)) if latencies else None,
    }
    summary["status"] = service_status(summary)
    summary["interpretation"] = interpret(summary)
    return summary


def service_status(s):
    if s["total"] == 0 or s["passed"] == 0 or s["availability"] < 0.5:
        return "DOWN"
    if s["failed"] or s["errors"] or s["availability"] < 1:
        return "DEGRADED"
    return "UP"


def interpret(s):
    """Phrases lisibles qui expliquent les chiffres du run."""
    notes = []
    status_txt = {
        "UP": "Service opérationnel : tous les tests passent.",
        "DEGRADED": "Service dégradé : au moins un test est en échec.",
        "DOWN": "Service indisponible ou contrat cassé : la majorité des vérifications échouent.",
    }
    notes.append(status_txt[s["status"]])

    notes.append(f"Disponibilité {s['availability'] * 100:.0f} % sur {s['requests']} requêtes"
                 + (f" ({s['http_5xx']} 5xx, {s['timeouts']} timeout(s), "
                    f"{s['network_errors']} erreur(s) réseau)." if s["availability"] < 1 else "."))

    p95 = s["latency_ms_p95"]
    if p95 is not None:
        if p95 < LATENCY_GOOD_MS:
            level = "excellente"
        elif p95 < LATENCY_OK_MS:
            level = "acceptable"
        else:
            level = "dégradée (risque de timeout côté client)"
        notes.append(f"Latence {level} : moyenne {s['latency_ms_avg']} ms, p95 {p95} ms, "
                     f"max {s['latency_ms_max']} ms.")

    if s["failed"] or s["errors"]:
        notes.append(f"Taux d'erreur {s['error_rate'] * 100:.1f} % "
                     f"({s['failed']} échec(s) de contrat, {s['errors']} erreur(s) technique(s)).")
    if s["http_429"]:
        notes.append(f"{s['http_429']} réponse(s) 429 : l'API limite le débit, espacer les runs.")
    if s["retries"]:
        notes.append(f"{s['retries']} retry effectué(s) : instabilité ponctuelle absorbée.")
    return notes

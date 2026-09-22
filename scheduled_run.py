"""Point d'entrée de la tâche planifiée PythonAnywhere (onglet "Tasks").

Commande à planifier (adapter le chemin à PA_TARGET_DIR) :
    python3.13 /home/<user>/mysite/scheduled_run.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import storage  # noqa: E402
from tester.runner import run_all  # noqa: E402


def main():
    run = run_all()
    run_id = storage.save_run(run, trigger="scheduled-task")
    s = run["summary"]
    print(f"[{run['timestamp']}] run #{run_id} {s['status']} — {s['passed']}/{s['total']} PASS, "
          f"erreur {s['error_rate'] * 100:.1f} %, dispo {s['availability'] * 100:.0f} %, "
          f"avg {s['latency_ms_avg']} ms, p95 {s['latency_ms_p95']} ms")
    for t in run["tests"]:
        if t["status"] != "PASS":
            print(f"  {t['id']} {t['status']} {t['name']} : {t['details']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

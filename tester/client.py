"""Wrapper HTTP : timeout strict, 1 retry max, gestion 429/5xx, mesure de latence.

Uniquement la bibliothèque standard (urllib) : rien à installer sur PythonAnywhere,
et le proxy des comptes gratuits (variables https_proxy) est pris en compte
automatiquement par urllib.
"""
from __future__ import annotations  # syntaxe "int | None" aussi sous Python 3.9

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_TIMEOUT_S = 3.0
MAX_RETRIES = 1                       # consigne : 1 retry maximum
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF_S = 5.0                   # on n'attend jamais plus de 5 s
DEFAULT_429_WAIT_S = 2.0              # attente si 429 sans en-tête Retry-After
BASE_BACKOFF_S = 0.5                  # attente avant retry sur 5xx / timeout
MAX_REQUESTS_PER_RUN = 20             # consigne : 20 requêtes max par run
RUN_DEADLINE_S = 25.0                 # durée max d'un run (1 seul worker web sur un compte gratuit)
USER_AGENT = "atelier-api-monitoring/1.0 (tests non destructifs)"


class BudgetExceeded(Exception):
    """Levée quand le run dépasse son quota de requêtes ou sa durée maximale."""


@dataclass
class ApiResponse:
    url: str
    status: int | None          # None = aucune réponse (timeout / erreur réseau)
    headers: dict
    body: bytes
    latency_ms: float           # latence de la dernière tentative
    attempts: int               # 1 = pas de retry, 2 = un retry
    error: str | None = None    # "timeout" / "network: ..." si pas de réponse

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    def json(self):
        return json.loads(self.body.decode("utf-8"))


@dataclass
class ApiClient:
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_retries: int = MAX_RETRIES
    max_requests: int = MAX_REQUESTS_PER_RUN
    deadline_s: float = RUN_DEADLINE_S
    sleep: callable = time.sleep            # injectable pour les tests unitaires
    calls: list = field(default_factory=list)  # une entrée par tentative HTTP

    def __post_init__(self):
        self._started = time.monotonic()

    # ------------------------------------------------------------------ public
    def get(self, url: str, params: dict | None = None) -> ApiResponse:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        attempt = 0
        while True:
            attempt += 1
            self._check_budget()
            status, headers, body, latency_ms, error = self._send(url)
            self.calls.append({
                "url": url,
                "status": status,
                "latency_ms": round(latency_ms, 1),
                "attempt": attempt,
                "error": error,
            })

            retryable = error is not None or status in RETRY_STATUSES
            if not retryable or attempt > self.max_retries:
                return ApiResponse(url, status, headers, body, latency_ms, attempt, error)

            self.sleep(self._backoff(status, headers))

    # ----------------------------------------------------------------- interne
    def _check_budget(self):
        if len(self.calls) >= self.max_requests:
            raise BudgetExceeded(f"quota de {self.max_requests} requêtes/run atteint")
        if time.monotonic() - self._started > self.deadline_s:
            raise BudgetExceeded(f"durée max du run ({self.deadline_s:.0f} s) dépassée")

    def _send(self, url: str):
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read()
                return resp.status, _lower(resp.headers), body, _ms(start), None
        except urllib.error.HTTPError as e:     # 4xx / 5xx : c'est une vraie réponse
            body = e.read() or b""
            return e.code, _lower(e.headers), body, _ms(start), None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)):
                return None, {}, b"", _ms(start), "timeout"
            return None, {}, b"", _ms(start), f"network: {e.reason}"
        except (TimeoutError, socket.timeout):
            return None, {}, b"", _ms(start), "timeout"
        except OSError as e:
            return None, {}, b"", _ms(start), f"network: {e}"

    @staticmethod
    def _backoff(status, headers) -> float:
        if status == 429:
            retry_after = headers.get("retry-after", "")
            try:
                wait = float(retry_after)
            except ValueError:
                wait = DEFAULT_429_WAIT_S
            return max(0.0, min(wait, MAX_BACKOFF_S))
        return BASE_BACKOFF_S


def _lower(headers) -> dict:
    return {k.lower(): v for k, v in (headers.items() if headers else [])}


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0

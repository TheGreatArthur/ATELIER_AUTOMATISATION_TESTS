"""Tests "as code" de l'API Open-Meteo (non destructifs, lecture seule).

Chaque test est une fonction qui reçoit un TestContext, lève AssertionError en cas
d'échec et renvoie une courte chaîne de détails en cas de succès.
Budget : 12 requêtes par run (hors retries), sous la limite de 20.
"""
from datetime import date, datetime
from statistics import mean

from .client import ApiClient, ApiResponse
from .metrics import percentile

API_NAME = "Open-Meteo"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
UNKNOWN_ENDPOINT_URL = "https://api.open-meteo.com/v1/endpoint-inexistant"

PARIS_LAT, PARIS_LON = 48.8566, 2.3522
TIMEZONE = "Europe/Paris"
CURRENT_VARS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m"]

QOS_CALLS = 5
LATENCY_P95_THRESHOLD_MS = 1000


class TestContext:
    """Donne accès au client HTTP et met en cache les réponses partagées entre tests."""

    def __init__(self, client: ApiClient):
        self.client = client
        self._cache = {}
        self.reused = None  # dernière réponse servie depuis le cache (pour le rapport)

    def cached(self, key, fetch):
        if key in self._cache:
            self.reused = self._cache[key]
        else:
            self._cache[key] = fetch()
        return self._cache[key]

    def forecast_current(self) -> ApiResponse:
        return self.cached("forecast_current", lambda: self.client.get(FORECAST_URL, {
            "latitude": PARIS_LAT,
            "longitude": PARIS_LON,
            "current": ",".join(CURRENT_VARS),
            "timezone": TIMEZONE,
        }))


# --------------------------------------------------------------------- helpers
def check(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_status(resp: ApiResponse, expected: int):
    if resp.status is None:
        raise AssertionError(f"pas de réponse ({resp.error}) après {resp.attempts} tentative(s)")
    check(resp.status == expected, f"HTTP {resp.status} reçu, {expected} attendu")


def expect_json(resp: ApiResponse):
    check("application/json" in resp.content_type,
          f"Content-Type '{resp.content_type}' au lieu de application/json")
    try:
        data = resp.json()
    except ValueError as e:
        raise AssertionError(f"JSON invalide : {e}") from None
    check(isinstance(data, dict), f"objet JSON attendu, {type(data).__name__} reçu")
    return data


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def expect_keys(obj: dict, keys, where):
    missing = [k for k in keys if k not in obj]
    check(not missing, f"champ(s) manquant(s) dans {where} : {', '.join(missing)}")


def expect_error_payload(data: dict):
    """Contrat d'erreur Open-Meteo : {"error": true, "reason": "<texte>"}."""
    check(data.get("error") is True, f"'error' devrait valoir true, reçu {data.get('error')!r}")
    reason = data.get("reason")
    check(isinstance(reason, str) and reason, "'reason' devrait être une chaîne non vide")
    return reason


# ----------------------------------------------------------------------- tests
TESTS = []


def api_test(name, category):
    def register(func):
        TESTS.append({"id": f"T{len(TESTS) + 1:02d}", "name": name,
                      "category": category, "func": func})
        return func
    return register


@api_test("GET /forecast (current) → HTTP 200 + JSON", "Contrat")
def test_forecast_status_and_content_type(ctx: TestContext):
    resp = ctx.forecast_current()
    expect_status(resp, 200)
    expect_json(resp)
    return f"HTTP 200, {resp.content_type}"


@api_test("Contrat /forecast : champs obligatoires", "Contrat")
def test_forecast_required_fields(ctx: TestContext):
    resp = ctx.forecast_current()
    expect_status(resp, 200)
    data = expect_json(resp)
    expect_keys(data, ["latitude", "longitude", "timezone", "utc_offset_seconds",
                       "elevation", "current_units", "current"], "la racine")
    expect_keys(data["current"], ["time", "interval", *CURRENT_VARS], "'current'")
    expect_keys(data["current_units"], CURRENT_VARS, "'current_units'")
    return f"{len(data)} champs racine, {len(data['current'])} champs 'current'"


@api_test("Contrat /forecast : types et plages de valeurs", "Contrat")
def test_forecast_types_and_ranges(ctx: TestContext):
    resp = ctx.forecast_current()
    expect_status(resp, 200)
    data = expect_json(resp)
    cur = data.get("current", {})

    check(isinstance(data.get("latitude"), float), "latitude doit être un float")
    check(isinstance(data.get("longitude"), float), "longitude doit être un float")
    check(abs(data["latitude"] - PARIS_LAT) < 0.5 and abs(data["longitude"] - PARIS_LON) < 0.5,
          f"point renvoyé ({data['latitude']}, {data['longitude']}) trop loin de Paris")
    check(data.get("timezone") == TIMEZONE, f"timezone {data.get('timezone')!r} ≠ {TIMEZONE}")
    check(isinstance(data.get("utc_offset_seconds"), int), "utc_offset_seconds doit être un int")

    check(isinstance(cur.get("time"), str), "current.time doit être une chaîne")
    try:
        datetime.fromisoformat(cur["time"])
    except ValueError:
        raise AssertionError(f"current.time n'est pas au format ISO 8601 : {cur['time']!r}") from None

    temp = cur.get("temperature_2m")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    check(is_number(temp) and -60 <= temp <= 60, f"temperature_2m hors plage : {temp!r}")
    check(isinstance(hum, int) and 0 <= hum <= 100, f"relative_humidity_2m hors plage : {hum!r}")
    check(is_number(wind) and wind >= 0, f"wind_speed_10m invalide : {wind!r}")
    check(data["current_units"].get("temperature_2m") == "°C", "unité de température ≠ °C")
    return f"{temp} °C, {hum} %, {wind} km/h"


@api_test("GET /forecast (daily, 3 jours) → séries cohérentes", "Contrat")
def test_forecast_daily_consistency(ctx: TestContext):
    days = 3
    resp = ctx.client.get(FORECAST_URL, {
        "latitude": PARIS_LAT, "longitude": PARIS_LON, "timezone": TIMEZONE,
        "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": days,
    })
    expect_status(resp, 200)
    data = expect_json(resp)
    expect_keys(data, ["daily", "daily_units"], "la racine")
    daily = data["daily"]
    expect_keys(daily, ["time", "temperature_2m_max", "temperature_2m_min"], "'daily'")

    for key in ("time", "temperature_2m_max", "temperature_2m_min"):
        check(isinstance(daily[key], list) and len(daily[key]) == days,
              f"daily.{key} doit être une liste de {days} éléments")
    dates = [date.fromisoformat(d) for d in daily["time"]]
    check(all((b - a).days == 1 for a, b in zip(dates, dates[1:])),
          f"dates non consécutives : {daily['time']}")
    for d, tmax, tmin in zip(daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"]):
        check(is_number(tmax) and is_number(tmin), f"{d} : températures non numériques")
        check(tmax >= tmin, f"{d} : max ({tmax}) < min ({tmin})")
    return f"{daily['time'][0]} → {daily['time'][-1]}"


@api_test("GET /search?name=Paris (géocodage) → résultat attendu", "Contrat")
def test_geocoding_paris(ctx: TestContext):
    resp = ctx.client.get(GEOCODING_URL, {"name": "Paris", "count": 1,
                                          "language": "fr", "format": "json"})
    expect_status(resp, 200)
    data = expect_json(resp)
    results = data.get("results")
    check(isinstance(results, list) and results, "'results' doit être une liste non vide")
    first = results[0]
    expect_keys(first, ["id", "name", "latitude", "longitude", "country_code", "timezone"],
                "results[0]")
    check(isinstance(first["id"], int), "results[0].id doit être un int")
    check(first["name"] == "Paris", f"nom {first['name']!r} ≠ 'Paris'")
    check(first["country_code"] == "FR", f"country_code {first['country_code']!r} ≠ 'FR'")
    check(abs(first["latitude"] - PARIS_LAT) < 0.2 and abs(first["longitude"] - PARIS_LON) < 0.2,
          "coordonnées de Paris incohérentes")
    return f"{first['name']} ({first['country_code']}) {first['latitude']}, {first['longitude']}"


@api_test("GET /search nom inconnu → 200 sans résultat", "Erreurs attendues")
def test_geocoding_unknown_city(ctx: TestContext):
    resp = ctx.client.get(GEOCODING_URL, {"name": "zzqxw-ville-inexistante", "count": 1})
    expect_status(resp, 200)
    data = expect_json(resp)
    check(not data.get("results"), f"aucun résultat attendu, reçu {len(data.get('results', []))}")
    check(is_number(data.get("generationtime_ms")), "generationtime_ms doit être numérique")
    return "aucun résultat, comme documenté"


@api_test("Entrée invalide : latitude=999 → HTTP 400", "Erreurs attendues")
def test_invalid_latitude(ctx: TestContext):
    resp = ctx.client.get(FORECAST_URL, {"latitude": 999, "longitude": PARIS_LON,
                                         "current": "temperature_2m"})
    expect_status(resp, 400)
    reason = expect_error_payload(expect_json(resp))
    check("latitude" in reason.lower(), f"le message devrait mentionner la latitude : {reason!r}")
    return reason[:80]


@api_test("Entrée invalide : variable inconnue → HTTP 400", "Erreurs attendues")
def test_invalid_variable(ctx: TestContext):
    resp = ctx.client.get(FORECAST_URL, {"latitude": PARIS_LAT, "longitude": PARIS_LON,
                                         "current": "variable_inexistante"})
    expect_status(resp, 400)
    reason = expect_error_payload(expect_json(resp))
    return reason[:80]


@api_test("Endpoint inexistant → HTTP 404", "Erreurs attendues")
def test_unknown_endpoint(ctx: TestContext):
    resp = ctx.client.get(UNKNOWN_ENDPOINT_URL)
    expect_status(resp, 404)
    reason = expect_error_payload(expect_json(resp))
    return f"404 · {reason}"


@api_test(f"QoS : {QOS_CALLS} appels /forecast, p95 < {LATENCY_P95_THRESHOLD_MS} ms", "QoS")
def test_latency_p95(ctx: TestContext):
    latencies = []
    for _ in range(QOS_CALLS):
        resp = ctx.client.get(FORECAST_URL, {"latitude": PARIS_LAT, "longitude": PARIS_LON,
                                             "current": "temperature_2m"})
        expect_status(resp, 200)
        latencies.append(resp.latency_ms)
    p95 = percentile(latencies, 95)
    avg = mean(latencies)
    check(p95 < LATENCY_P95_THRESHOLD_MS,
          f"p95 = {p95:.0f} ms ≥ seuil {LATENCY_P95_THRESHOLD_MS} ms (avg {avg:.0f} ms)")
    return f"avg {avg:.0f} ms · p95 {p95:.0f} ms"

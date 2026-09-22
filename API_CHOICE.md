# API Choice

- Étudiant : Arthur Litschig (GitHub : TheGreatArthur)
- API choisie : **Open-Meteo** (prévisions météo + géocodage)
- URL base :
  - Prévisions : `https://api.open-meteo.com/v1`
  - Géocodage : `https://geocoding-api.open-meteo.com/v1`
- Documentation officielle / README :
  - https://open-meteo.com/en/docs
  - https://open-meteo.com/en/docs/geocoding-api
  - Fiche public-apis (catégorie Weather) : https://github.com/public-apis/public-apis#weather
- Auth : **None** (pas de clé)
- Licence / conditions : usage **non commercial** gratuit (un projet éducatif en fait partie), données sous **CC BY 4.0** → attribution « Open-Meteo.com » affichée en pied de dashboard ([conditions](https://open-meteo.com/en/terms)).
- Pourquoi ce choix : sans clé, contrat JSON stable et documenté, vraies réponses d'erreur (400 + `reason`),
  et domaines présents dans la **whitelist PythonAnywhere** des comptes gratuits
  (`api.open-meteo.com`, `geocoding-api.open-meteo.com`).

## Endpoints testés

| # | Requête | Attendu |
|---|---------|---------|
| 1 | `GET /v1/forecast?latitude=48.8566&longitude=2.3522&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=Europe/Paris` | 200, JSON, météo actuelle de Paris |
| 2 | `GET /v1/forecast?...&daily=temperature_2m_max,temperature_2m_min&forecast_days=3` | 200, 3 jours consécutifs, max ≥ min |
| 3 | `GET /v1/search?name=Paris&count=1&language=fr` (géocodage) | 200, `results[0]` = Paris, FR |
| 4 | `GET /v1/search?name=zzqxw-ville-inexistante` | 200, **pas** de clé `results` |
| 5 | `GET /v1/forecast?latitude=999&...` | **400**, `{"error": true, "reason": "Latitude must be in range..."}` |
| 6 | `GET /v1/forecast?...&current=variable_inexistante` | **400**, `{"error": true, "reason": ...}` |
| 7 | `GET /v1/endpoint-inexistant` | **404**, `{"error": true, "reason": "Not Found"}` |
| 8 | 5 × `GET /v1/forecast?...&current=temperature_2m` | 200, latence p95 < 1000 ms |

## Hypothèses de contrat (champs attendus, types, codes)

- `Content-Type: application/json` sur toutes les réponses (succès **et** erreurs).
- `/forecast` (current) :
  - racine : `latitude` (float), `longitude` (float), `timezone` (str = `Europe/Paris`),
    `utc_offset_seconds` (int), `elevation` (number), `current_units` (object), `current` (object) ;
  - `current` : `time` (str ISO 8601), `interval` (int), `temperature_2m` (number, −60…60 °C),
    `relative_humidity_2m` (int, 0…100 %), `wind_speed_10m` (number ≥ 0) ;
  - `current_units.temperature_2m` = `"°C"` ; le point renvoyé est à moins de 0,5° des coordonnées demandées.
- `/forecast` (daily) : `daily.time`, `daily.temperature_2m_max`, `daily.temperature_2m_min`
  sont des listes de longueur `forecast_days`, dates consécutives, max ≥ min.
- `/search` : `results` = liste d'objets `{id:int, name:str, latitude, longitude, country_code, timezone}` ;
  absence de résultat = clé `results` absente (et non une erreur HTTP) ; `generationtime_ms` numérique.
- Erreurs : entrée invalide → **400**, route inconnue → **404**, corps `{"error": true, "reason": "<texte>"}`.

## Limites / rate limiting connu

- Gratuit en usage non commercial : **600 appels/minute, 5 000/heure, moins de 10 000/jour** (≈ 300 000/mois), d'après les conditions d'utilisation (vérifié le 22/09/2026).
- Notre charge : **12 requêtes par run** (+ 1 retry max par requête, plafond dur de 20/run),
  anti-spam de 5 minutes entre deux runs, run planifié toutes les 30 min → environ 600 requêtes/jour, très loin des quotas.
- En cas de dépassement l'API renvoie **429** : le client attend (`Retry-After`, plafonné à 5 s) puis fait 1 seul retry.

## Risques (instabilité, downtime, CORS, etc.)

- Données **dynamiques** (météo) : on teste des types et des plages, jamais des valeurs exactes.
- Messages d'erreur (`reason`) en texte libre, susceptibles de changer : on vérifie seulement
  la présence de `error: true` et d'un `reason` non vide (+ le mot « latitude » pour le test 5).
- Latence variable selon le réseau (proxy PythonAnywhere sur les comptes gratuits) :
  seuil QoS volontairement large (p95 < 1000 ms), timeout client de 3 s.
- Dépendance à l'allowlist PythonAnywhere (comptes gratuits) : si le domaine en sortait, tous les tests passeraient
  en ERROR (erreur réseau) ; le smoke test du déploiement le détecte (« Aucune requête sortante n'aboutit »).
- CORS : sans objet, les appels sont faits côté serveur (Python), pas depuis le navigateur.

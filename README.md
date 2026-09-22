------------------------------------------------------------------------------------------------------
🎯Atelier “Testing as Code & API Monitoring”
------------------------------------------------------------------------------------------------------
Aujourd’hui, vous allez passer du rôle de développeur au rôle d’ingénieur qualité.  
  
Internet est rempli d’API publiques : météo, devises, citations, géolocalisation, données statistiques…
Mais une API, ce n’est pas juste une URL qui répond. C’est un service.
Et un service doit être fiable, mesurable et surveillé.  
  
Votre mission :  
  
👉 Choisir une API publique.  
👉 Concevoir et implémenter une solution d’automatisation des tests.  
👉 Déployer votre solution sur PythonAnywhere.  
👉 Mesurer et exposer des indicateurs de qualité de service.    
  
-------------------------------------------------------------------------------------------------------
🧩 Séquence 1 : GitHUB
-------------------------------------------------------------------------------------------------------
Objectif : Création d'un Repository GitHUB pour travailler avec son projet  
Difficulté : Très facile (~10 minutes)
-------------------------------------------------------------------------------------------------------
**Faites un Fork de ce projet**. Si besoin, voici une vidéo d'accompagnement pour vous aider à "Forker" un Repository Github : [Forker ce projet](https://youtu.be/p33-7XQ29zQ)  

---------------------------------------------------
🧩 Séquence 2 : Création d'un site chez Pythonanywhere
---------------------------------------------------
Objectif : Créer un hébergement sur Pythonanywhere  
Difficulté : Faible (~10 minutes)
---------------------------------------------------

Rendez-vous sur **https://www.pythonanywhere.com/** et créez vous un compte. Puis créez un serveur Web **Flask 3.13**. 
  
---------------------------------------------------------------------------------------------
🧩 Séquence 3 : Les Actions GitHUB (Industrialisation Continue)
---------------------------------------------------------------------------------------------
Objectif : Automatiser la mise à jour de votre hébergement Pythonanywhere  
Difficulté : Moyenne (~15 minutes)
---------------------------------------------------------------------------------------------
Dans le Repository GitHUB que vous venez de créer précédemment lors de la séquence 1, vous avez un fichier intitulé deploy-pythonanywhere.yml et qui est déposé dans le répertoire .github/workflows. Ce fichier a pour objectif d'automatiser le déploiement de votre code sur votre site Pythonanywhere. Pour information, c'est ce que l'on appel des Actions GitHUB. Ce sont des scripts qui s'exécutent automatiquement lors de chaque Commit dans votre projet (C'est à dire à chaque modification de votre code). Ces scripts (appelés actions) sont au format yml qui est un format structuré proche de celui d'XML.  

Pour utiliser cette Action (deploy-pythonanywhere.yml), **vous avez besoin de créer des secrets dans GitHUB** afin de ne pas divulguer des informations sensibles aux internautes de passage dans votre Repository comme vos login et password par exemple.  

Pour cet atelier, **vous avez 4 secrets à créer** dans votre Repository GitHUB : **Settings → Secrets and variables → Actions → New repository secret**  
  
**PA_USERNAME** = votre username PythonAnywhere.  
**PA_TOKEN** = votre API token. Token à créer dans pythonanywhere (Acount → API Token).  
**PA_TARGET_DIR** = Web → Source code (ex: /home/monuser/myapp).  
**PA_WEBAPP_DOMAIN** = votre site (ex: monuser.pythonanywhere.com).  
  
**Dernière étape :** Pour engager l'automatisation de votre première Action, vous devez cliquer sur le gros boutton vert dans l'onglet supérieur [Actions] dans votre Repository Github. Le boutton s'intitule "I understand my workflows, go ahead and enable them". Ensuite procédez à une "petite" modification de votre fichier README.md GitHub puis faites un [Commit] pour déclancher l'action.   

Notions acquises de cette séquence :  
Vous avez vu dans cette séquence comment créer des secrets GiHUB afin de mettre en place de l'industrialisation continue.   
  
---------------------------------------------------
🔹 Séquence 4 : Atelier
---------------------------------------------------
Objectif : Travailler sur l'automatisation de vos tests  
Difficulté : Moyenne (~120 minutes)
---------------------------------------------------
**Consignes : Retrouvez les consignes de votre atelier sur votre site pythonanywhere**    
Vous pouvez retrouver le travail demandé dans le cadre de cet atelier directement sur votre site pythonanywhere (ex: monuser.pythonanywhere.com).    
   
--------------------------------------------------------------------
🧠 Troubleshooting :
---------------------------------------------------
Objectif : Visualiser ses logs et découvrir ses erreurs
---------------------------------------------------
Lors de vos développements, vous serez peut-être confronté à des erreurs systèmes car vous avez faits des erreurs de syntaxes dans votre code, faits de mauvaises déclarations de fonctions, appelez des modules inexistants, mal renseigner vos secrets, etc…  
Les causes d'erreurs sont quasi illimitées. **Vous devez donc vous tourner vers les logs de votre système pour comprendre d'où vient le problème** :  

Vos log sont accéssible via les URL suivantes :  
* Access log : {site}.pythonanywhere.com.access.log
* Error log : {site}.pythonanywhere.com.error.log
* Server log: {site}.pythonanywhere.com.server.log

------------------------------------------------------------------------------------------------------
✅ Réalisation : monitoring de l'API Open-Meteo
------------------------------------------------------------------------------------------------------
API testée : **[Open-Meteo](https://open-meteo.com/)** (sans clé, présente dans l'allowlist PythonAnywhere des comptes gratuits). Fiche de choix et contrat : [API_CHOICE.md](API_CHOICE.md). Données météo : Open-Meteo.com, licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (attribution affichée sur le dashboard, comme l'exigent les [conditions d'utilisation](https://open-meteo.com/en/terms)).

**Routes de l'application Flask**

| Route | Rôle |
|-------|------|
| `/` | Consignes de l'atelier |
| `/run` (GET/POST) | Lance un run de tests, l'enregistre en SQLite et renvoie le JSON (201). Anti-spam : **1 run / 5 min**, sinon 429 + `Retry-After` |
| `/dashboard` | Dernier run (statut, KPIs, interprétation, détail des tests), filtre de période, indicateurs agrégés, tendances latence / taux d'erreur, historique cliquable (`?run=<id>`) |
| `/health` | Santé de la solution : base SQLite joignable, âge et statut du dernier run, **version déployée** (SHA du commit), délai avant le prochain run autorisé (503 si la base est KO) |
| `/api/runs?period=24h\|7d\|30d\|all` | Historique + agrégats de la période en JSON |
| `/api/runs/latest`, `/api/runs/<id>` | Un run complet en JSON |
| `/export.json?period=…` | Export JSON téléchargeable (runs complets + agrégats) |
| `/robots.txt` | Interdit l'indexation de `/run` et de l'API |

**Outils du dashboard**

* **Pastille « solution ok / degraded »** (lien vers `/health`) : âge du dernier run, alerte si aucun run depuis plus de 3 h (planification cassée), version en prod.
* **Bouton « Lancer un run »** : désactivé avec compte à rebours tant que l'anti-spam bloque, au lieu de renvoyer une erreur.
* **Filtre de période** (24 h / 7 jours / 30 jours / Tout) qui pilote les indicateurs agrégés (runs UP, disponibilité moyenne, taux d'erreur moyen, p95 moyen et pire p95), les graphiques, l'historique et l'export JSON.
* **Graphiques** avec infobulle au survol (et au clavier sur la latence) ; un clic sur une barre ou une ligne d'historique ouvre le détail du run.

**Structure**

```
flask_app.py          # routes Flask, en-têtes de sécurité / cache
storage.py            # SQLite : runs, créneau anti-spam atomique, agrégats par période
scheduled_run.py      # point d'entrée d'une tâche planifiée PythonAnywhere (comptes éligibles)
tester/
├─ client.py          # wrapper HTTP : timeout 3 s, 1 retry max, 429/5xx, latence, 20 req et 25 s max par run
├─ tests.py           # 10 tests "as code" (contrat, erreurs attendues, QoS)
├─ metrics.py         # avg / p95 / dispo / taux d'erreur + interprétation
└─ runner.py          # exécute les tests et construit le run
templates/dashboard.html
tests_unit/           # 25 tests unitaires hors-ligne (faux serveur HTTP local), lancés par la CI avant déploiement
```

**Plan de tests (10 tests, 12 requêtes par run)**

| ID | Test | Catégorie |
|----|------|-----------|
| T01 | `GET /forecast` (current) → HTTP 200 + `Content-Type` JSON | Contrat |
| T02 | Champs obligatoires présents (racine, `current`, `current_units`) | Contrat |
| T03 | Types et plages (float/int/str ISO, température, humidité 0–100, unité °C, timezone) | Contrat |
| T04 | `daily` sur 3 jours : longueurs, dates consécutives, max ≥ min | Contrat |
| T05 | Géocodage « Paris » → `results[0]` = Paris, FR, coordonnées cohérentes | Contrat |
| T06 | Géocodage d'un nom inconnu → 200 sans `results` | Erreurs attendues |
| T07 | `latitude=999` → 400 + `{"error": true, "reason": ...}` | Erreurs attendues |
| T08 | Variable inconnue → 400 + corps d'erreur | Erreurs attendues |
| T09 | Endpoint inexistant → 404 | Erreurs attendues |
| T10 | 5 appels : latence p95 < 1000 ms | QoS |

**Robustesse** : timeout 3 s, 1 retry maximum sur timeout / erreur réseau / 429 / 5xx (jamais sur les 4xx attendus), attente `Retry-After` plafonnée à 5 s sur 429, backoff 0,5 s sur 5xx, plafond de 20 requêtes et 25 s par run (un compte gratuit n'a qu'un seul worker web : un run ne doit pas bloquer le site). Un test qui plante est classé `ERROR` sans interrompre le run. L'anti-spam repose sur un UPDATE conditionnel SQLite : fiable même avec plusieurs workers.

**Indicateurs QoS** (par run) : latence moyenne / p95 / min / max, taux d'erreur = (FAIL + ERROR) / tests, disponibilité = requêtes ayant obtenu une réponse exploitable (hors 5xx, timeouts, erreurs réseau), nombre de retries / 429 / 5xx. Statut `UP` (tout passe), `DEGRADED` (au moins un échec), `DOWN` (rien ne passe ou dispo < 50 %). Le dashboard affiche une interprétation en clair, et les mêmes indicateurs agrégés sur la période choisie.

---------------------------------------------------
🚀 Mise en production
---------------------------------------------------

**Les 4 secrets** (Settings → Secrets and variables → Actions) :

| Secret | Format attendu | Exemple |
|--------|----------------|---------|
| `PA_USERNAME` | nom d'utilisateur PythonAnywhere | `monuser` |
| `PA_TOKEN` | Account → API Token | *(ne jamais le committer)* |
| `PA_TARGET_DIR` | onglet Web → *Source code*, chemin absolu sans `/` final | `/home/monuser/mysite` |
| `PA_WEBAPP_DOMAIN` | domaine seul, sans `https://` ni `/` | `monuser.pythonanywhere.com` |
| `PA_HOST` *(optionnel)* | uniquement pour un compte EU | `eu.pythonanywhere.com` |

**Ce que fait le workflow de déploiement** ([deploy-pythonanywhere.yml](.github/workflows/deploy-pythonanywhere.yml)) à chaque push sur `main` :

1. **Tests unitaires** hors-ligne : un échec bloque le déploiement.
2. **Validation des secrets** : présence et format des 4 secrets, message explicite pour chaque erreur.
3. **Vérification réelle via l'API PythonAnywhere** (`GET /api/v0/user/<user>/webapps/<domaine>/`) : token et username valides (sinon 401), web app existante (sinon 404), `PA_TARGET_DIR` identique au *Source code* de la web app, Python 3.13.
4. **Upload des seuls fichiers d'exécution** (code Python hors tests + templates + `VERSION`), avec retry : l'API PythonAnywhere est limitée à 40 requêtes/min. `runs.db` n'est jamais envoyé, l'historique de prod est conservé.
5. **Reload** de la web app.
6. **Smoke test de la prod** : `/health` doit renvoyer le SHA du commit déployé, `/`, `/dashboard` et `/api/runs` doivent répondre 200, puis un vrai `POST /run` vérifie que les requêtes sortantes vers Open-Meteo passent le proxy PythonAnywhere.

**Planification**

* Les comptes gratuits **créés après le 15/01/2026** (08/01/2026 sur le serveur EU) n'ont **pas de tâche planifiée** ([doc PythonAnywhere](https://help.pythonanywhere.com/pages/FreeAccountsFeatures)). La planification principale est donc le workflow [`scheduled-run.yml`](.github/workflows/scheduled-run.yml), qui appelle `POST /run` **toutes les 30 minutes** puis contrôle `/health`.
* Compte payant ou compte gratuit plus ancien : onglet **Tasks** → `python3.13 /home/<user>/mysite/scheduled_run.py` (1 fois par jour en gratuit). Ces runs passent toujours et repoussent le prochain run manuel.

**Limites d'un compte gratuit récent** : 1 web app, 1 worker web, et la web app **expire au bout d'1 mois** : cliquer sur *« Run until 1 month from today »* dans l'onglet Web pour la prolonger. Si le site s'arrête, le workflow planifié échoue et GitHub le signale (onglet Actions, et e-mail selon tes réglages de notifications).

**Dépannage**

| Symptôme dans GitHub Actions | Cause probable |
|---|---|
| `PA_… manquant` / format invalide | secret absent ou mal saisi (voir tableau ci-dessus) |
| `Token refusé (HTTP 401)` | token révoqué ou erroné, mauvais `PA_USERNAME`, ou compte EU sans `PA_HOST` |
| `Web app … introuvable (HTTP 404)` | web app non créée ou `PA_WEBAPP_DOMAIN` erroné |
| `PA_TARGET_DIR différent du 'Source code'` | le code serait déposé dans un dossier que le site ne charge pas |
| `/health ne renvoie pas la version déployée` | erreur au démarrage : consulter `<site>.pythonanywhere.com.error.log` |
| `Aucune requête sortante n'aboutit` | domaine absent de l'allowlist / proxy PythonAnywhere |

**En local**

```bash
pip install -r requirements.txt
python -m unittest discover -s tests_unit -v   # tests unitaires hors-ligne
python scheduled_run.py                         # un run réel contre l'API
python flask_app.py                             # puis http://localhost:5000/dashboard (PORT=… pour changer)
```

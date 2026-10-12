Market Game 2027 : couverture d'un portefeuille d'électricité
Projet du cours Energy Market (EPF, 5e année, majeure Énergie et Environnement).
Nous jouons l'équipe Energy Management d'un fournisseur d'électricité français
(200 000 clients résidentiels RES1, 5 000 clients professionnels PRO1) et
construisons la stratégie de couverture de l'année de livraison 2027.
Tableau de bord interactif : `dashboard.html` (s'ouvre dans n'importe quel navigateur).
Ce que fait le modèle
Consommation 2027 : profils Enedis RES1 / PRO1, correction météo
(seuil de chauffage 15 °C, gradients dynamiques), calendrier 2027 avec jours fériés.
Courbe à température normale = moyenne dé-météorisée 2023–2025.
Scénarios : 4 années météo historiques (2022 à 2025). Spot 2027 heure par heure =
prix EEX du mois ou du trimestre × (1 − prime de risque) × (1 + b × anomalie de consommation)
× forme horaire historique. La pente prix-volume b est estimée par régression
sur les anomalies journalières d'hiver.
Stratégies de couverture : deux achats (T1 le 22/09/2026, T2 le 01/12/2026) en produits
mois, trimestres ou Cal-27 Base / Peak. Marge calculée heure par heure ; règle du Board :
meilleure marge espérée parmi les stratégies dont le pire cas reste au-dessus du plancher.
Risque : chocs de crise (+20 %, +50 %), Monte Carlo météo × niveau de prix,
sous-stratégies (16 combinaisons de produits par stratégie), analyse rétrospective.
T3 (31/12/2026) : position ouverte du 01/01/2027 à acheter ou revendre au day-ahead.
Lancer le projet
```bash
pip install -r requirements.txt
python export_dashboard.py      # calcule tout et ouvre dashboard.html
```
Sous Windows : double-clic sur `lancer_dashboard.bat`.
Les données (Enedis, prix day-ahead) sont téléchargées par les API et mises en cache
dans `data/` (non versionné).
Fichiers
Fichier	Rôle
`config.py`	Tous les paramètres : clients, prix EEX aux trois dates, règles du Board
`enedis_api.py`	Téléchargement des profils et températures Enedis
`prix_api.py`, `prix.py`	Prix day-ahead, anomalies, régression prix-volume, scénarios spot
`calendrier.py`	Jours fériés et alignement des calendriers
`load_model.py`, `load_2027.py`	Consommation normale et par scénario météo
`hedging.py`, `marges.py`	Stratégies et calcul des marges (version Python, par trimestres)
`main_suite.py`	Enchaînement des calculs en Python
`export_dashboard.py`	Prépare les données et génère `dashboard.html`
`dashboard_template.html`	Modèle du tableau de bord (moteur de calcul en JavaScript)
Modifier les paramètres
Le tableau de bord est en lecture seule par défaut. Le bouton Modifier déverrouille
les champs ; les changements restent dans le navigateur. Enregistrer en CSV crée
`dashboard_local.csv` (non versionné), relu au prochain lancement de `export_dashboard.py`.

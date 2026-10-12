NB_RES1 = 200_000
NB_PRO1 = 5_000

THETA_RES1 = 0.0521
THETA_PRO1 = 0.08004

PUISSANCE_RES1 = 6
PUISSANCE_PRO1 = 36

SEUIL_CHAUFFAGE = 15.0

# =========================
# PARAMETRES MARKET GAME 2027
# =========================

ANNEE_CIBLE = 2027
ANNEE_PROFIL_REF = [2023, 2024, 2025]   # moyenne des 4 formes
ANNEES_SCENARIOS = [2022, 2023, 2024, 2025]

# Prix day-ahead ENTSO-E (exports CSV, un fichier par année)
FICHIERS_PRIX = [
    "data/prix_entsoe_2022.csv",
    "data/prix_entsoe_2023.csv",
    "data/prix_entsoe_2024.csv",
    "data/prix_entsoe_2025.csv",
]

# Régression prix-volume
MOIS_HIVER = (11, 12, 1, 2, 3)

# Paramètres fixés par les guidelines
PRIX_VENTE = 95.0          # €/MWh, composante énergie
MARGE_CIBLE = 10.0         # €/MWh
PLANCHER_RISQUE = 5.0      # €/MWh, worst-case minimum
PRIME_RISQUE = 0.03        # 3 %

# A REMPLACER par le settlement EEX Cal-27 FR Base du 22/09/2026
FORWARD_T1_CAL_BASE = 83.31

# Part du scénario déjà intégrée au forward le 01/12 (à justifier)
ALPHA = 0.4



# Prix EEX du 22/09/2026 par trimestre (€/MWh)
FORWARDS_T1 = {
    "Q1": {"base": 139.00, "peak": 171.94},
    "Q2": {"base": 45.18,  "peak": 36.50},
    "Q3": {"base": 61.09,  "peak": 51.62},
    "Q4": {"base": 88.78,  "peak": 123.72},
}

FORWARD_T1_CAL_PEAK = 95.59   # Cal-27 Peak, settlement EEX du 22/09/2026


# Tests de stress : chocs sur le niveau des prix spot 2027
CHOCS_PRIX = {
    "Tension +20 %": 0.20,
    "Crise énergétique +50 %": 0.50,
}


# =====================================================================
# DONNÉES T2 (01/12/2026) ET T3 (31/12/2026)
# ---------------------------------------------------------------------
# À AJOUTER à la fin de config.py, SANS modifier le bloc T1 au-dessus.
# Guidelines §1 et §4.4 : la décision T1 doit rester fondée sur les
# prix du 22/09 ; la "ré-optimiser" avec des informations postérieures
# fait perdre les points de T1 ET de T2.
# Source : fichiers Moodle du 01/12/2026 et du 31/12/2026.
# =====================================================================

# Stratégie réellement décidée à T1 (nom exact d'une clé de
# hedging.STRATEGIES). Ses achats T1 sont figés à T2 et à T3.
STRATEGIE_T1 = "S4 Saisonnière"   # <-- à adapter à ta décision T1

# Prix mensuels EEX du 22/09/2026 (information T1) : (Base, Peak) €/MWh
MOIS_T1 = {
    "Jan": (159.54, 202.58), "Feb": (153.15, 201.51), "Mar": (105.63, 118.25),
    "Apr": (59.51, 43.02),   "May": (39.33, 26.13),   "Jun": (36.90, 39.89),
}

# ---------------- T2 : 01/12/2026 ----------------
# Prévision commerciale : RES1 -5,9 %, PRO1 -8,3 % par rapport à T1
CLIENTS_T2 = {"RES1": 188_200, "PRO1": 4_585}

FORWARD_T2_CAL = {"base": 73.70, "peak": 83.74}
FORWARDS_T2 = {
    "Q1": {"base": 119.54, "peak": 146.15},
    "Q2": {"base": 42.47,  "peak": 35.04},
    "Q3": {"base": 56.20,  "peak": 48.52},
    "Q4": {"base": 77.24,  "peak": 106.40},
}
MOIS_T2 = {
    "Jan": (135.42, 169.95), "Feb": (131.53, 171.07), "Mar": (92.83, 102.75),
    "Apr": (55.44, 40.88),   "May": (37.03, 25.09),   "Jun": (35.12, 38.70),
}

# ---------------- T3 : 31/12/2026 ----------------
# Prévision commerciale "réelle" pour le 01/01/2027.
# Attention : dans le fichier Moodle, la formule RES1 est T1 + T2 x variation
# (200 000 + 188 200 x -4,5 % = 191 531) alors que PRO1 est T1 x (1 + variation).
# On garde les valeurs affichées par le fichier ; à signaler dans le rapport.
CLIENTS_T3 = {"RES1": 191_531, "PRO1": 4_745}

FORWARD_T3_CAL = {"base": 78.37, "peak": 90.31}
FORWARDS_T3 = {
    "Q1": {"base": 133.88, "peak": 166.61},
    "Q2": {"base": 43.32,  "peak": 35.39},
    "Q3": {"base": 56.76,  "peak": 49.01},
    "Q4": {"base": 80.33,  "peak": 111.72},
}
MOIS_T3 = {
    "Jan": (156.25, 199.83), "Feb": (147.87, 196.07), "Mar": (98.87, 110.66),
    "Apr": (57.02, 41.53),   "May": (37.71, 25.24),   "Jun": (35.42, 38.93),
}

# Température prévue le 01/01/2027, heure par heure (°C), de 00h-01h à 23h-24h
TEMPERATURE_PREVUE_0101 = [
    0.5, 0.0, -0.5, -1.0, -1.5, -2.0, -2.0, -1.5, -0.5, 1.0, 2.5, 3.5,
    4.0, 4.0, 3.5, 2.5, 1.5, 1.0, 0.5, 0.0, -0.5, -1.0, -1.5, -2.0,
]

# Centrale solaire du portefeuille : puissance installée et production
# prévue le 01/01/2027 (MWh par heure)
SOLAIRE_MWC = 80
SOLAIRE_PREVU_0101 = [
    0, 0, 0, 0, 0, 0, 0, 0, 2, 8, 15, 21,
    24, 21, 14, 5, 0.5, 0, 0, 0, 0, 0, 0, 0,
]

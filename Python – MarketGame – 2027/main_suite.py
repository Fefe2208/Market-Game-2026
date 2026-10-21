"""
Suite du Market Game : à lancer après avoir constitué le cache data/
avec main.py (FORCER_MAJ_API = True une première fois).
"""

import config

from enedis_api import (
    recuperer_profil, nettoyer_profil,
    recuperer_temperatures, nettoyer_temperatures,
    recuperer_gradients, nettoyer_gradients,
    charger_ou_actualiser,
)
from load_model import (
    calculer_puissance_moyenne, calculer_load,
    fusionner_load_normale, construire_load_finale,
)
from load_2027 import (
    construire_base_2027, construire_loads_scenarios,
    tableau_recap, volumes_mensuels, controle_calendrier,
    tracer_loads_2027,
)
from prix import (
    charger_prix_entsoe, controle_prix,
    anomalies_journalieres, regression_prix_volume, tracer_regression,
    niveau_spot_2027, construire_spot_2027,
    tableau_scenarios_prix, tracer_spots_2027,
    anomalies_trimestrielles, forwards_par_bloc,
    construire_spot_2027_trimestriel, controle_spot_trimestriel,
)
from prix_api import recuperer_prix, nettoyer_prix
from hedging import (
    decouper_load_en_produits, presenter_cal_plus_trimestres, tracer_couverture,
    STRATEGIES, construire_achats, tableau_mw_par_produit,
    taux_de_couverture, cout_achats_t1, prix_t1_depuis_config,
)
from marges import (
    evaluer_strategies, synthese, choisir_strategie,
    tracer_esperee_vs_pire, tracer_marges_par_scenario,
    cout_protection, sensibilite_plancher,
    evaluer_avec_crises, synthese_avec_crises, tracer_crises,
)


# =========================
# 0. DONNEES (cache local)
# =========================

FORCER_MAJ_API = False

res1 = charger_ou_actualiser("res1.csv", lambda: recuperer_profil("RES1_BASE"), nettoyer_profil, FORCER_MAJ_API)
pro1 = charger_ou_actualiser("pro1.csv", lambda: recuperer_profil("PRO1_BASE"), nettoyer_profil, FORCER_MAJ_API)
temperatures = charger_ou_actualiser("temperatures.csv", recuperer_temperatures, nettoyer_temperatures, FORCER_MAJ_API)
gradients = charger_ou_actualiser("gradients.csv", recuperer_gradients, nettoyer_gradients, FORCER_MAJ_API)

res1["load_normal_kw"] = calculer_load(
    res1["coefficient_dynamique"],
    calculer_puissance_moyenne(config.NB_RES1, config.THETA_RES1, config.PUISSANCE_RES1),
)
pro1["load_normal_kw"] = calculer_load(
    pro1["coefficient_dynamique"],
    calculer_puissance_moyenne(config.NB_PRO1, config.THETA_PRO1, config.PUISSANCE_PRO1),
)


# =========================
# 1. LOAD NORMALE 2027
# =========================

base_2027 = construire_base_2027(
    res1, pro1, gradients, temperatures,
    annee_ref=config.ANNEE_PROFIL_REF,
    annee_cible=config.ANNEE_CIBLE,
)

print("\n--- CONTROLE CALENDRIER 2027 (MW moyen par type de jour) ---")
print(controle_calendrier(base_2027, config.ANNEE_CIBLE))


# =========================
# 2. LOADS 2027 PAR SCENARIO METEO
# =========================

loads_2027 = construire_loads_scenarios(
    base_2027, temperatures, config.ANNEES_SCENARIOS,
    config.ANNEE_CIBLE, config.SEUIL_CHAUFFAGE,
)

recap_load = tableau_recap(base_2027, loads_2027)
print("\n--- RECAP VOLUMES 2027 ---")
print(recap_load.round(1).to_string())

mensuel = volumes_mensuels(base_2027, loads_2027)
print("\n--- VOLUMES MENSUELS 2027 (MWh) ---")
print(mensuel.round(0).to_string())

tracer_loads_2027(base_2027, loads_2027)
tracer_loads_2027(base_2027, loads_2027, "2027-01-11", "2027-01-18")

#raise SystemExit("Fin de l'étape volumes")


# =========================
# 3. LIEN PRIX-VOLUME (historique)
# =========================

prix = charger_ou_actualiser("prix.csv", recuperer_prix, nettoyer_prix, FORCER_MAJ_API)
prix = prix[prix["horodate"].dt.year.between(2022, 2025)]
prix = prix.set_index("horodate")["prix"].resample("h").mean().reset_index()
print("\n--- CONTROLE PRIX ---")
print(controle_prix(prix))

load_normale_hist = fusionner_load_normale(res1, pro1)
load_finale_hist = construire_load_finale(
    load_normale_hist, temperatures, gradients, config.SEUIL_CHAUFFAGE
)

anomalies = anomalies_journalieres(load_finale_hist, prix)
reg = regression_prix_volume(anomalies, mois=config.MOIS_HIVER, annees=config.ANNEES_SCENARIOS)
print(f"\nb = {reg['b']:.2f} | R² = {reg['r2']:.2f} | n = {reg['n']} jours")
print("b par année :", reg["b_par_annee"])
tracer_regression(anomalies, reg, config.MOIS_HIVER)

# Test de sensibilité demandé : b sans 2022 (année de crise)
reg_sans_2022 = regression_prix_volume(anomalies, config.MOIS_HIVER, [2023, 2024, 2025])
print(f"b sans 2022 = {reg_sans_2022['b']:.2f}")


# =========================
# 4. SCENARIOS SPOT 2027 + FORWARD T2
# =========================

if config.FORWARD_T1_CAL_BASE is None:
    raise SystemExit("Renseigner FORWARD_T1_CAL_BASE (settlement EEX du 22/09/2026) dans config.py")

F_T1 = config.FORWARD_T1_CAL_BASE
b = reg["b"]

tab_prix = tableau_scenarios_prix(
    recap_load, F_T1, b, config.ALPHA, config.PRIME_RISQUE
)
print("\n--- SCENARIOS PRIX 2027 ---")
print(tab_prix.to_string())

# Anomalies de volume par trimestre (recentrées, comme la correction 1)
anom_trim = anomalies_trimestrielles(base_2027, loads_2027)
print("\n--- ANOMALIES DE VOLUME PAR TRIMESTRE (%) ---")
print((anom_trim * 100).round(2))

# Courbes spot 2027 ancrées sur les trimestres EEX (Peak / Off-peak)
spots_2027 = {}
for annee in config.ANNEES_SCENARIOS:
    spots_2027[annee] = construire_spot_2027_trimestriel(
        prix, annee, config.FORWARDS_T1, b, anom_trim,
        config.PRIME_RISQUE, config.ANNEE_CIBLE,
    )

print("\n--- PRIX EEX PAR BLOC (22/09) ---")
print(forwards_par_bloc(config.FORWARDS_T1, spots_2027[2025]))

print("\n--- CONTROLE : SPOT 2027 MOYEN PAR TRIMESTRE (€/MWh) ---")
print(controle_spot_trimestriel(spots_2027))

tracer_spots_2027(spots_2027, F_T1)

# Sensibilité du forward T2 à alpha (0.2 vs 0.6)
for a in (0.2, 0.6):
    print(f"\nalpha = {a}")
    print(tableau_scenarios_prix(recap_load, F_T1, b, a, config.PRIME_RISQUE)
          [["niveau_spot_2027", "forward_T2_anticipe"]].to_string())


# =========================
# 5. STRATEGIES - PARTIE 1 : DECOUPAGE EN PRODUITS EEX
# =========================

produits = decouper_load_en_produits(base_2027)
print("\n--- COUVERTURE 100 % : MW PAR TRIMESTRE ---")
print(produits.to_string())

print("\n--- COUVERTURE 100 % : MW PAR PRODUIT EEX ---")
print(presenter_cal_plus_trimestres(produits))

# Une semaine d'hiver et une semaine d'été
tracer_couverture(base_2027, produits, "2027-01-11", "2027-01-18")
tracer_couverture(base_2027, produits, "2027-07-12", "2027-07-19")


# =========================
# 5. STRATEGIES - PARTIE 2 : LES 6 STRATEGIES
# =========================

import pandas as pd

prix_t1 = prix_t1_depuis_config(config)

achats_strategies = {}
resume = []

for nom, strategie in STRATEGIES.items():
    achats = construire_achats(strategie, produits, base_2027)
    achats_strategies[nom] = achats
    resume.append({
        "strategie": nom,
        **taux_de_couverture(achats, produits),
        **cout_achats_t1(achats, produits, prix_t1),
    })

print("\n--- RESUME DES STRATEGIES ---")
print(pd.DataFrame(resume).set_index("strategie").to_string())

for nom, achats in achats_strategies.items():
    print(f"\n--- {nom} : MW PAR PRODUIT ---")
    print(tableau_mw_par_produit(achats).to_string(index=False))




# =========================
# 6. MARGES ET CHOIX DE LA STRATEGIE
# =========================

pd.set_option("display.width", 250)

# --- 6a. Scénarios météo seuls (comme avant)
resultats_meteo = evaluer_strategies(
    achats_strategies, loads_2027, spots_2027,
    prix_t1, config.FORWARDS_T1, b, anom_trim,
    alpha=config.ALPHA,
    prime_risque=config.PRIME_RISQUE,
    prix_vente=config.PRIX_VENTE,
)
synth_meteo = synthese(resultats_meteo, plancher=config.PLANCHER_RISQUE)
print("\n--- SYNTHESE : RISQUE METEO SEUL (€/MWh) ---")
print(synth_meteo.round(2).to_string())
tracer_marges_par_scenario(resultats_meteo, plancher=config.PLANCHER_RISQUE)

# --- 6b. Avec les tests de stress "crise énergétique"
print("\n--- TESTS DE STRESS ---")
resultats = evaluer_avec_crises(
    achats_strategies, loads_2027, spots_2027,
    prix_t1, config.FORWARDS_T1, b, anom_trim,
    alpha=config.ALPHA,
    chocs=config.CHOCS_PRIX,
    prime_risque=config.PRIME_RISQUE,
    prix_vente=config.PRIX_VENTE,
)
synth = synthese_avec_crises(resultats, plancher=config.PLANCHER_RISQUE)
print("\n--- SYNTHESE AVEC CRISES (€/MWh) ---")
print(synth.round(2).to_string())

choix = choisir_strategie(synth, plancher=config.PLANCHER_RISQUE)

print("\n--- COUT DE LA PROTECTION (par rapport à S0, €/MWh) ---")
print(cout_protection(synth).round(2).to_string())

print("\n--- SENSIBILITE AU PLANCHER DU BOARD ---")
print(sensibilite_plancher(synth).to_string())

tracer_crises(synth)
tracer_esperee_vs_pire(synth, plancher=config.PLANCHER_RISQUE)


# =========================
# 7. SENSIBILITE DE LA DECISION A b ET A ALPHA (guidelines §3.2 et §3.3)
# =========================

# --- b corrigé : le volume est comparé, comme le prix, à la moyenne
#     de son mois et de son type de jour
hiver = anomalies[anomalies["mois"].isin(config.MOIS_HIVER)
                  & anomalies["annee"].isin(config.ANNEES_SCENARIOS)].copy()
hiver["x"] = hiver["x"] - hiver.groupby(["annee", "mois", "type_jour"])["x"].transform("mean")
reg_intra = regression_prix_volume(hiver, config.MOIS_HIVER)
b_intra = reg_intra["b"]
print(f"\nb du modèle (méthode du cours) = {b:.2f} | R² = {reg['r2']:.2f}")
print(f"b corrigé = {b_intra:.2f} | R² = {reg_intra['r2']:.2f} | n = {reg_intra['n']} jours")
print("b corrigé par année :", reg_intra["b_par_annee"])

# --- alpha "temps écoulé" : 70 jours / jours jusqu'au milieu de la livraison
jours = {1: 146, 2: 236, 3: 327, 4: 419}
poids = {q: produits.loc[f"Q{q}", "energie_load_MWh"] * config.FORWARDS_T1[f"Q{q}"]["base"]
         for q in jours}
alpha_temps = sum(70 / jours[q] * poids[q] for q in jours) / sum(poids.values())
part_ete = (poids[2] + poids[3]) / sum(poids.values())
print(f"alpha 'temps écoulé' pondéré par le coût = {alpha_temps:.2f}")
print(f"part de l'été (Q2 + Q3) dans le coût = {part_ete * 100:.0f} %"
      f" -> bascule S7/S4 attendue vers alpha = {2 * part_ete:.2f}")

# --- la décision avec chaque b et chaque alpha
print("\n--- SENSIBILITE DE LA DECISION A b ET A ALPHA ---")
for b_test in (b, reg_sans_2022["b"], b_intra):
    spots_test = {an: construire_spot_2027_trimestriel(
                      prix, an, config.FORWARDS_T1, b_test, anom_trim,
                      config.PRIME_RISQUE, config.ANNEE_CIBLE)
                  for an in config.ANNEES_SCENARIOS}
    for a_test in (0.2, config.ALPHA, 0.6):
        res_test = evaluer_avec_crises(
            achats_strategies, loads_2027, spots_test, prix_t1, config.FORWARDS_T1,
            b_test, anom_trim, alpha=a_test, chocs=config.CHOCS_PRIX,
            prime_risque=config.PRIME_RISQUE, prix_vente=config.PRIX_VENTE)
        print(f"\nb = {b_test:.2f}, alpha = {a_test} :")
        choisir_strategie(synthese_avec_crises(res_test, plancher=config.PLANCHER_RISQUE),
                          plancher=config.PLANCHER_RISQUE)
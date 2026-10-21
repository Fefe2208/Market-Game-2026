import config

from enedis_api import (
    recuperer_profil,
    nettoyer_profil,
    recuperer_temperatures,
    nettoyer_temperatures,
    recuperer_gradients,
    nettoyer_gradients,
    charger_ou_actualiser
)


from load_model import (
    calculer_puissance_moyenne,
    calculer_load,
    fusionner_load_normale,
    calculer_cm,
    construire_load_finale
)


from visualisation import (
    tracer_load_normale,
    tracer_semaine,
    tracer_comparaison_load
)


from scenarios import (
    creer_scenarios_meteo,
    remapper_tous_les_scenarios
)


# =========================
# CONFIGURATION
# =========================

FORCER_MAJ_API = False


# =========================
# PROFIL RES1
# =========================

res1 = charger_ou_actualiser(
    "res1.csv",
    lambda: recuperer_profil("RES1_BASE"),
    nettoyer_profil,
    FORCER_MAJ_API
)


# =========================
# PROFIL PRO1
# =========================

pro1 = charger_ou_actualiser(
    "pro1.csv",
    lambda: recuperer_profil("PRO1_BASE"),
    nettoyer_profil,
    FORCER_MAJ_API
)


# =========================
# TEMPERATURES
# =========================

temperatures = charger_ou_actualiser(
    "temperatures.csv",
    recuperer_temperatures,
    nettoyer_temperatures,
    FORCER_MAJ_API
)


# =========================
# GRADIENTS
# =========================

gradients = charger_ou_actualiser(
    "gradients.csv",
    recuperer_gradients,
    nettoyer_gradients,
    FORCER_MAJ_API
)


# =========================
# PUISSANCES MOYENNES
# =========================

puissance_res1 = calculer_puissance_moyenne(
    config.NB_RES1,
    config.THETA_RES1,
    config.PUISSANCE_RES1
)

puissance_pro1 = calculer_puissance_moyenne(
    config.NB_PRO1,
    config.THETA_PRO1,
    config.PUISSANCE_PRO1
)


# =========================
# LOAD A TEMPERATURE NORMALE
# =========================

res1["load_normal_kw"] = calculer_load(
    res1["coefficient_dynamique"],
    puissance_res1
)

pro1["load_normal_kw"] = calculer_load(
    pro1["coefficient_dynamique"],
    puissance_pro1
)


# =========================
# VERIFICATIONS
# =========================

print("\n--- RES1 ---")
print(res1.head())
print(
    "Période :",
    res1["horodate"].min(),
    "->",
    res1["horodate"].max()
)

print("\n--- PRO1 ---")
print(pro1.head())
print(
    "Période :",
    pro1["horodate"].min(),
    "->",
    pro1["horodate"].max()
)

print("\n--- TEMPERATURES ---")
print(temperatures.head())
print(
    "Période :",
    temperatures["horodate"].min(),
    "->",
    temperatures["horodate"].max()
)

print("\n--- GRADIENTS ---")
print(gradients.head())
print(
    "Période :",
    gradients["horodate"].min(),
    "->",
    gradients["horodate"].max()
)



load_normale = fusionner_load_normale(
    res1,
    pro1
)

print("\n--- LOAD NORMALE ---")
print(load_normale.head())


tracer_load_normale(load_normale)

tracer_semaine(
    load_normale,
    "2025-01-01",
    "2025-01-07"
)


# =========================
# LOAD FINALE CORRIGEE METEO
# =========================

load_finale = construire_load_finale(
    load_normale,
    temperatures,
    gradients,
    seuil_chauffage=config.SEUIL_CHAUFFAGE
)

print("\n--- LOAD FINALE ---")
print(load_finale.head())

print("\nPériode de la load finale :")
print(
    load_finale["horodate"].min(),
    "->",
    load_finale["horodate"].max()
)

print("\nNombre de points :")
print(len(load_finale))


tracer_comparaison_load(
    load_finale,
    "2022-01-10",
    "2022-01-17"
)

tracer_comparaison_load(
    load_finale,
    "2023-12-01",
    "2023-12-08"
)

tracer_comparaison_load(
    load_finale,
    "2024-01-01",
    "2024-12-31"
)

load_finale["ecart_mw"] = (
    load_finale["load_final_total_mw"]
    - load_finale["load_normal_total_mw"]
)


# =========================
# CONTROLE DES ANNEES
# =========================


print("\n--- CONTROLE DES ANNEES ---")

for annee in [2022, 2023, 2024, 2025]:

    donnees_annee = load_finale[
        load_finale["horodate"].dt.year == annee
    ]

    print(f"\nAnnée {annee}")
    print("Nombre de points :", len(donnees_annee))
    print(
        "Début :",
        donnees_annee["horodate"].min()
    )
    print(
        "Fin :",
        donnees_annee["horodate"].max()
    )

    print(
        "Valeurs manquantes :",
        donnees_annee.isna().sum().sum()
    )



# =========================
# SCENARIOS METEO
# =========================

ANNEES_SCENARIOS = [
    2022,
    2023,
    2024,
    2025
]

scenarios_meteo = creer_scenarios_meteo(
    temperatures,
    ANNEES_SCENARIOS
)


print("\n--- SCENARIOS METEO ---")

for annee, scenario in scenarios_meteo.items():

    print(f"\nScénario météo {annee}")

    print(
        "Nombre de points :",
        len(scenario)
    )

    print(
        "Période :",
        scenario["horodate"].min(),
        "->",
        scenario["horodate"].max()
    )

    print(
        "Anomalie moyenne :",
        round(
            scenario[
                "anomalie_temperature"
            ].mean(),
            2
        ),
        "°C"
    )

    print(
        "Anomalie minimale :",
        round(
            scenario[
                "anomalie_temperature"
            ].min(),
            2
        ),
        "°C"
    )

    print(
        "Anomalie maximale :",
        round(
            scenario[
                "anomalie_temperature"
            ].max(),
            2
        ),
        "°C"
    )


scenarios_2027 = remapper_tous_les_scenarios(
    scenarios_meteo,
    annee_cible=2027
)


print("\n--- SCENARIOS REMAPPES SUR 2027 ---")

for annee_source, scenario in scenarios_2027.items():

    print(
        f"\nScénario météo {annee_source} -> 2027"
    )

    print(
        "Nombre de points :",
        len(scenario)
    )

    print(
        "Période :",
        scenario["horodate"].min(),
        "->",
        scenario["horodate"].max()
    )
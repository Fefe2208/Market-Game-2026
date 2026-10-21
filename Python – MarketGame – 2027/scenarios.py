import pandas as pd


def creer_scenario_meteo(temperatures, annee):
    """
    Crée un scénario météo historique à partir
    des températures Enedis d'une année donnée.

    Le scénario contient :
    - température normale
    - température réelle
    - anomalie météo

    La résolution est ramenée à 30 minutes.
    """

    scenario = temperatures[
        temperatures["horodate"].dt.year == annee
    ].copy()

    scenario = scenario[
        [
            "horodate",
            "temperature_normale_lissee_degc",
            "temperature_realisee_lissee_degc"
        ]
    ]

    scenario = scenario.rename(
        columns={
            "temperature_normale_lissee_degc": "temperature_normale",
            "temperature_realisee_lissee_degc": "temperature_reelle"
        }
    )

    # ==========================================
    # PASSAGE EN RESOLUTION 30 MINUTES
    # ==========================================

    scenario = (
        scenario
        .set_index("horodate")
        .resample("30min")
        .mean()
        .reset_index()
    )

    # ==========================================
    # ANOMALIE METEO
    # ==========================================

    scenario["anomalie_temperature"] = (
        scenario["temperature_reelle"]
        - scenario["temperature_normale"]
    )

    # Année source du scénario
    scenario["annee_scenario"] = annee

    return scenario


def creer_scenarios_meteo(temperatures, annees):
    """
    Crée plusieurs scénarios météo historiques.

    Retourne un dictionnaire :
    {
        2022: dataframe,
        2023: dataframe,
        ...
    }
    """

    scenarios = {}

    for annee in annees:

        scenario = creer_scenario_meteo(
            temperatures,
            annee
        )

        scenarios[annee] = scenario

    return scenarios



def remapper_scenario_vers_annee(
    scenario,
    annee_cible=2027
):
    """
    Remappe un scénario météo historique vers une année cible.

    Le rapprochement se fait par :
    - mois
    - jour
    - heure
    - minute

    Cela permet de gérer correctement :
    - les changements d'heure
    - le 29 février
    - les années ayant des calendriers DST différents
    """

    scenario = scenario.copy()

    # Année météo utilisée
    annee_source = int(
        scenario["annee_scenario"].iloc[0]
    )

    # ========================================================
    # 1. CLES CALENDAIRES DU SCENARIO HISTORIQUE
    # ========================================================

    scenario["mois"] = scenario["horodate"].dt.month
    scenario["jour"] = scenario["horodate"].dt.day
    scenario["heure"] = scenario["horodate"].dt.hour
    scenario["minute"] = scenario["horodate"].dt.minute


    # ========================================================
    # 2. GESTION DU CHANGEMENT D'HEURE AUTOMNE
    # ========================================================
    #
    # Certaines heures existent deux fois.
    # On prend la moyenne des deux valeurs météo.
    #

    scenario_reference = (
        scenario.groupby(
            [
                "mois",
                "jour",
                "heure",
                "minute"
            ],
            as_index=False
        )[
            [
                "temperature_normale",
                "temperature_reelle",
                "anomalie_temperature"
            ]
        ]
        .mean()
    )


    # ========================================================
    # 3. CREATION DU VRAI CALENDRIER 2027
    # ========================================================

    calendrier_cible = pd.date_range(
        start=f"{annee_cible}-01-01 00:00",
        end=f"{annee_cible}-12-31 23:30",
        freq="30min",
        tz="Europe/Paris"
    )

    scenario_cible = pd.DataFrame(
        {
            "horodate": calendrier_cible
        }
    )


    # ========================================================
    # 4. CLES CALENDAIRES 2027
    # ========================================================

    scenario_cible["mois"] = (
        scenario_cible["horodate"].dt.month
    )

    scenario_cible["jour"] = (
        scenario_cible["horodate"].dt.day
    )

    scenario_cible["heure"] = (
        scenario_cible["horodate"].dt.hour
    )

    scenario_cible["minute"] = (
        scenario_cible["horodate"].dt.minute
    )


    # ========================================================
    # 5. ASSOCIATION METEO HISTORIQUE -> 2027
    # ========================================================

    scenario_cible = pd.merge(
        scenario_cible,
        scenario_reference,
        on=[
            "mois",
            "jour",
            "heure",
            "minute"
        ],
        how="left"
    )


    # ========================================================
    # 6. GESTION DES PETITS TROUS LIES AU CHANGEMENT D'HEURE
    # ========================================================

    colonnes_meteo = [
        "temperature_normale",
        "temperature_reelle",
        "anomalie_temperature"
    ]

    scenario_cible[colonnes_meteo] = (
        scenario_cible[colonnes_meteo]
        .interpolate(
            method="linear",
            limit_direction="both"
        )
    )


    # ========================================================
    # 7. INFORMATIONS DU SCENARIO
    # ========================================================

    scenario_cible["annee_scenario"] = (
        annee_source
    )

    scenario_cible["annee_cible"] = (
        annee_cible
    )


    # ========================================================
    # 8. SUPPRESSION DES COLONNES TECHNIQUES
    # ========================================================

    scenario_cible = scenario_cible.drop(
        columns=[
            "mois",
            "jour",
            "heure",
            "minute"
        ]
    )

    return scenario_cible


def remapper_tous_les_scenarios(
    scenarios,
    annee_cible=2027
):
    """
    Remappe tous les scénarios historiques
    vers l'année cible.
    """

    scenarios_cibles = {}

    for annee_source, scenario in scenarios.items():

        scenario_cible = remapper_scenario_vers_annee(
            scenario,
            annee_cible
        )

        scenarios_cibles[
            annee_source
        ] = scenario_cible

    return scenarios_cibles
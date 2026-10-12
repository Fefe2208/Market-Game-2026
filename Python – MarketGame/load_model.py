import pandas as pd
import numpy as np

def calculer_puissance_moyenne(nb_clients, theta, puissance_souscrite):
    return nb_clients * theta * puissance_souscrite


def calculer_load(coefficient, puissance_moyenne):
    return coefficient * puissance_moyenne


def fusionner_load_normale(res1, pro1):
    """
    Fusionne les loads normales RES1 et PRO1
    sur les horodates communes.
    """

    res1_temp = res1[
        ["horodate", "load_normal_kw"]
    ].rename(
        columns={
            "load_normal_kw": "load_normal_res1_kw"
        }
    )

    pro1_temp = pro1[
        ["horodate", "load_normal_kw"]
    ].rename(
        columns={
            "load_normal_kw": "load_normal_pro1_kw"
        }
    )

    load = pd.merge(
        res1_temp,
        pro1_temp,
        on="horodate",
        how="inner"
    )

    load["load_normal_total_kw"] = (
        load["load_normal_res1_kw"]
        + load["load_normal_pro1_kw"]
    )

    load["load_normal_total_mw"] = (
        load["load_normal_total_kw"] / 1000
    )

    return load



def calculer_cm(
    temperature_reelle,
    temperature_normale,
    gradient,
    seuil_chauffage=15.0
):
    """
    Calcule le coefficient de correction météo CM.
    """

    temperature_reelle = np.asarray(
        temperature_reelle,
        dtype=float
    )

    temperature_normale = np.asarray(
        temperature_normale,
        dtype=float
    )

    gradient = np.asarray(
        gradient,
        dtype=float
    )

    cm = np.ones_like(
        temperature_reelle
    )

    deux_froides = (
        (temperature_reelle < seuil_chauffage)
        & (temperature_normale < seuil_chauffage)
    )

    reelle_froide = (
        (temperature_reelle < seuil_chauffage)
        & (temperature_normale >= seuil_chauffage)
    )

    normale_froide = (
        (temperature_normale < seuil_chauffage)
        & (temperature_reelle >= seuil_chauffage)
    )

    cm[deux_froides] = (
        1
        + gradient[deux_froides]
        * (
            temperature_normale[deux_froides]
            - temperature_reelle[deux_froides]
        )
    )

    cm[reelle_froide] = (
        1
        + gradient[reelle_froide]
        * (
            seuil_chauffage
            - temperature_reelle[reelle_froide]
        )
    )

    cm[normale_froide] = (
        1
        + gradient[normale_froide]
        * (
            temperature_normale[normale_froide]
            - seuil_chauffage
        )
    )

    return pd.Series(cm)



def construire_load_finale(
    load_normale,
    temperatures,
    gradients,
    seuil_chauffage=15.0
):
    """
    Construit le tableau complet de consommation.

    Fusionne :
    - la load normale RES1 / PRO1
    - les températures normales et réalisées
    - les gradients RES1 / PRO1

    Puis calcule :
    - CM RES1
    - CM PRO1
    - load finale RES1
    - load finale PRO1
    - load finale totale
    """

    # ========================================================
    # 1. PREPARATION DES TEMPERATURES
    # ========================================================

    temperatures_temp = temperatures[
        [
            "horodate",
            "temperature_normale_lissee_degc",
            "temperature_realisee_lissee_degc"
        ]
    ].copy()

    temperatures_temp = temperatures_temp.rename(
        columns={
            "temperature_normale_lissee_degc": "temperature_normale",
            "temperature_realisee_lissee_degc": "temperature_reelle"
        }
    )


    # ========================================================
    # 2. PREPARATION DES GRADIENTS
    # ========================================================

    gradients_temp = gradients[
        [
            "horodate",
            "res1_base",
            "pro1_base"
        ]
    ].copy()

    gradients_temp = gradients_temp.rename(
        columns={
            "res1_base": "gradient_res1",
            "pro1_base": "gradient_pro1"
        }
    )

    # Sécurise le type numérique
    gradients_temp["gradient_res1"] = pd.to_numeric(
        gradients_temp["gradient_res1"],
        errors="coerce"
    )

    gradients_temp["gradient_pro1"] = pd.to_numeric(
        gradients_temp["gradient_pro1"],
        errors="coerce"
    )


    # ========================================================
    # 3. FUSION LOAD + TEMPERATURES
    # ========================================================

    load = pd.merge(
        load_normale,
        temperatures_temp,
        on="horodate",
        how="inner"
    )


    # ========================================================
    # 4. FUSION AVEC LES GRADIENTS
    # ========================================================

    load = pd.merge(
        load,
        gradients_temp,
        on="horodate",
        how="inner"
    )

    load = load.sort_values(
        "horodate"
    ).reset_index(
        drop=True
    )


    # ========================================================
    # 5. CALCUL DES COEFFICIENTS METEO
    # ========================================================

    load["cm_res1"] = calculer_cm(
        load["temperature_reelle"],
        load["temperature_normale"],
        load["gradient_res1"],
        seuil_chauffage
    )

    load["cm_pro1"] = calculer_cm(
        load["temperature_reelle"],
        load["temperature_normale"],
        load["gradient_pro1"],
        seuil_chauffage
    )


    # ========================================================
    # 6. LOAD FINALE PAR PROFIL
    # ========================================================

    load["load_final_res1_kw"] = (
        load["load_normal_res1_kw"]
        * load["cm_res1"]
    )

    load["load_final_pro1_kw"] = (
        load["load_normal_pro1_kw"]
        * load["cm_pro1"]
    )


    # ========================================================
    # 7. LOAD FINALE DU PORTEFEUILLE
    # ========================================================

    load["load_final_total_kw"] = (
        load["load_final_res1_kw"]
        + load["load_final_pro1_kw"]
    )

    load["load_final_total_mw"] = (
        load["load_final_total_kw"]
        / 1000
    )

    return load
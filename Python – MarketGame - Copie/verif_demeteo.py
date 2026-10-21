"""
Vérification de la dé-météorisation du coefficient dynamique Enedis.

Question : une fois dé-météorisée, la load « à température normale »
réagit-elle encore à la météo RÉELLE de son année ?

Méthode, jour par jour, en saison de chauffe (T normale < 15 °C) :
  - x = écart de froid du jour = T normale − T réelle
        (> 0 : plus froid que la normale)
  - y = écart de consommation du jour, en %
  Les deux sont mesurés par rapport aux MÊMES jours de semaine des
  3 semaines avant et des 3 semaines après (J−21, J−14, J−7, J+7, J+14, J+21).
  Cela retire la saison (hiver plus chargé que l'automne) et le rythme
  de la semaine (samedi, dimanche) : il ne reste que l'effet de la météo du jour.

  On calcule la corrélation entre x et y, et la pente (% de conso par °C),
  AVANT et APRÈS dé-météorisation.
  Avant : corrélation nettement positive (la load contient la météo réelle).
  Après : corrélation proche de 0 (la météo a été retirée).

Lancement : python verif_demeteo.py   (même dossier que main_suite.py)
"""

import numpy as np
import pandas as pd

import config
from enedis_api import (
    charger_ou_actualiser, nettoyer_gradients, nettoyer_profil, nettoyer_temperatures,
    recuperer_gradients, recuperer_profil, recuperer_temperatures,
)
from load_2027 import _annee, demeteoriser_load
from load_model import calculer_load, calculer_puissance_moyenne, fusionner_load_normale

DECALAGES = [-21, -14, -7, 7, 14, 21]   # mêmes jours de semaine autour du jour J


def ecart_aux_voisins(serie):
    """Valeur du jour moins la moyenne des mêmes jours de semaine à ±1, 2, 3 semaines."""
    voisins = pd.concat([serie.shift(-d) for d in DECALAGES], axis=1)
    return serie - voisins.mean(axis=1, skipna=False)


def mesurer(load_annee, temperatures, annee):
    """Corrélation et pente entre écart de froid et écart de consommation."""
    j = load_annee.assign(date=load_annee["horodate"].dt.normalize())
    conso = j.groupby("date")[["load_normal_res1_kw", "load_normal_pro1_kw"]].mean().sum(axis=1)

    t = _annee(temperatures, annee)
    t = t.assign(date=t["horodate"].dt.normalize())
    tj = t.groupby("date")[["temperature_normale_lissee_degc", "temperature_realisee_lissee_degc"]].mean()

    df = pd.DataFrame({"conso": conso}).join(tj, how="inner").asfreq("D")
    df["froid"] = df["temperature_normale_lissee_degc"] - df["temperature_realisee_lissee_degc"]
    df["x"] = ecart_aux_voisins(df["froid"])
    df["y"] = ecart_aux_voisins(np.log(df["conso"])) * 100      # en % (écart logarithmique)
    df = df[df["temperature_normale_lissee_degc"] < config.SEUIL_CHAUFFAGE].dropna(subset=["x", "y"])

    corr = df["x"].corr(df["y"])
    pente = np.polyfit(df["x"], df["y"], 1)[0] if len(df) > 2 else np.nan
    return corr, pente, len(df)


def main():
    res1 = charger_ou_actualiser("res1.csv", lambda: recuperer_profil("RES1_BASE"), nettoyer_profil)
    pro1 = charger_ou_actualiser("pro1.csv", lambda: recuperer_profil("PRO1_BASE"), nettoyer_profil)
    temperatures = charger_ou_actualiser("temperatures.csv", recuperer_temperatures, nettoyer_temperatures)
    gradients = charger_ou_actualiser("gradients.csv", recuperer_gradients, nettoyer_gradients)

    res1["load_normal_kw"] = calculer_load(res1["coefficient_dynamique"], calculer_puissance_moyenne(
        config.NB_RES1, config.THETA_RES1, config.PUISSANCE_RES1))
    pro1["load_normal_kw"] = calculer_load(pro1["coefficient_dynamique"], calculer_puissance_moyenne(
        config.NB_PRO1, config.THETA_PRO1, config.PUISSANCE_PRO1))
    load_hist = fusionner_load_normale(res1, pro1)

    annees = sorted(set(config.ANNEE_PROFIL_REF) | set(config.ANNEES_SCENARIOS))
    lignes = []
    for annee in annees:
        brute = _annee(load_hist, annee)
        if brute.empty:
            continue
        print(f"Année {annee} :")
        corrigee = demeteoriser_load(brute, temperatures, gradients, config.SEUIL_CHAUFFAGE)
        c0, p0, n = mesurer(brute, temperatures, annee)
        c1, p1, _ = mesurer(corrigee, temperatures, annee)
        lignes.append({"année": annee, "jours testés": n,
                       "corrélation AVANT": round(c0, 2), "corrélation APRÈS": round(c1, 2),
                       "pente AVANT (%/°C)": round(p0, 2), "pente APRÈS (%/°C)": round(p1, 2)})

    print("\n--- VÉRIFICATION DE LA DÉ-MÉTÉORISATION (jours de chauffe) ---")
    print("x = écart de froid du jour (T normale − T réelle), y = écart de consommation du jour,")
    print("tous deux comparés aux mêmes jours de semaine des 3 semaines avant et après.")
    print(pd.DataFrame(lignes).set_index("année").to_string())
    print("\nLecture : AVANT, la consommation monte quand il fait plus froid que la normale "
          "(corrélation et pente positives).\nAPRÈS, il ne doit presque plus rien rester : "
          "la load ne contient plus la météo de son année.")


if __name__ == "__main__":
    main()

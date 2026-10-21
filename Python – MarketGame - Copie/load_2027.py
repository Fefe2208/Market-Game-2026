"""
Étape 1 et 2 du Market Game :
- load 2027 à température normale (forme de l'année de référence,
  alignée par jour de semaine + fériés 2027)
- loads 2027 avec la météo de chaque année historique
- tableaux récapitulatifs et graphiques
"""

import matplotlib.pyplot as plt
import pandas as pd

from calendrier import (
    construire_correspondance,
    correspondance_par_date,
    jours_feries_fr,
    remapper_serie,
)
from load_model import calculer_cm, construire_load_finale, fusionner_load_normale


PAS_HEURES = 0.5  # pas de 30 min


def _annee(df, annee):
    return df[df["horodate"].dt.year == annee].copy()


# ============================================================
# 1. BASE 2027 : LOAD NORMALE + GRADIENTS + TEMPERATURE NORMALE
# ============================================================

def construire_base_2027(
    res1,
    pro1,
    gradients,
    temperatures,
    annee_ref=2025,
    annee_cible=2027,
    demeteoriser=True,
    seuil_chauffage=15.0,
):
    """
    Construit la grille 2027 (30 min) contenant :
    - load normale RES1 / PRO1 / totale
    - gradients RES1 / PRO1
    - température normale

    annee_ref peut être :
    - une année (ex. 2025)          -> forme de cette seule année
    - une liste (ex. [2022, ..., 2025]) -> MOYENNE des années

    POURQUOI UNE MOYENNE ?
    ----------------------
    Les coefficients Enedis d'une année gardent la trace des jours
    réellement froids ou doux de cette année-là. Si on prend la forme
    d'UNE seule année (ex. 2025), ces jours se retrouvent alignés,
    jour pour jour, avec les prix de la même année dans le scénario
    "météo 2025". On crée alors une corrélation consommation-prix
    artificielle qui pénalise ce seul scénario (test fait : changer
    l'année de référence de 2025 à 2024 remonte le scénario 2025
    d'environ +1,6 €/MWh).

    En faisant la moyenne de plusieurs années, chacune remappée sur
    le calendrier 2027 (jour de semaine + fériés), la trace météo de
    chaque année est diluée : on obtient une forme "type", plus proche
    d'une vraie load à température normale, et aucun scénario n'est
    favorisé ou pénalisé.

    demeteoriser=True : chaque année est d'abord débarrassée de sa
    météo réelle (voir demeteoriser_load). demeteoriser=False redonne
    l'ancien calcul, utile pour la comparaison dans le rapport.
    """

    if isinstance(annee_ref, (list, tuple)):
        bases = []
        for annee in annee_ref:
            print(f"  Année de référence {annee} :")
            b = _base_une_annee(res1, pro1, gradients, temperatures,
                                annee, annee_cible, demeteoriser, seuil_chauffage)
            volume = b["load_normal_total_mw"].sum() * PAS_HEURES
            print(f"  Forme {annee} : {volume:,.0f} MWh sur 2027".replace(",", " "))
            bases.append(b)

        # Toutes les bases ont exactement la même grille 2027 :
        # on fait la moyenne colonne par colonne, ligne à ligne.
        colonnes = [
            "load_normal_res1_kw", "load_normal_pro1_kw",
            "gradient_res1", "gradient_pro1", "temperature_normale",
        ]
        base = bases[0][["horodate"]].copy()
        for col in colonnes:
            base[col] = sum(b[col].values for b in bases) / len(bases)

        base["load_normal_total_kw"] = (
            base["load_normal_res1_kw"] + base["load_normal_pro1_kw"]
        )
        base["load_normal_total_mw"] = base["load_normal_total_kw"] / 1000
        return base

    return _base_une_annee(res1, pro1, gradients, temperatures,
                           annee_ref, annee_cible, demeteoriser, seuil_chauffage)


# ------------------------------------------------------------
# DE-METEORISATION DU COEFFICIENT DYNAMIQUE
# ------------------------------------------------------------
#
# Constat (vérifié sur les données 2025) : le coefficient DYNAMIQUE
# d'Enedis est calculé à partir des courbes de charge réellement
# mesurées. Il contient donc la météo RÉELLE de son année
# (corrélation de 0,89 avec le froid réel de 2025, jour par jour).
#
# Si on l'utilise tel quel comme "load à température normale", puis
# qu'on applique la correction météo d'un scénario, une partie de la
# météo est comptée deux fois.
#
# Correction : on inverse le modèle de correction météo du cours.
#
#   load réelle  = load normale x CM(T réelle, T normale)
#   => load normale = load réelle / CM(T réelle de l'année, T normale)
#
# On calcule donc, pour l'année de référence, le CM avec SES
# températures réelles et on divise la load par ce CM.
# Test sur 2025 : la corrélation avec le froid réel passe de 0,71 à 0,11.


def demeteoriser_load(load_annee, temperatures, gradients, seuil_chauffage=15.0):
    """
    Retire l'effet de la météo réelle d'une load historique.
    Entrée / sortie : colonnes horodate, load_normal_res1_kw, load_normal_pro1_kw.
    """
    detail = construire_load_finale(
        load_annee, temperatures, gradients, seuil_chauffage
    )

    sortie = detail[["horodate"]].copy()
    sortie["load_normal_res1_kw"] = detail["load_normal_res1_kw"] / detail["cm_res1"]
    sortie["load_normal_pro1_kw"] = detail["load_normal_pro1_kw"] / detail["cm_pro1"]

    # Contrôle : part des pas de temps pour lesquels on avait la météo
    couverture = len(sortie) / max(len(load_annee), 1) * 100
    brut = (load_annee["load_normal_res1_kw"] + load_annee["load_normal_pro1_kw"]).mean()
    corrige = (sortie["load_normal_res1_kw"] + sortie["load_normal_pro1_kw"]).mean()
    print(f"    dé-météorisation : {couverture:.0f} % des pas de temps, "
          f"niveau moyen {(corrige / brut - 1) * 100:+.2f} %")

    return sortie


def _base_une_annee(
    res1,
    pro1,
    gradients,
    temperatures,
    annee_ref,
    annee_cible=2027,
    demeteoriser=True,
    seuil_chauffage=15.0,
):
    """Base 2027 construite à partir d'une seule année de référence."""

    corr_semaine = construire_correspondance(annee_ref, annee_cible)
    corr_date = correspondance_par_date(annee_ref, annee_cible)

    # --- Load de l'année de référence (coefficient dynamique)
    load_hist = fusionner_load_normale(res1, pro1)
    load_annee = _annee(load_hist, annee_ref)

    # --- On retire la météo réelle de cette année (voir plus haut)
    if demeteoriser:
        load_annee = demeteoriser_load(
            load_annee, temperatures, gradients, seuil_chauffage
        )

    # --- Load normale : alignée par jour de semaine
    base = remapper_serie(
        load_annee,
        ["load_normal_res1_kw", "load_normal_pro1_kw"],
        corr_semaine,
        annee_cible,
    )

    # --- Gradients : même alignement que les profils
    grad = gradients.copy()
    for col in ["res1_base", "pro1_base"]:
        grad[col] = pd.to_numeric(grad[col], errors="coerce")

    grad_2027 = remapper_serie(
        _annee(grad, annee_ref),
        ["res1_base", "pro1_base"],
        corr_semaine,
        annee_cible,
    )
    base["gradient_res1"] = grad_2027["res1_base"].values
    base["gradient_pro1"] = grad_2027["pro1_base"].values

    # --- Température normale : purement saisonnière -> par date
    temp_norm = remapper_serie(
        _annee(temperatures, annee_ref),
        ["temperature_normale_lissee_degc"],
        corr_date,
        annee_cible,
    )
    base["temperature_normale"] = (
        temp_norm["temperature_normale_lissee_degc"].values
    )

    base["load_normal_total_kw"] = (
        base["load_normal_res1_kw"] + base["load_normal_pro1_kw"]
    )
    base["load_normal_total_mw"] = base["load_normal_total_kw"] / 1000

    return base


# ============================================================
# 2. LOADS 2027 PAR SCENARIO METEO
# ============================================================

def construire_load_scenario(
    base_2027,
    temperatures,
    annee_source,
    annee_cible=2027,
    seuil_chauffage=15.0,
):
    """
    Applique la météo de l'année source à la base 2027.

    T_reelle_2027 = T_normale_2027 + anomalie(année source)

    L'anomalie est remappée avec la MEME correspondance jour-de-semaine
    que celle qui sera utilisée pour les prix du scénario.
    """

    corr = construire_correspondance(annee_source, annee_cible)

    temp = _annee(temperatures, annee_source)
    temp["anomalie_temperature"] = (
        temp["temperature_realisee_lissee_degc"]
        - temp["temperature_normale_lissee_degc"]
    )

    anom = remapper_serie(
        temp, ["anomalie_temperature"], corr, annee_cible
    )

    df = base_2027.copy()
    df["date_source"] = anom["date_source"].values
    df["anomalie_temperature"] = anom["anomalie_temperature"].values
    df["temperature_reelle"] = (
        df["temperature_normale"] + df["anomalie_temperature"]
    )

    df["cm_res1"] = calculer_cm(
        df["temperature_reelle"], df["temperature_normale"],
        df["gradient_res1"], seuil_chauffage,
    ).values
    df["cm_pro1"] = calculer_cm(
        df["temperature_reelle"], df["temperature_normale"],
        df["gradient_pro1"], seuil_chauffage,
    ).values

    df["load_final_res1_kw"] = df["load_normal_res1_kw"] * df["cm_res1"]
    df["load_final_pro1_kw"] = df["load_normal_pro1_kw"] * df["cm_pro1"]
    df["load_final_total_mw"] = (
        df["load_final_res1_kw"] + df["load_final_pro1_kw"]
    ) / 1000

    df["annee_scenario"] = annee_source

    return df


def construire_loads_scenarios(
    base_2027, temperatures, annees, annee_cible=2027, seuil_chauffage=15.0
):
    scenarios = {}
    for annee in annees:
        print(f"Load 2027 avec météo {annee}...")
        scenarios[annee] = construire_load_scenario(
            base_2027, temperatures, annee, annee_cible, seuil_chauffage
        )
    return scenarios


# ============================================================
# 3. RECAPITULATIFS
# ============================================================

def masque_peak(horodate):
    """
    Heures Peak EEX : lundi-vendredi, 08:00-20:00,
    jours fériés INCLUS (définition produit EEX).
    """
    return (horodate.dt.weekday < 5) & (horodate.dt.hour >= 8) & (
        horodate.dt.hour < 20
    )


def _stats(horodate, mw):
    peak = masque_peak(horodate)
    return {
        "volume_MWh": mw.sum() * PAS_HEURES,
        "volume_peak_MWh": mw[peak].sum() * PAS_HEURES,
        "volume_offpeak_MWh": mw[~peak].sum() * PAS_HEURES,
        "MW_moyen": mw.mean(),
        "MW_max": mw.max(),
        "MW_min": mw.min(),
    }


def tableau_recap(base_2027, scenarios):
    lignes = [
        {"scenario": "Normale",
         **_stats(base_2027["horodate"], base_2027["load_normal_total_mw"])}
    ]
    for annee, df in scenarios.items():
        lignes.append(
            {"scenario": f"Météo {annee}",
             **_stats(df["horodate"], df["load_final_total_mw"])}
        )

    recap = pd.DataFrame(lignes).set_index("scenario")
    v_norm = recap.loc["Normale", "volume_MWh"]
    recap["anomalie_volume_%"] = (recap["volume_MWh"] / v_norm - 1) * 100
    recap["part_peak_%"] = recap["volume_peak_MWh"] / recap["volume_MWh"] * 100
    return recap


def volumes_mensuels(base_2027, scenarios):
    """Volumes mensuels en MWh (normale + scénarios)."""
    out = pd.DataFrame(index=range(1, 13))
    mois = base_2027["horodate"].dt.month
    out["Normale"] = (
        base_2027.groupby(mois)["load_normal_total_mw"].sum() * PAS_HEURES
    )
    for annee, df in scenarios.items():
        out[f"Météo {annee}"] = (
            df.groupby(df["horodate"].dt.month)["load_final_total_mw"].sum()
            * PAS_HEURES
        )
    out.index.name = "mois"
    return out


def load_horaire(df, colonne):
    """Passage 30 min -> horaire (MW moyen sur l'heure)."""
    return (
        df.set_index("horodate")[colonne]
        .resample("h")
        .mean()
        .reset_index()
    )


# ============================================================
# 4. GRAPHIQUES
# ============================================================

def tracer_loads_2027(base_2027, scenarios, debut=None, fin=None):
    """
    Sans dates : moyenne journalière sur l'année.
    Avec dates : courbe 30 min sur la période.
    """
    plt.figure(figsize=(14, 6))

    def prep(df, col):
        s = df.set_index("horodate")[col]
        if debut is None:
            return s.resample("D").mean()
        return s.loc[debut:fin]

    plt.plot(prep(base_2027, "load_normal_total_mw"),
             color="black", linewidth=2, label="Normale")
    for annee, df in scenarios.items():
        plt.plot(prep(df, "load_final_total_mw"),
                 linewidth=1, label=f"Météo {annee}")

    titre = "Load 2027 par scénario météo"
    titre += " (moyenne journalière)" if debut is None else f" — {debut} → {fin}"
    plt.title(titre)
    plt.ylabel("Puissance (MW)")
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()


def controle_calendrier(base_2027, annee_cible=2027):
    """Moyenne MW par type de jour : les fériés doivent ressembler aux dimanches."""
    feries = set(jours_feries_fr(annee_cible).values())
    d = base_2027["horodate"].dt.date
    wd = base_2027["horodate"].dt.weekday
    type_j = pd.Series("ouvre", index=base_2027.index)
    type_j[wd == 5] = "samedi"
    type_j[wd == 6] = "dimanche"
    type_j[d.isin(feries)] = "ferie"
    return base_2027.groupby(type_j)["load_normal_total_mw"].mean().round(1)

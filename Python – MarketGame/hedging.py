"""
Étape 5 du Market Game : stratégies de couverture.

PARTIE 1 (ce fichier pour l'instant) :
découper la load 2027 à température normale en produits EEX,
c'est-à-dire répondre à la question :

    "Pour couvrir 100 % de ma consommation normale,
     combien de MW dois-je acheter sur chaque produit ?"

Produits utilisés (cotés au 22/09/2026) :
- Base : livre la même puissance 24h/24, 7j/7
- Peak : livre en plus de 08:00 à 20:00, du lundi au vendredi
         (jours fériés inclus, définition EEX)
- sur 4 trimestres : Q1, Q2, Q3, Q4 2027
"""

import matplotlib.pyplot as plt
import pandas as pd

from load_2027 import masque_peak, PAS_HEURES


# ============================================================
# 1. DECOUPAGE DE LA LOAD NORMALE EN MW BASE + PEAK PAR TRIMESTRE
# ============================================================
#
# Principe, pour chaque trimestre :
#
#   - En heures OFF-PEAK (nuits, week-ends), seul le produit Base livre.
#     -> on achète en Base la puissance MOYENNE consommée en off-peak.
#
#   - En heures PEAK, on reçoit le Base + le Peak.
#     -> on achète en Peak le complément pour atteindre
#        la puissance MOYENNE consommée en peak.
#
#   Base_MW = load moyenne sur les heures off-peak du trimestre
#   Peak_MW = load moyenne sur les heures peak du trimestre - Base_MW
#
# Résultat : sur chaque bloc (trimestre x peak/off-peak), l'énergie
# achetée est EXACTEMENT égale à l'énergie consommée à température
# normale. C'est notre "100 %".
#
# Ce qui reste non couvert : les écarts heure par heure AUTOUR de ces
# moyennes (ex. pic de 19h, creux de 4h du matin). C'est le risque de
# FORME, qui sera acheté ou revendu au spot.
#
# Cas particulier : si la load moyenne en peak est plus faible qu'en
# off-peak (Peak_MW négatif), on n'achète pas de Peak et on couvre le
# trimestre avec du Base seul, égal à la load moyenne du trimestre.


def decouper_load_en_produits(base_2027, colonne="load_normal_total_mw"):
    """
    Retourne un tableau, une ligne par trimestre :
    MW moyens peak / off-peak, MW à acheter en Base et en Peak,
    et un contrôle énergie couverte / énergie consommée.
    """

    df = base_2027[["horodate", colonne]].copy()
    df["trimestre"] = df["horodate"].dt.quarter
    df["peak"] = masque_peak(df["horodate"])

    lignes = []

    for t in range(1, 5):
        dans_t = df["trimestre"] == t
        en_peak = dans_t & df["peak"]
        en_off = dans_t & ~df["peak"]

        mw_peak_moyen = df.loc[en_peak, colonne].mean()
        mw_off_moyen = df.loc[en_off, colonne].mean()

        # Nombre d'heures du bloc (pas de 30 min -> x 0,5)
        h_peak = en_peak.sum() * PAS_HEURES
        h_off = en_off.sum() * PAS_HEURES
        h_tot = h_peak + h_off

        if mw_peak_moyen >= mw_off_moyen:
            base_mw = mw_off_moyen
            peak_mw = mw_peak_moyen - mw_off_moyen
        else:
            # Cas particulier : pas de Peak, Base = moyenne du trimestre
            base_mw = df.loc[dans_t, colonne].mean()
            peak_mw = 0.0

        # Contrôle : énergie livrée par les produits vs énergie consommée
        energie_produits = base_mw * h_tot + peak_mw * h_peak
        energie_load = df.loc[dans_t, colonne].sum() * PAS_HEURES

        lignes.append(
            {
                "trimestre": f"Q{t}",
                "MW_moyen_offpeak": round(mw_off_moyen, 2),
                "MW_moyen_peak": round(mw_peak_moyen, 2),
                "Base_MW": round(base_mw, 2),
                "Peak_MW": round(peak_mw, 2),
                "heures_peak": h_peak,
                "heures_totales": h_tot,
                "energie_load_MWh": round(energie_load, 0),
                "energie_produits_MWh": round(energie_produits, 0),
                "couverture_%": round(energie_produits / energie_load * 100, 2),
            }
        )

    return pd.DataFrame(lignes).set_index("trimestre")


# ============================================================
# 2. PRESENTATION EN "CAL + COMPLEMENTS TRIMESTRIELS"
# ============================================================
#
# Les guidelines demandent d'exprimer la couverture "en MW par produit"
# (Cal-27, Quarters). On présente donc le même 100 % comme :
#
#   - un bloc Cal-27 = la puissance commune à toute l'année
#     (le plus petit des 4 trimestres)
#   - plus un complément par trimestre (ce qui dépasse le Cal)
#
# C'est l'image de la slide 8 de la séance 3 : bande Calendar en bas,
# trimestres par-dessus.
#
# Remarque : au 22/09, le Cal-27 vaut exactement la moyenne pondérée
# des 4 trimestres (vérifié : 83,31 en Base, 95,59 en Peak). Acheter
# "Cal + compléments" ou "4 trimestres" coûte donc la même chose :
# c'est seulement une façon de présenter les achats.


def presenter_cal_plus_trimestres(produits):
    """
    Transforme les MW par trimestre en MW par produit EEX :
    Cal-27 Base, Cal-27 Peak, puis compléments Q1..Q4 Base et Peak.
    """

    cal_base = produits["Base_MW"].min()
    cal_peak = produits["Peak_MW"].min()

    lignes = [
        {"produit": "Cal-27 Base", "MW": round(cal_base, 2)},
        {"produit": "Cal-27 Peak", "MW": round(cal_peak, 2)},
    ]

    for t in produits.index:
        lignes.append(
            {
                "produit": f"{t}-27 Base (complément)",
                "MW": round(produits.loc[t, "Base_MW"] - cal_base, 2),
            }
        )
    for t in produits.index:
        lignes.append(
            {
                "produit": f"{t}-27 Peak (complément)",
                "MW": round(produits.loc[t, "Peak_MW"] - cal_peak, 2),
            }
        )

    return pd.DataFrame(lignes).set_index("produit")


# ============================================================
# 3. GRAPHIQUE : LOAD NORMALE vs COUVERTURE 100 %
# ============================================================

def profil_couverture(horodate, produits, ratio=1.0):
    """
    Puissance livrée (MW) à chaque pas de temps par les produits,
    multipliée par un ratio de couverture (1.0 = 100 %).
    """
    trimestre = "Q" + horodate.dt.quarter.astype(str)
    peak = masque_peak(horodate)

    base_mw = trimestre.map(produits["Base_MW"])
    peak_mw = trimestre.map(produits["Peak_MW"])

    return ratio * (base_mw + peak_mw * peak)


def tracer_couverture(base_2027, produits, debut, fin):
    """Compare la load normale et la couverture 100 % sur une période."""

    df = base_2027.set_index("horodate")
    extrait = base_2027[
        (base_2027["horodate"] >= debut) & (base_2027["horodate"] <= fin)
    ]
    couverture = profil_couverture(extrait["horodate"], produits)

    plt.figure(figsize=(14, 6))
    plt.plot(extrait["horodate"], extrait["load_normal_total_mw"],
             label="Load normale 2027")
    plt.step(extrait["horodate"], couverture, where="post",
             linewidth=2, label="Couverture 100 % (Base + Peak)")
    plt.ylabel("Puissance (MW)")
    plt.title(f"Load normale vs couverture 100 % — {debut} → {fin}")
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()


# ============================================================
# 4. DEFINITION DES STRATEGIES
# ============================================================
#
# Une stratégie = une liste d'achats. Chaque achat est un triplet :
#
#     (date, type d'achat, ratio)
#
#   date  : "T1" (22/09/2026, figé) ou "T2" (01/12/2026, prévu)
#
#   type d'achat :
#     "forme"         -> trimestres Base + Peak, qui suivent la forme de la load
#                        (= Cal + compléments trimestriels, même coût)
#                        ratio = dictionnaire {trimestre: %}
#     "cal_base"      -> un bloc plat Cal-27 Base (même MW toute l'année)
#                        ratio = % de la puissance moyenne annuelle
#     "cal_base_peak" -> Cal-27 Base + Cal-27 Peak : forme jour/nuit,
#                        mais PAS de forme saisonnière
#                        ratio = % de la load annuelle
#     "complement"    -> trimestres achetés pour compléter les achats
#                        déjà faits jusqu'à un total donné (avec la forme)
#                        ratio = % total visé
#
# Les ratios sont toujours exprimés sur la load à température NORMALE
# (le "100 %" calculé par decouper_load_en_produits).


def uniforme(ratio):
    """Même ratio pour les 4 trimestres."""
    return {1: ratio, 2: ratio, 3: ratio, 4: ratio}


STRATEGIES = {
    # STRATEGIE DE REFERENCE "BASSE" : aucune couverture.
    # Tout le volume est acheté au spot. Sert de point zéro pour mesurer
    # ce que coûte et ce que rapporte la protection.
    "S0 Sans couverture": [
        ("T1", "forme", uniforme(0.0)),
    ],
    # Acheter tôt : 50 % à T1, 40 % à T2
    "S1 Front-loaded": [
        ("T1", "forme", uniforme(0.50)),
        ("T2", "forme", uniforme(0.40)),
    ],
    # Même total que S1, mais acheté plus tard : test du "timing"
    "S2 Back-loaded": [
        ("T1", "forme", uniforme(0.30)),
        ("T2", "forme", uniforme(0.60)),
    ],
    # Stratégie risquée : 40 % du volume reste au spot
    "S3 Peu couverte": [
        ("T1", "forme", uniforme(0.30)),
        ("T2", "forme", uniforme(0.30)),
    ],
    # Plus de couverture en hiver (Q1, Q4), là où est le risque prix-volume
    "S4 Saisonnière": [
        ("T1", "forme", {1: 0.60, 2: 0.40, 3: 0.40, 4: 0.60}),
        ("T2", "forme", uniforme(0.40)),
    ],
    # Stratégie naïve : un seul bloc plat Cal-27 Base
    "S5 Cal plat": [
        ("T1", "cal_base", 0.40),
        ("T2", "cal_base", 0.40),
    ],
    # Cascade : d'abord la bande annuelle (Cal Base + Peak), puis la forme
    # saisonnière avec les trimestres à T2
    "S6 Cascade": [
        ("T1", "cal_base_peak", 0.50),
        ("T2", "complement", 0.90),
    ],
    # STRATEGIE DE REFERENCE "HAUTE" : couverture maximale autorisée,
    # 100 % du volume normal (50 % à T1 + 50 % à T2), avec la forme.
    # Seul reste au spot le résiduel que les produits ne peuvent pas
    # couvrir (forme horaire, écarts de volume liés à la météo).
    "S7 Couverture 100 %": [
        ("T1", "forme", uniforme(0.50)),
        ("T2", "forme", uniforme(0.50)),
    ],
}


# ============================================================
# 5. TRADUCTION D'UNE STRATEGIE EN ACHATS (MW PAR PRODUIT)
# ============================================================

def construire_achats(strategie, produits, base_2027,
                      colonne="load_normal_total_mw"):
    """
    Transforme une stratégie en liste d'achats concrets.

    Résultat : un tableau, une ligne par (date, produit, trimestre, composante)
      - produit    : "Cal-27" ou "Q1-27"... (pour le Cal, une ligne par trimestre
                     avec le même MW, ce qui simplifie les calculs)
      - composante : "Base" ou "Peak"
      - MW         : puissance achetée (négatif = revente)
    """

    # Moyennes ANNUELLES de la load normale (utiles pour les produits Cal)
    peak = masque_peak(base_2027["horodate"])
    mw_moyen_annuel = base_2027[colonne].mean()
    mw_peak_annuel = base_2027.loc[peak, colonne].mean()
    mw_off_annuel = base_2027.loc[~peak, colonne].mean()

    lignes = []

    # Ce qui a déjà été acheté, par trimestre (pour le type "complement")
    deja_base = {q: 0.0 for q in range(1, 5)}
    deja_peak = {q: 0.0 for q in range(1, 5)}

    for date, type_achat, ratio in strategie:

        for q in range(1, 5):
            cle = f"Q{q}"

            if type_achat == "forme":
                produit = f"Q{q}-27"
                mw_base = ratio[q] * produits.loc[cle, "Base_MW"]
                mw_peak = ratio[q] * produits.loc[cle, "Peak_MW"]

            elif type_achat == "cal_base":
                produit = "Cal-27"
                mw_base = ratio * mw_moyen_annuel
                mw_peak = 0.0

            elif type_achat == "cal_base_peak":
                produit = "Cal-27"
                mw_base = ratio * mw_off_annuel
                mw_peak = ratio * (mw_peak_annuel - mw_off_annuel)

            elif type_achat == "complement":
                produit = f"Q{q}-27"
                mw_base = ratio * produits.loc[cle, "Base_MW"] - deja_base[q]
                mw_peak = ratio * produits.loc[cle, "Peak_MW"] - deja_peak[q]

            else:
                raise ValueError(f"Type d'achat inconnu : {type_achat}")

            deja_base[q] += mw_base
            deja_peak[q] += mw_peak

            lignes.append({"date": date, "produit": produit, "trimestre": q,
                           "composante": "Base", "MW": mw_base})
            if mw_peak != 0:
                lignes.append({"date": date, "produit": produit, "trimestre": q,
                               "composante": "Peak", "MW": mw_peak})

    return pd.DataFrame(lignes)


def tableau_mw_par_produit(achats):
    """
    MW achetés par produit et par date, présentés comme sur EEX
    (le Cal n'apparaît qu'une fois, pas une fois par trimestre).
    """
    t = (
        achats.groupby(["date", "produit", "composante"])["MW"]
        .first()
        .round(2)
        .reset_index()
    )
    return t


# ============================================================
# 6. CONTROLES : TAUX DE COUVERTURE ET COUT DES ACHATS T1
# ============================================================

def taux_de_couverture(achats, produits):
    """
    Énergie couverte / énergie normale, par trimestre et sur l'année,
    au total et pour la part T1.
    Règle des guidelines : jamais plus de 100 %.
    """

    h_tot = {int(i[1]): produits.loc[i, "heures_totales"] for i in produits.index}
    h_peak = {int(i[1]): produits.loc[i, "heures_peak"] for i in produits.index}
    e_load = {int(i[1]): produits.loc[i, "energie_load_MWh"] for i in produits.index}

    a = achats.copy()
    a["heures"] = [
        h_tot[q] if c == "Base" else h_peak[q]
        for q, c in zip(a["trimestre"], a["composante"])
    ]
    a["energie_MWh"] = a["MW"] * a["heures"]

    resultat = {}
    for q in range(1, 5):
        e = a[a["trimestre"] == q]["energie_MWh"].sum()
        resultat[f"Q{q}_%"] = round(e / e_load[q] * 100, 1)

    e_totale = a["energie_MWh"].sum()
    e_t1 = a[a["date"] == "T1"]["energie_MWh"].sum()
    e_annee = sum(e_load.values())

    resultat["T1_%"] = round(e_t1 / e_annee * 100, 1)
    resultat["Total_%"] = round(e_totale / e_annee * 100, 1)

    if max(resultat[f"Q{q}_%"] for q in range(1, 5)) > 100.0:
        print("  ATTENTION : un trimestre dépasse 100 % de couverture !")

    return resultat


def cout_achats_t1(achats, produits, prix_t1):
    """
    Coût des achats faits à T1, aux prix EEX du 22/09/2026.
    prix_t1 = {"Cal-27": {"Base": 83.31, "Peak": 95.59},
               "Q1-27": {"Base": 139.00, "Peak": 171.94}, ...}
    """

    h_tot = {int(i[1]): produits.loc[i, "heures_totales"] for i in produits.index}
    h_peak = {int(i[1]): produits.loc[i, "heures_peak"] for i in produits.index}

    a = achats[achats["date"] == "T1"].copy()
    a["heures"] = [
        h_tot[q] if c == "Base" else h_peak[q]
        for q, c in zip(a["trimestre"], a["composante"])
    ]
    a["prix"] = [prix_t1[p][c] for p, c in zip(a["produit"], a["composante"])]
    a["energie_MWh"] = a["MW"] * a["heures"]
    a["cout_EUR"] = a["energie_MWh"] * a["prix"]

    energie = a["energie_MWh"].sum()
    cout = a["cout_EUR"].sum()

    return {
        "energie_T1_MWh": round(energie, 0),
        "cout_T1_MEUR": round(cout / 1e6, 2),
        # (pas de prix moyen si rien n'est acheté à T1, ex. S0)
        "prix_moyen_T1_EUR_MWh": round(cout / energie, 2) if energie > 0 else None,
    }


def prix_t1_depuis_config(config):
    """Construit le dictionnaire des prix T1 à partir de config.py."""
    prix = {"Cal-27": {"Base": config.FORWARD_T1_CAL_BASE,
                       "Peak": config.FORWARD_T1_CAL_PEAK}}
    for q in range(1, 5):
        f = config.FORWARDS_T1[f"Q{q}"]
        prix[f"Q{q}-27"] = {"Base": f["base"], "Peak": f["peak"]}
    return prix

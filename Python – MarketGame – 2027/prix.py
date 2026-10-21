"""
Étapes 3 et 4 du Market Game (+ anticipation du forward T2) :
- chargement des prix day-ahead ENTSO-E (France)
- anomalies prix / volume et pente b
- scénarios spot 2027 = niveau (ancré sur le forward) x forme historique
- forward anticipé à T2 (méthode alpha) + plausibilité
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calendrier import construire_correspondance, jours_feries_fr, type_jour, remapper_serie


# ============================================================
# 1. CHARGEMENT ENTSO-E
# ============================================================

def charger_prix_entsoe(chemins, tz="Europe/Paris"):
    """
    Lit un ou plusieurs exports CSV ENTSO-E "Day-ahead prices" (France)
    et renvoie une série HORAIRE : colonnes horodate (tz), prix.

    - Colonne de temps : celle qui contient "MTU" ("01/01/2024 00:00 - 01/01/2024 01:00")
    - Colonne de prix : celle qui contient "price"
    - Les données 15 min (depuis le 01/10/2025) sont moyennées à l'heure.

    Le format des exports change selon les versions de la plateforme :
    si la lecture échoue, afficher df.columns et adapter les deux noms.
    """

    if isinstance(chemins, (str, Path)):
        chemins = [chemins]

    morceaux = []

    for chemin in chemins:
        df = pd.read_csv(chemin)

        col_temps = next(c for c in df.columns if "MTU" in c)
        col_prix = next(c for c in df.columns if "price" in c.lower())

        debut = (
            df[col_temps].astype(str)
            .str.split(" - ").str[0]
            .str.replace(r"\s*\(.*\)", "", regex=True)
            .str.strip()
        )

        h = pd.to_datetime(debut, dayfirst=True)
        h = h.dt.tz_localize(tz, ambiguous="infer", nonexistent="shift_forward")

        morceaux.append(
            pd.DataFrame(
                {
                    "horodate": h,
                    "prix": pd.to_numeric(df[col_prix], errors="coerce"),
                }
            )
        )

    prix = pd.concat(morceaux).dropna()
    prix = prix.drop_duplicates("horodate").sort_values("horodate")

    prix = (
        prix.set_index("horodate")["prix"]
        .resample("h")
        .mean()
        .interpolate(limit=3)
        .reset_index()
    )

    return prix


def controle_prix(prix):
    """Nombre d'heures, moyenne et trous par année."""
    g = prix.groupby(prix["horodate"].dt.year)["prix"]
    return pd.DataFrame(
        {
            "nb_heures": g.size(),
            "manquants": g.apply(lambda s: s.isna().sum()),
            "moyenne_EUR_MWh": g.mean().round(1),
            "min": g.min().round(1),
            "max": g.max().round(1),
        }
    )


# ============================================================
# 2. ANOMALIES PRIX / VOLUME (données historiques)
# ============================================================

def anomalies_journalieres(load_finale_hist, prix):
    """
    load_finale_hist : sortie de construire_load_finale (dates historiques),
                       avec load_normal_total_mw et load_final_total_mw.

    Volume anomaly x = (réel - normal) / normal            (par jour)
    Price  anomaly y = (prix jour - moyenne réf) / moyenne réf
      où la référence = moyenne du même mois ET même type de jour
      (ouvré / samedi / dimanche-férié), comme recommandé en cours.
    """

    lf = load_finale_hist.copy()
    lf["date"] = lf["horodate"].dt.date
    vol = lf.groupby("date")[
        ["load_normal_total_mw", "load_final_total_mw"]
    ].mean()
    vol["x"] = vol["load_final_total_mw"] / vol["load_normal_total_mw"] - 1

    p = prix.copy()
    p["date"] = p["horodate"].dt.date
    pj = p.groupby("date")["prix"].mean().to_frame("prix_jour")

    df = vol[["x"]].join(pj, how="inner").reset_index()
    df["annee"] = [d.year for d in df["date"]]
    df["mois"] = [d.month for d in df["date"]]

    feries = {
        a: set(jours_feries_fr(a).values()) for a in df["annee"].unique()
    }
    df["type_jour"] = [
        type_jour(d, feries[d.year]) for d in df["date"]
    ]

    ref = df.groupby(["annee", "mois", "type_jour"])["prix_jour"].transform("mean")
    df["prix_ref"] = ref
    df["y"] = df["prix_jour"] / ref - 1

    return df


def regression_prix_volume(
    anomalies,
    mois=(11, 12, 1, 2, 3),
    annees=None,
):
    """
    Régression y = a + b x (MCO) sur les jours d'hiver.

    Renvoie b, a, R², n, et b par année (pour tester la stabilité).
    Par construction mean(y) ~ 0 dans chaque groupe, donc a ~ 0 :
    b = Cov(x,y) / Var(x) comme dans le cours.
    """

    d = anomalies[anomalies["mois"].isin(mois)]
    if annees is not None:
        d = d[d["annee"].isin(annees)]
    d = d.dropna(subset=["x", "y"])

    def ajuster(sous):
        x, y = sous["x"].values, sous["y"].values
        b = np.cov(x, y, bias=True)[0, 1] / np.var(x)
        a = y.mean() - b * x.mean()
        r2 = np.corrcoef(x, y)[0, 1] ** 2
        return b, a, r2, len(sous)

    b, a, r2, n = ajuster(d)

    par_annee = {
        int(an): round(float(ajuster(s)[0]), 2)
        for an, s in d.groupby("annee")
        if len(s) > 20
    }

    return {"b": b, "a": a, "r2": r2, "n": n, "b_par_annee": par_annee}


def tracer_regression(anomalies, resultat, mois=(11, 12, 1, 2, 3)):
    d = anomalies[anomalies["mois"].isin(mois)]
    plt.figure(figsize=(9, 6))
    for annee, s in d.groupby("annee"):
        plt.scatter(s["x"] * 100, s["y"] * 100, s=12, alpha=0.6,
                    label=f"Hiver {annee}")
    xs = np.linspace(d["x"].min(), d["x"].max(), 50)
    plt.plot(xs * 100, (resultat["a"] + resultat["b"] * xs) * 100,
             "r--", linewidth=2,
             label=f"b = {resultat['b']:.2f}  (R² = {resultat['r2']:.2f})")
    plt.axhline(0, color="grey", linewidth=0.5)
    plt.axvline(0, color="grey", linewidth=0.5)
    plt.xlabel("Anomalie de volume (%)")
    plt.ylabel("Anomalie de prix (%)")
    plt.title("Lien prix-volume sur anomalies (jours d'hiver)")
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()


# ============================================================
# 3. SCENARIOS SPOT 2027
# ============================================================

def niveau_spot_2027(forward_t1, b, anomalie_volume_annuelle, prime_risque=0.03):
    """Level = F_T1 x (1 - prime) x (1 + b x anomalie volume annuelle)."""
    return forward_t1 * (1 - prime_risque) * (1 + b * anomalie_volume_annuelle)


def construire_spot_2027(prix, annee_source, niveau, annee_cible=2027):
    """
    Spot 2027 horaire = niveau x forme(année source)

    La forme est remappée avec la MEME correspondance jour-de-semaine
    que la météo du scénario -> corrélation prix-volume conservée.
    Elle est renormalisée à une moyenne de 1 après remapping.
    Le niveau historique de l'année n'est jamais réutilisé.
    """

    corr = construire_correspondance(annee_source, annee_cible)
    hist = prix[prix["horodate"].dt.year == annee_source]

    spot = remapper_serie(hist, ["prix"], corr, annee_cible, freq="h")
    spot["forme"] = spot["prix"] / spot["prix"].mean()
    spot["spot"] = niveau * spot["forme"]
    spot["annee_scenario"] = annee_source

    return spot[["horodate", "date_source", "forme", "spot", "annee_scenario"]]


# ============================================================
# 4. FORWARD ANTICIPE A T2 (méthode alpha)
# ============================================================

def forward_t2(forward_t1, niveau, alpha):
    """F_T2 = F_T1 + alpha x (niveau scénario - F_T1)."""
    return forward_t1 + alpha * (niveau - forward_t1)


def tableau_scenarios_prix(
    recap_load,
    forward_t1,
    b,
    alpha,
    prime_risque=0.03,
    probabilites=None,
    volatilite=0.20,
    jours_t1_t2=70,
    recentrer=True,
):
    """
    Une ligne par scénario : anomalie volume, niveau spot 2027,
    forward anticipé à T2, probabilité.
    + écart-type de plausibilité CRE : F x vol x sqrt(jours/365).

    CORRECTION 1 : RECENTRAGE DES ANOMALIES (recentrer=True)
    ---------------------------------------------------------
    Problème : les 4 années historiques (2022-2025) ont toutes été
    plus douces que la "normale" Enedis. Leurs anomalies de volume
    sont donc toutes négatives (-0,8 % à -1,7 %).
    Avec la formule du cours, les 4 niveaux de prix tombent alors
    TOUS sous le forward : le modèle dirait que le marché se trompe
    toujours à la hausse, ce qui n'est pas crédible.

    Explication : le forward du 22/09 intègre déjà le climat des
    hivers récents. Le marché n'attend pas un hiver "normale Enedis",
    il attend un hiver "comme les dernières années".

    Solution : on mesure l'anomalie de chaque scénario par rapport à
    la MOYENNE des scénarios, et non plus par rapport à la normale :

        anomalie recentrée = anomalie du scénario - moyenne des anomalies

    -> la moyenne des anomalies recentrées vaut 0
    -> les niveaux de prix se répartissent AUTOUR de F_T1 x (1 - prime)
    -> on garde l'écart météo ENTRE les années (une année plus froide
       que les autres reste plus chère), c'est ce qui fait le risque.

    recentrer=False redonne la méthode du cours "brute",
    utile pour la comparaison dans le rapport.
    """

    scen = [s for s in recap_load.index if s != "Normale"]

    # Anomalies de volume brutes (par rapport à la normale Enedis), en fraction
    anomalies = {
        s: recap_load.loc[s, "anomalie_volume_%"] / 100 for s in scen
    }

    # Moyenne des anomalies des scénarios (≈ -1,26 % avec 2022-2025)
    anomalie_moyenne = np.mean(list(anomalies.values()))

    if recentrer:
        print(
            f"Recentrage : anomalie moyenne des scénarios = "
            f"{anomalie_moyenne * 100:.2f} % (retirée de chaque scénario)"
        )

    lignes = []

    for s in scen:
        anom_brute = anomalies[s]

        # Anomalie utilisée pour le niveau de prix
        if recentrer:
            anom = anom_brute - anomalie_moyenne
        else:
            anom = anom_brute

        # Niveau = F_T1 x (1 - prime) x (1 + b x anomalie)   (slide 17)
        niv = niveau_spot_2027(forward_t1, b, anom, prime_risque)

        lignes.append(
            {
                "scenario": s,
                "anomalie_brute_%": round(anom_brute * 100, 2),
                "anomalie_utilisee_%": round(anom * 100, 2),
                "niveau_spot_2027": round(niv, 2),
                "forward_T2_anticipe": round(forward_t2(forward_t1, niv, alpha), 2),
                "probabilite": (probabilites or {}).get(s, 1 / len(scen)),
            }
        )

    tab = pd.DataFrame(lignes).set_index("scenario")

    # Contrôle de plausibilité CRE (guidelines §3.3) :
    # 1 écart-type = forward x 20 % x racine(70 jours / 365)
    sigma = forward_t1 * volatilite * np.sqrt(jours_t1_t2 / 365)
    tab["ecart_vs_F_T1"] = (tab["forward_T2_anticipe"] - forward_t1).round(2)
    tab["dans_1_sigma"] = tab["ecart_vs_F_T1"].abs() <= sigma

    print(f"Plausibilité : 1 écart-type sur {jours_t1_t2} j = ±{sigma:.1f} €/MWh")
    return tab


def tracer_spots_2027(spots, forward_t1=None):
    plt.figure(figsize=(14, 6))
    for annee, s in spots.items():
        j = s.set_index("horodate")["spot"].resample("D").mean()
        plt.plot(j, linewidth=1, label=f"Spot 2027, scénario {annee}")
    if forward_t1 is not None:
        plt.axhline(forward_t1, color="black", linestyle="--",
                    label=f"Forward Cal-27 T1 ({forward_t1} €/MWh)")
    plt.ylabel("€/MWh")
    plt.title("Scénarios spot 2027 (moyenne journalière)")
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()


# ============================================================
# 5. CORRECTION 2 : ANCRAGE SUR LES TRIMESTRES EEX
# ============================================================
#
# Problème : avec construire_spot_2027, toute l'année est ancrée sur
# le seul Cal-27 (83,31 €/MWh). La répartition des prix ENTRE les
# saisons vient alors de l'année historique.
#   - Le marché, au 22/09, dit que l'hiver sera environ 3 fois plus cher
#     que le printemps (Q1 = 139 €/MWh, Q2 = 45 €/MWh).
#   - Les années historiques ne respectent pas ce rapport. En 2022,
#     c'est même l'inverse (été très cher à cause de la crise du gaz).
#
# Solution : on découpe l'année en 8 "blocs" = 4 trimestres x (Peak / Off-peak)
# et on ancre chaque bloc sur son prix EEX :
#
#   spot 2027 (heure h) = NIVEAU du bloc x FORME de l'heure h
#
#   NIVEAU du bloc = forward EEX du bloc x (1 - prime) x (1 + b x anomalie du trimestre)
#                    -> vient du MARCHE (22/09) + effet météo du scénario
#
#   FORME de l'heure = prix historique de l'heure / moyenne historique du bloc
#                    -> vient de l'HISTOIRE : jours froids, week-ends, profil horaire
#                    -> vaut 1 en moyenne sur chaque bloc
#
# Pourquoi séparer Peak et Off-peak ?
#   Parce qu'on achètera des produits Peak. Il faut que, dans nos scénarios,
#   le prix moyen des heures peak soit cohérent avec le prix EEX Peak.
#   (Ex. Q2 : le Peak à 36,50 est MOINS cher que le Base à 45,18, à cause
#   du solaire en journée. Une année historique ne le reproduit pas forcément.)
#
# Le prix Off-peak n'est pas coté sur EEX : on le déduit du Base et du Peak.
#   Base = moyenne de toutes les heures, donc :
#   F_base x heures_totales = F_peak x heures_peak + F_offpeak x heures_offpeak
#   => F_offpeak = (F_base x H_tot - F_peak x H_peak) / H_offpeak


def masque_peak_h(horodate):
    """Heures Peak EEX : lundi-vendredi, 08:00-20:00 (fériés inclus)."""
    return (
        (horodate.dt.weekday < 5)
        & (horodate.dt.hour >= 8)
        & (horodate.dt.hour < 20)
    )


def anomalies_trimestrielles(base_2027, loads_2027, recentrer=True):
    """
    Anomalie de volume de chaque scénario, trimestre par trimestre :
        anomalie = volume du trimestre (météo de l'année) / volume normal - 1

    Résultat : tableau, une ligne par année, une colonne par trimestre (1 à 4).

    recentrer=True : même logique que la correction 1, mais trimestre par
    trimestre (on retire la moyenne des scénarios de chaque trimestre).
    """

    trimestre = base_2027["horodate"].dt.quarter
    volume_normal = base_2027.groupby(trimestre)["load_normal_total_mw"].sum()

    tableau = {}
    for annee, df in loads_2027.items():
        volume_scenario = df.groupby(df["horodate"].dt.quarter)[
            "load_final_total_mw"
        ].sum()
        tableau[annee] = volume_scenario / volume_normal - 1

    # Lignes = années, colonnes = trimestres
    tableau = pd.DataFrame(tableau).T

    if recentrer:
        tableau = tableau - tableau.mean()

    return tableau


def forwards_par_bloc(forwards_t1, grille):
    """
    Pour chaque trimestre : prix Peak (coté) et prix Off-peak (déduit).
    'grille' = DataFrame horaire 2027 avec colonnes 'trimestre' et 'peak',
    utilisée pour compter les heures exactes (changements d'heure inclus).
    """

    lignes = []
    for t in range(1, 5):
        f_base = forwards_t1[f"Q{t}"]["base"]
        f_peak = forwards_t1[f"Q{t}"]["peak"]

        dans_t = grille["trimestre"] == t
        h_tot = dans_t.sum()
        h_peak = (dans_t & grille["peak"]).sum()
        h_off = h_tot - h_peak

        f_off = (f_base * h_tot - f_peak * h_peak) / h_off

        lignes.append(
            {
                "trimestre": t,
                "F_base": f_base,
                "F_peak": f_peak,
                "F_offpeak_deduit": round(f_off, 2),
                "heures_peak": h_peak,
                "heures_offpeak": h_off,
            }
        )

    return pd.DataFrame(lignes).set_index("trimestre")


def construire_spot_2027_trimestriel(
    prix,
    annee_source,
    forwards_t1,
    b,
    anomalies_trim,
    prime_risque=0.03,
    annee_cible=2027,
):
    """
    Courbe spot horaire 2027 d'un scénario, ancrée sur les trimestres EEX
    (Peak et Off-peak séparés).

    La forme est remappée avec la MEME correspondance jour-de-semaine
    que la météo du scénario -> corrélation prix-volume conservée.
    """

    # 1. Prix historiques de l'année, placés sur le calendrier 2027
    corr = construire_correspondance(annee_source, annee_cible)
    hist = prix[prix["horodate"].dt.year == annee_source]
    spot = remapper_serie(hist, ["prix"], corr, annee_cible, freq="h")

    # 2. Repérage des blocs : trimestre + peak / off-peak
    spot["trimestre"] = spot["horodate"].dt.quarter
    spot["peak"] = masque_peak_h(spot["horodate"])

    # 3. FORME : prix de l'heure / moyenne du bloc (moyenne = 1 dans chaque bloc)
    moyenne_bloc = spot.groupby(["trimestre", "peak"])["prix"].transform("mean")
    spot["forme"] = spot["prix"] / moyenne_bloc

    # 4. Prix EEX du bloc (Peak coté, Off-peak déduit)
    fwd = forwards_par_bloc(forwards_t1, spot)
    spot["forward_bloc"] = np.where(
        spot["peak"],
        spot["trimestre"].map(fwd["F_peak"]),
        spot["trimestre"].map(fwd["F_offpeak_deduit"]),
    )

    # 5. NIVEAU : forward x (1 - prime) x (1 + b x anomalie du trimestre)
    anomalie = spot["trimestre"].map(anomalies_trim.loc[annee_source])
    spot["niveau"] = spot["forward_bloc"] * (1 - prime_risque) * (1 + b * anomalie)

    # 6. Spot 2027 = niveau x forme
    spot["spot"] = spot["niveau"] * spot["forme"]
    spot["annee_scenario"] = annee_source

    return spot[
        ["horodate", "date_source", "trimestre", "peak", "forme", "spot", "annee_scenario"]
    ]


def controle_spot_trimestriel(spots):
    """
    Prix spot moyen par trimestre et par scénario.
    À comparer avec forward Base du trimestre x 0,97 (+ petit effet météo).
    """
    lignes = {}
    for annee, s in spots.items():
        lignes[f"Scénario {annee}"] = s.groupby("trimestre")["spot"].mean()
        lignes[f"Scénario {annee}"]["Année"] = s["spot"].mean()
    return pd.DataFrame(lignes).T.round(2)
"""
Étape 6 du Market Game : calcul des marges et choix de la stratégie.

Pour chaque stratégie x chaque scénario météo, heure par heure :

    MARGE = CHIFFRE D'AFFAIRES - COUT DES COUVERTURES - COUT DU RESIDUEL

    - Chiffre d'affaires : consommation réelle du scénario x prix de vente (95 €/MWh)
    - Couvertures T1     : MW achetés le 22/09 x heures x prix EEX du 22/09 (connus)
    - Couvertures T2     : MW achetés le 01/12 x heures x forward T2 ANTICIPÉ
                           (méthode alpha, propre à chaque scénario)
    - Résiduel           : (consommation - MW livrés par les couvertures) x spot
                           > 0 : on achète le manque au spot
                           < 0 : on revend l'excédent au spot (recette)

Ensuite, par stratégie :
    - marge espérée  = moyenne pondérée des scénarios (25 % chacun par défaut)
    - pire cas       = la plus mauvaise marge des scénarios
    - règle du cours : la meilleure marge espérée PARMI les stratégies dont
                       le pire cas reste au-dessus du plancher du Board (5 €/MWh)
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ============================================================
# 1. PRIX D'ACHAT A T2 (forward anticipé, par trimestre)
# ============================================================
#
# On ne connaît pas les prix du 01/12. On les anticipe pour chaque
# scénario avec la méthode alpha (guidelines §3.3), trimestre par
# trimestre et séparément pour Base et Peak :
#
#   niveau du bloc = F_T1 x (1 - prime) x (1 + b x anomalie du trimestre)
#                    (= le prix spot moyen attendu dans ce scénario)
#
#   F_T2 = F_T1 + alpha x (niveau du bloc - F_T1)
#
# Intuition : le 01/12, le marché a déjà "vu" une partie de l'hiver qui
# arrive (prévisions météo, stocks...). Le forward s'est donc rapproché
# du prix final du scénario, d'une fraction alpha du chemin.
#   alpha = 0 -> le forward n'a pas bougé depuis T1
#   alpha = 1 -> le forward vaut déjà le prix spot final


def forwards_t2(forwards_t1, b, anomalies_trim, annee, alpha, prime_risque=0.03,
                choc=0.0):
    """
    Forward anticipé au 01/12 pour un scénario.
    Retourne un dictionnaire {(trimestre, "Base"/"Peak"): prix €/MWh}.

    choc : hausse (ou baisse) du niveau des prix dans un scénario de
    crise (ex. 0.50 = +50 %). La crise se construit entre T1 et la
    livraison : au 01/12, le marché en a déjà intégré une part alpha,
    comme pour l'effet météo. Ce qu'on achète à T2 coûte donc déjà
    plus cher qu'à T1.
    """
    resultat = {}
    for q in range(1, 5):
        anomalie = anomalies_trim.loc[annee, q]
        for composante, cle in [("Base", "base"), ("Peak", "peak")]:
            f_t1 = forwards_t1[f"Q{q}"][cle]
            niveau = f_t1 * (1 - prime_risque) * (1 + b * anomalie) * (1 + choc)
            resultat[(q, composante)] = f_t1 + alpha * (niveau - f_t1)
    return resultat


# ============================================================
# 2. PRIX DE CHAQUE LIGNE D'ACHAT
# ============================================================
#
# - Achat à T1 : prix EEX du 22/09 du produit acheté (Cal ou trimestre).
# - Achat à T2 : forward T2 anticipé du trimestre.
#   Pour un Cal acheté à T2 (stratégie S5), chaque ligne trimestrielle
#   du Cal est payée au forward T2 de son trimestre. Comme le Cal vaut
#   la moyenne des trimestres (pas d'arbitrage), c'est équivalent.


def ajouter_prix_achats(achats, prix_t1, fwd_t2):
    a = achats.copy()
    a["prix"] = [
        prix_t1[produit][composante] if date == "T1" else fwd_t2[(q, composante)]
        for date, produit, q, composante in zip(
            a["date"], a["produit"], a["trimestre"], a["composante"]
        )
    ]
    return a


# ============================================================
# 3. GRILLE HORAIRE D'UN SCENARIO (consommation + spot)
# ============================================================

def grille_horaire(load_scenario, spot_scenario):
    """
    Une ligne par heure de 2027 :
    horodate, load (MW), spot (€/MWh), trimestre, peak (True/False).

    La load est au pas de 30 min : on la ramène à l'heure (moyenne des
    deux demi-heures), puisque les prix spot sont horaires.
    """
    load_h = (
        load_scenario.set_index("horodate")["load_final_total_mw"]
        .resample("h")
        .mean()
        .rename("load")
        .reset_index()
    )
    grille = load_h.merge(
        spot_scenario[["horodate", "spot", "trimestre", "peak"]],
        on="horodate",
        how="inner",
    )
    return grille


# ============================================================
# 4. PUISSANCE LIVREE PAR LES COUVERTURES, HEURE PAR HEURE
# ============================================================
#
# À l'heure h du trimestre q :
#   MW livrés = somme des MW Base achetés pour q
#             + somme des MW Peak achetés pour q   (si h est une heure peak)


def mw_livres(grille, achats):
    base = achats[achats["composante"] == "Base"].groupby("trimestre")["MW"].sum()
    peak = achats[achats["composante"] == "Peak"].groupby("trimestre")["MW"].sum()

    mw_base = grille["trimestre"].map(base).fillna(0.0)
    mw_peak = grille["trimestre"].map(peak).fillna(0.0)

    return mw_base + mw_peak * grille["peak"]


# ============================================================
# 5. MARGE D'UNE STRATEGIE DANS UN SCENARIO
# ============================================================

def marge_un_cas(grille, achats_prix, prix_vente):
    """
    Retourne le détail de la marge (en € et en €/MWh consommé).
    """

    # Nombre d'heures de chaque bloc, compté sur la grille horaire
    h_total = grille.groupby("trimestre").size()
    h_peak = grille[grille["peak"]].groupby("trimestre").size()

    a = achats_prix.copy()
    a["heures"] = [
        h_total[q] if c == "Base" else h_peak[q]
        for q, c in zip(a["trimestre"], a["composante"])
    ]
    a["energie_MWh"] = a["MW"] * a["heures"]
    a["cout_EUR"] = a["energie_MWh"] * a["prix"]

    # --- Chiffre d'affaires
    volume = grille["load"].sum()                 # MWh (pas horaire)
    ca = volume * prix_vente

    # --- Coût des couvertures
    cout_t1 = a.loc[a["date"] == "T1", "cout_EUR"].sum()
    cout_t2 = a.loc[a["date"] == "T2", "cout_EUR"].sum()

    # --- Résiduel au spot
    livre = mw_livres(grille, achats_prix)
    residuel = grille["load"] - livre             # > 0 manque, < 0 excédent
    cout_residuel = (residuel * grille["spot"]).sum()

    achat_spot = residuel.clip(lower=0).sum()     # MWh achetés au spot
    revente_spot = (-residuel).clip(lower=0).sum()  # MWh revendus au spot

    marge = ca - cout_t1 - cout_t2 - cout_residuel

    return {
        "volume_MWh": volume,
        "CA_MEUR": ca / 1e6,
        "cout_T1_MEUR": cout_t1 / 1e6,
        "cout_T2_MEUR": cout_t2 / 1e6,
        "cout_residuel_MEUR": cout_residuel / 1e6,
        "achat_spot_MWh": achat_spot,
        "revente_spot_MWh": revente_spot,
        "marge_MEUR": marge / 1e6,
        "marge_EUR_MWh": marge / volume,
        "cout_total_EUR_MWh": (cout_t1 + cout_t2 + cout_residuel) / volume,
    }


# ============================================================
# 6. TOUTES LES STRATEGIES x TOUS LES SCENARIOS
# ============================================================

def evaluer_strategies(
    achats_strategies,
    loads_2027,
    spots_2027,
    prix_t1,
    forwards_t1,
    b,
    anomalies_trim,
    alpha,
    prime_risque=0.03,
    prix_vente=95.0,
    choc=0.0,
    nom_choc="Météo seule",
):
    """
    Tableau long : une ligne par (stratégie, scénario) avec le détail
    de la marge.

    choc = 0 : scénarios de base (risque météo seul).
    choc > 0 : tous les prix spot 2027 du scénario sont multipliés par
               (1 + choc), et le forward T2 en intègre une part alpha.
    """
    lignes = []

    for annee in loads_2027:
        grille = grille_horaire(loads_2027[annee], spots_2027[annee])
        grille["spot"] = grille["spot"] * (1 + choc)
        fwd_t2 = forwards_t2(forwards_t1, b, anomalies_trim, annee, alpha,
                             prime_risque, choc)

        for nom, achats in achats_strategies.items():
            achats_prix = ajouter_prix_achats(achats, prix_t1, fwd_t2)
            detail = marge_un_cas(grille, achats_prix, prix_vente)
            lignes.append({"strategie": nom, "scenario": annee,
                           "choc": nom_choc, **detail})

    return pd.DataFrame(lignes)


# ============================================================
# 7. SYNTHESE ET CHOIX DE LA STRATEGIE
# ============================================================

def synthese(resultats, plancher=5.0, probabilites=None):
    """
    Par stratégie :
      - marge espérée (moyenne pondérée par les probabilités)
      - pire cas, meilleur cas, écart-type
      - respect du plancher du Board (pire cas >= plancher)
    """
    r = resultats.copy()
    if probabilites is None:
        n = r["scenario"].nunique()
        r["proba"] = 1 / n
    else:
        r["proba"] = r["scenario"].map(probabilites)

    lignes = []
    for nom, g in r.groupby("strategie", sort=False):
        esperee = (g["marge_EUR_MWh"] * g["proba"]).sum()
        lignes.append(
            {
                "strategie": nom,
                "marge_esperee": esperee,
                "pire_cas": g["marge_EUR_MWh"].min(),
                "scenario_pire": int(g.loc[g["marge_EUR_MWh"].idxmin(), "scenario"]),
                "meilleur_cas": g["marge_EUR_MWh"].max(),
                "ecart_type": np.sqrt((g["proba"] * (g["marge_EUR_MWh"] - esperee) ** 2).sum()),
            }
        )

    s = pd.DataFrame(lignes).set_index("strategie")
    s["respecte_plancher"] = s["pire_cas"] >= plancher
    return s


def choisir_strategie(synth, plancher=5.0):
    """
    Règle du cours (séance 4) :
      parmi les stratégies dont le pire cas >= plancher,
      choisir celle qui a la meilleure marge espérée.

    Si AUCUNE ne respecte le plancher, on le signale et on propose
    la stratégie au meilleur pire cas (la plus protectrice) : c'est
    au Board de décider s'il accepte de déroger à sa règle.
    """
    ok = synth[synth["respecte_plancher"]]

    if len(ok) > 0:
        choix = ok["marge_esperee"].idxmax()
        print(f"\nStratégie retenue : {choix}")
        print(f"  marge espérée = {synth.loc[choix, 'marge_esperee']:.2f} €/MWh")
        print(f"  pire cas      = {synth.loc[choix, 'pire_cas']:.2f} €/MWh "
              f"(plancher {plancher} €/MWh respecté)")
    else:
        choix = synth["pire_cas"].idxmax()
        print(f"\nAUCUNE stratégie ne respecte le plancher de {plancher} €/MWh.")
        print(f"Meilleur pire cas : {choix} "
              f"({synth.loc[choix, 'pire_cas']:.2f} €/MWh) -> à soumettre au Board.")

    return choix


# ============================================================
# 8. GRAPHIQUES
# ============================================================

def tracer_esperee_vs_pire(synth, plancher=5.0):
    """
    Un point par stratégie : pire cas (x) contre marge espérée (y).
    La ligne verticale est le plancher : les stratégies à droite
    respectent la règle du Board. (Image de la slide 30, séance 4.)
    """
    plt.figure(figsize=(10, 7))
    for nom, ligne in synth.iterrows():
        plt.scatter(ligne["pire_cas"], ligne["marge_esperee"], s=80)
        plt.annotate(nom, (ligne["pire_cas"], ligne["marge_esperee"]),
                     textcoords="offset points", xytext=(8, 4))
    plt.axvline(plancher, color="red", linestyle="--",
                label=f"Plancher du Board ({plancher} €/MWh)")
    plt.xlabel("Pire cas (€/MWh)")
    plt.ylabel("Marge espérée (€/MWh)")
    plt.title("Stratégies : marge espérée vs pire cas")
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()


def tracer_marges_par_scenario(resultats, plancher=5.0):
    """Barres groupées : marge de chaque stratégie dans chaque scénario."""
    tableau = resultats.pivot(index="strategie", columns="scenario",
                              values="marge_EUR_MWh")
    tableau = tableau.loc[resultats["strategie"].unique()]
    tableau.plot(kind="bar", figsize=(12, 6))
    plt.axhline(plancher, color="red", linestyle="--",
                label=f"Plancher ({plancher} €/MWh)")
    plt.ylabel("Marge (€/MWh)")
    plt.title("Marge par stratégie et par scénario météo")
    plt.xticks(rotation=20)
    plt.grid(axis="y")
    plt.legend(title="Météo")
    plt.tight_layout()
    plt.show()


# ============================================================
# 9. COUT DE LA PROTECTION (par rapport à "aucune couverture")
# ============================================================
#
# Question du Board : "combien de marge espérée abandonne-t-on, et
# combien de pire cas gagne-t-on, en se couvrant ?"
#
# On compare chaque stratégie à S0 (aucune couverture) :
#   - cout_protection   = marge espérée de S0 - marge espérée de la stratégie
#                         (> 0 : on renonce à de la marge en moyenne)
#   - gain_pire_cas     = pire cas de la stratégie - pire cas de S0
#                         (> 0 : la couverture améliore le pire scénario)
#   - efficacite        = gain_pire_cas / cout_protection
#                         (€ de pire cas gagné par € de marge espérée
#                          abandonné : plus c'est haut, plus la protection
#                          est "rentable")


def cout_protection(synth, reference="S0 Sans couverture"):
    ref = synth.loc[reference]
    t = pd.DataFrame(index=synth.index)
    t["marge_esperee"] = synth["marge_esperee"]
    t["pire_cas"] = synth["pire_cas"]
    t["cout_protection"] = ref["marge_esperee"] - synth["marge_esperee"]
    t["gain_pire_cas"] = synth["pire_cas"] - ref["pire_cas"]
    t["efficacite"] = np.where(
        t["cout_protection"] > 1e-9,
        t["gain_pire_cas"] / t["cout_protection"],
        np.nan,
    )
    return t.drop(index=reference)


# ============================================================
# 10. SENSIBILITE AU PLANCHER DU BOARD
# ============================================================
#
# Le plancher (5 €/MWh) est un CHOIX du Board, pas une donnée de marché.
# Les guidelines demandent : "what would change your answer if the floor
# were higher or lower?"
#
# On rejoue donc la règle de décision pour plusieurs planchers :
#   pour chaque plancher -> quelles stratégies passent ? laquelle choisit-on ?
# On voit ainsi à partir de quel niveau la décision change.


def sensibilite_plancher(synth, planchers=(-10.0, -5.0, -2.0, 0.0, 2.0, 3.0, 4.0, 5.0)):
    lignes = []
    for p in planchers:
        ok = synth[synth["pire_cas"] >= p]
        if len(ok) > 0:
            choix = ok["marge_esperee"].idxmax()
            lignes.append({
                "plancher": p,
                "nb_strategies_ok": len(ok),
                "strategie_choisie": choix,
                "marge_esperee": round(synth.loc[choix, "marge_esperee"], 2),
                "pire_cas": round(synth.loc[choix, "pire_cas"], 2),
            })
        else:
            lignes.append({
                "plancher": p,
                "nb_strategies_ok": 0,
                "strategie_choisie": "aucune",
                "marge_esperee": None,
                "pire_cas": None,
            })
    return pd.DataFrame(lignes).set_index("plancher")


# ============================================================
# 11. TEST DE STRESS : CRISE ENERGETIQUE
# ============================================================
#
# POURQUOI ?
# Nos 4 scénarios ne contiennent que le risque MÉTÉO : le spot moyen
# 2027 n'y varie que de ±2 %. Or le vrai risque d'un fournisseur est le
# risque de NIVEAU de prix (gaz, nucléaire, géopolitique) :
#   - volatilité annuelle des forwards ≈ 20 % (hypothèse du cours / CRE)
#   - le Cal-27 a pris +13 % entre le 22/09 et le 05/10/2026
#   - le spot moyen est passé de 58 €/MWh (2024) à 276 €/MWh (2022)
# Sans ce risque, se couvrir paraît inutile (S0 gagne partout).
#
# COMMENT ?
# Pour chaque météo (2022 à 2025), on rejoue l'année avec des prix
# spot plus élevés : spot x (1 + choc). Les achats T1 sont figés au
# prix du 22/09, les achats T2 intègrent une part alpha de la crise.
#
# COMMENT ON S'EN SERT ?
# Les scénarios de crise sont des STRESS TESTS, pas des prévisions :
#   - la marge ESPÉRÉE reste calculée sur les 4 scénarios météo
#     (on ne sait pas donner une probabilité à une crise) ;
#   - le PIRE CAS est pris sur TOUS les scénarios, crises comprises :
#     c'est lui que le Board compare à son plancher.


def evaluer_avec_crises(
    achats_strategies,
    loads_2027,
    spots_2027,
    prix_t1,
    forwards_t1,
    b,
    anomalies_trim,
    alpha,
    chocs,
    prime_risque=0.03,
    prix_vente=95.0,
):
    """
    chocs = {"Tension +20 %": 0.20, "Crise énergétique +50 %": 0.50}
    Retourne le tableau long : scénarios de base + scénarios de crise.
    """
    morceaux = [
        evaluer_strategies(achats_strategies, loads_2027, spots_2027, prix_t1,
                           forwards_t1, b, anomalies_trim, alpha,
                           prime_risque, prix_vente)
    ]
    for nom_choc, choc in chocs.items():
        print(f"  Stress test : {nom_choc} (spot x {1 + choc:.2f})")
        morceaux.append(
            evaluer_strategies(achats_strategies, loads_2027, spots_2027, prix_t1,
                               forwards_t1, b, anomalies_trim, alpha,
                               prime_risque, prix_vente,
                               choc=choc, nom_choc=nom_choc)
        )
    return pd.concat(morceaux, ignore_index=True)


def synthese_avec_crises(resultats, plancher=5.0):
    """
    Par stratégie :
      - marge_esperee   : moyenne des 4 scénarios météo (sans crise)
      - pire_cas_meteo  : pire des 4 scénarios météo
      - pire_cas_<choc> : pire cas pour chaque niveau de crise
      - pire_cas        : le pire de TOUT (c'est lui qui est comparé
                          au plancher, et utilisé par choisir_strategie,
                          cout_protection et sensibilite_plancher)
    """
    base = resultats[resultats["choc"] == "Météo seule"]

    s = pd.DataFrame(index=pd.Index(resultats["strategie"].unique(), name="strategie"))
    s["marge_esperee"] = base.groupby("strategie")["marge_EUR_MWh"].mean()

    for nom_choc, g in resultats.groupby("choc", sort=False):
        col = "pire_cas_meteo" if nom_choc == "Météo seule" else f"pire_cas [{nom_choc}]"
        s[col] = g.groupby("strategie")["marge_EUR_MWh"].min()

    s["pire_cas"] = resultats.groupby("strategie")["marge_EUR_MWh"].min()
    s["respecte_plancher"] = s["pire_cas"] >= plancher
    return s


def tracer_crises(synth):
    """Pire cas de chaque stratégie, sans crise et avec chaque niveau de crise."""
    cols = [c for c in synth.columns if c.startswith("pire_cas_meteo")
            or c.startswith("pire_cas [")]
    synth[cols].plot(kind="bar", figsize=(12, 6))
    plt.axhline(0, color="black", linewidth=0.8)
    plt.ylabel("Pire cas (€/MWh)")
    plt.title("Pire cas par stratégie : météo seule vs crise énergétique")
    plt.xticks(rotation=20)
    plt.grid(axis="y")
    plt.legend(title="Scénarios")
    plt.tight_layout()
    plt.show()

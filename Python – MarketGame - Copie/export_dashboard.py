"""
Génère le tableau de bord HTML du Market Game.

1. Fait tourner le modèle Python (données en cache dans data/) :
   load normale 2027, loads des 4 scénarios météo, pente b,
   formes de prix spot 2027.
2. Écrit ces séries dans dashboard.html (à côté de ce script).
3. Ouvre le tableau de bord dans le navigateur.

Dans le navigateur, tout le reste (prix EEX, prime, alpha, b, prix de
vente, plancher, chocs de prix, nombre de clients, stratégies) se
modifie en direct, sans relancer Python.

Relancer ce script seulement si on change :
- les données (FORCER_MAJ_API, nouvelles années),
- les années de référence / de scénario dans config.py,
- les stratégies "par défaut" de hedging.py.

Lancement : double-clic sur lancer_dashboard.bat
            ou  python export_dashboard.py
"""

import csv
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config
from enedis_api import (
    charger_ou_actualiser,
    nettoyer_gradients,
    nettoyer_profil,
    nettoyer_temperatures,
    recuperer_gradients,
    recuperer_profil,
    recuperer_temperatures,
)
from hedging import STRATEGIES
from load_2027 import construire_base_2027, construire_loads_scenarios
from load_model import (
    calculer_load,
    calculer_puissance_moyenne,
    construire_load_finale,
    fusionner_load_normale,
)
from prix import (
    anomalies_journalieres,
    anomalies_trimestrielles,
    construire_spot_2027_trimestriel,
    regression_prix_volume,
)
from prix_api import nettoyer_prix, recuperer_prix

DOSSIER = Path(__file__).resolve().parent

# ---------------------------------------------------------------------
# Stratégies par défaut du tableau de bord
#   type "mois"       : mois de janvier à juin + trimestres Q3 et Q4
#                       ratio = 8 valeurs : Jan, Fév, Mar, Avr, Mai, Juin, Q3, Q4
#   type "complement" : à T2, on complète jusqu'au total visé (8 valeurs),
#                       calculé sur la prévision de volume du jour
#   type "trimestres" : Q1 à Q4, ratio = 4 valeurs
#   type "cal_base_peak" / "cal_base" : produits annuels, ratio = 1 valeur
# Chaque achat suit la forme Base + Peak de la consommation normale.
# À T1, "complement 90 %" après 50 % revient exactement à acheter 40 % à T2.
# ---------------------------------------------------------------------
def _r(*v):
    return list(v) if len(v) > 1 else [v[0]] * 8

STRATEGIES_DASHBOARD = {
    "S0 Sans couverture": [],
    "S1 Front-loaded": [("T1", "mois", _r(0.5)), ("T2", "complement", _r(0.9))],
    "S2 Back-loaded": [("T1", "mois", _r(0.3)), ("T2", "complement", _r(0.9))],
    "S4 Saisonnière": [("T1", "mois", _r(0.6, 0.6, 0.6, 0.4, 0.4, 0.4, 0.4, 0.6)),
                       ("T2", "complement", _r(1.0, 1.0, 1.0, 0.8, 0.8, 0.8, 0.8, 1.0))],
    "S7 Couverture 100 %": [("T1", "mois", _r(0.5)), ("T2", "complement", _r(1.0))],
}
# Modifications faites depuis le tableau de bord (bouton « Enregistrer en CSV »).
# Fichier local : à mettre dans .gitignore pour ne pas l'envoyer sur GitHub.
FICHIER_LOCAL = DOSSIER / "dashboard_local.csv"
COLS8 = ["Jan", "Fev", "Mar", "Avr", "Mai", "Juin", "Q3", "Q4"]


def _valeur(texte):
    """Convertit un texte du CSV : booléen, nombre (point ou virgule) ou texte."""
    t = (texte or "").strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return t


def _poser(racine, cle, valeur):
    """Écrit valeur dans racine en suivant un chemin du type 'dates.T1.q.0.1'."""
    morceaux = cle.split(".")
    obj = racine
    for i, m in enumerate(morceaux):
        dernier = i == len(morceaux) - 1
        vide = None if dernier else ([] if morceaux[i + 1].isdigit() else {})
        if isinstance(obj, list):
            m = int(m)
            while len(obj) <= m:
                obj.append(vide)
        elif m not in obj or obj[m] is None:
            obj[m] = vide
        if dernier:
            obj[m] = valeur
        else:
            if obj[m] is None:
                obj[m] = vide
            obj = obj[m]


def appliquer_csv_local(defaults, strategies):
    """Si dashboard_local.csv existe, il remplace les paramètres et les stratégies."""
    if not FICHIER_LOCAL.exists():
        return strategies
    params, strats = {}, {}
    with open(FICHIER_LOCAL, encoding="utf-8-sig", newline="") as f:
        for ligne in csv.DictReader(f, delimiter=";"):
            if ligne["section"] == "parametre":
                params[ligne["cle"]] = _valeur(ligne["valeur"])
            elif ligne["section"] == "strategie":
                etapes = strats.setdefault(ligne["cle"], [])
                t = ligne["type"]
                if not t or t == "aucun":
                    continue
                v = [float(_valeur(ligne[c]) or 0) for c in COLS8]
                if t in ("mois", "complement"):
                    ratio = v
                elif t == "trimestres":
                    ratio = [v[0], v[3], v[6], v[7]]
                else:
                    ratio = v[0]
                etape = {"date": ligne["date"], "type": t, "ratio": ratio}
                if ligne.get("produit"):
                    etape["prod"] = ligne["produit"]
                etapes.append(etape)
    if any(k.startswith("chocs.") for k in params):
        defaults["chocs"] = []          # la liste des chocs est entièrement remplacée
    for cle, val in params.items():
        _poser(defaults, cle, val)
    print(f"Modifications locales appliquées : {FICHIER_LOCAL.name} "
          f"({len(params)} paramètres, {len(strats)} stratégies)")
    if strats:
        return [{"nom": nom, "etapes": e} for nom, e in strats.items()]
    return strategies


MODELE_HTML = DOSSIER / "dashboard_template.html"
SORTIE_HTML = DOSSIER / "dashboard.html"

FORCER_MAJ_API = False


def _arrondi(serie, decimales=3):
    return [round(float(x), decimales) for x in serie]


def _horaire(df, colonne):
    """30 min -> horaire (MW moyen sur l'heure), indexé par horodate."""
    return df.set_index("horodate")[colonne].resample("h").mean()


def construire_donnees():
    annees = list(config.ANNEES_SCENARIOS)
    annee_cible = getattr(config, "ANNEE_CIBLE", 2027)
    seuil = getattr(config, "SEUIL_CHAUFFAGE", 15.0)

    # --------------------------------------------------------
    # 1. Données en cache
    # --------------------------------------------------------
    res1 = charger_ou_actualiser("res1.csv", lambda: recuperer_profil("RES1_BASE"),
                                 nettoyer_profil, FORCER_MAJ_API)
    pro1 = charger_ou_actualiser("pro1.csv", lambda: recuperer_profil("PRO1_BASE"),
                                 nettoyer_profil, FORCER_MAJ_API)
    temperatures = charger_ou_actualiser("temperatures.csv", recuperer_temperatures,
                                         nettoyer_temperatures, FORCER_MAJ_API)
    gradients = charger_ou_actualiser("gradients.csv", recuperer_gradients,
                                      nettoyer_gradients, FORCER_MAJ_API)

    p_res1 = calculer_puissance_moyenne(config.NB_RES1, config.THETA_RES1, config.PUISSANCE_RES1)
    p_pro1 = calculer_puissance_moyenne(config.NB_PRO1, config.THETA_PRO1, config.PUISSANCE_PRO1)
    res1["load_normal_kw"] = calculer_load(res1["coefficient_dynamique"], p_res1)
    pro1["load_normal_kw"] = calculer_load(pro1["coefficient_dynamique"], p_pro1)

    # --------------------------------------------------------
    # 2. Volumes 2027 (normale + scénarios météo)
    # --------------------------------------------------------
    print("\nLoad normale 2027...")
    base = construire_base_2027(
        res1, pro1, gradients, temperatures,
        annee_ref=config.ANNEE_PROFIL_REF, annee_cible=annee_cible,
        seuil_chauffage=seuil,
    )
    loads = construire_loads_scenarios(base, temperatures, annees, annee_cible, seuil)

    # --------------------------------------------------------
    # 3. Prix historiques, pente b, formes de prix 2027
    # --------------------------------------------------------
    prix = charger_ou_actualiser("prix.csv", recuperer_prix, nettoyer_prix, FORCER_MAJ_API)
    prix = prix[prix["horodate"].dt.year.isin(annees)]
    prix = prix.set_index("horodate")["prix"].resample("h").mean().reset_index()

    load_finale_hist = construire_load_finale(
        fusionner_load_normale(res1, pro1), temperatures, gradients, seuil
    )
    anomalies = anomalies_journalieres(load_finale_hist, prix)
    mois_hiver = getattr(config, "MOIS_HIVER", (11, 12, 1, 2, 3))
    reg = regression_prix_volume(anomalies, mois=mois_hiver, annees=annees)
    reg_sans_2022 = regression_prix_volume(
        anomalies, mois=mois_hiver, annees=[a for a in annees if a != 2022]
    )
    b = float(reg["b"])
    print(f"b = {b:.2f} | R² = {reg['r2']:.2f}")

    anom_trim = anomalies_trimestrielles(base, loads)
    spots = {
        a: construire_spot_2027_trimestriel(prix, a, config.FORWARDS_T1, b, anom_trim,
                                            config.PRIME_RISQUE, annee_cible)
        for a in annees
    }

    # --------------------------------------------------------
    # 4. Grille horaire commune
    # --------------------------------------------------------
    grille = spots[annees[0]][["horodate", "trimestre", "peak"]].set_index("horodate")
    idx = grille.index

    def aligner(serie):
        return serie.reindex(idx).interpolate(limit_direction="both")

    normal_res1 = aligner(_horaire(base, "load_normal_res1_kw") / 1000)
    normal_pro1 = aligner(_horaire(base, "load_normal_pro1_kw") / 1000)

    scen = {}
    for a in annees:
        forme = spots[a].set_index("horodate")["forme"].reindex(idx)
        scen[str(a)] = {
            "res1": _arrondi(aligner(_horaire(loads[a], "load_final_res1_kw") / 1000)),
            "pro1": _arrondi(aligner(_horaire(loads[a], "load_final_pro1_kw") / 1000)),
            "forme": _arrondi(forme.fillna(1.0), 4),
        }

    # --------------------------------------------------------
    # 5. Paramètres par défaut (config.py) et stratégies (hedging.py)
    # --------------------------------------------------------
    def bloc_date(nb_res, nb_pro, cal_base, cal_peak, fwd, mois):
        return {
            "nbRes": nb_res, "nbPro": nb_pro,
            "calBase": cal_base, "calPeak": cal_peak,
            "q": [[fwd[f"Q{q}"]["base"], fwd[f"Q{q}"]["peak"]] for q in range(1, 5)],
            "mois": [[m, b_, p_] for m, (b_, p_) in (mois or {}).items()],
        }

    # Un jeu de données par date : T1 (22/09), T2 (01/12), T3 (31/12)
    dates = {"T1": bloc_date(
        config.NB_RES1, config.NB_PRO1, config.FORWARD_T1_CAL_BASE,
        getattr(config, "FORWARD_T1_CAL_PEAK", config.FORWARD_T1_CAL_BASE),
        config.FORWARDS_T1, getattr(config, "MOIS_T1", {}),
    )}
    for t in ("T2", "T3"):
        if hasattr(config, f"FORWARDS_{t}"):
            cl = getattr(config, f"CLIENTS_{t}")
            cal = getattr(config, f"FORWARD_{t}_CAL")
            dates[t] = bloc_date(cl["RES1"], cl["PRO1"], cal["base"], cal["peak"],
                                 getattr(config, f"FORWARDS_{t}"), getattr(config, f"MOIS_{t}", {}))

    defaults = {
        "thRes": config.THETA_RES1, "pRes": config.PUISSANCE_RES1,
        "thPro": config.THETA_PRO1, "pPro": config.PUISSANCE_PRO1,
        "dates": dates,
        "mode": "T1",
        "decisionT1": getattr(config, "STRATEGIE_T1", "auto"),
        "t3": {
            "temp": list(getattr(config, "TEMPERATURE_PREVUE_0101", [])),
            "solaire": list(getattr(config, "SOLAIRE_PREVU_0101", [0] * 24)),
            "mwc": getattr(config, "SOLAIRE_MWC", 0),
            "solaireOn": hasattr(config, "SOLAIRE_PREVU_0101"),
        },
        "mc": {"n": 5000, "sigma": 0.20, "sigmaQ": 0.10, "seed": 1},
        "prime": config.PRIME_RISQUE,
        "alpha": config.ALPHA,
        "b": round(b, 3),
        "recentrer": True,
        "prixVente": config.PRIX_VENTE,
        "margeCible": getattr(config, "MARGE_CIBLE", 10.0),
        "plancher": config.PLANCHER_RISQUE,
        "chocs": [[nom, v] for nom, v in getattr(config, "CHOCS_PRIX", {}).items()],
        "stress": True,
        "proba": [round(1 / len(annees), 4)] * len(annees),
    }

    # Stratégies du tableau de bord : produits Cal, trimestres ET mois.
    # (définies dans config.py par STRATEGIES_DASHBOARD si présent, sinon ci-dessous)
    strategies = []
    for nom, etapes in getattr(config, "STRATEGIES_DASHBOARD", STRATEGIES_DASHBOARD).items():
        liste = []
        for date, type_achat, ratio in etapes:
            if isinstance(ratio, dict):
                ratio = [float(ratio[q]) for q in range(1, 5)]
            elif isinstance(ratio, (list, tuple)):
                ratio = [float(x) for x in ratio]
            else:
                ratio = float(ratio)
            liste.append({"date": date, "type": type_achat, "ratio": ratio})
        strategies.append({"nom": nom, "etapes": liste})
    strategies = appliquer_csv_local(defaults, strategies)

    # Données horaires du 01/01/2027 (24 h) pour la position ouverte :
    # température normale et gradients, pour appliquer la prévision T3
    jour1 = {
        "tn": _arrondi(aligner(_horaire(base, "temperature_normale"))[:24], 2),
        "gR": _arrondi(aligner(_horaire(base, "gradient_res1"))[:24], 5),
        "gP": _arrondi(aligner(_horaire(base, "gradient_pro1"))[:24], 5),
    }

    return {
        "jour1": jour1,
        "meta": {
            "genere_le": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "annee_cible": annee_cible,
            "annees": [str(a) for a in annees],
            "annees_ref": list(config.ANNEE_PROFIL_REF)
            if isinstance(config.ANNEE_PROFIL_REF, (list, tuple)) else [config.ANNEE_PROFIL_REF],
            "b": round(b, 3),
            "r2": round(float(reg["r2"]), 3),
            "n": int(reg["n"]),
            "b_par_annee": {str(k): float(v) for k, v in reg["b_par_annee"].items()},
            "b_sans_2022": round(float(reg_sans_2022["b"]), 3),
            "ref": {"pRes": p_res1, "pPro": p_pro1},
            "seuil": seuil,
            # Résultats du day-ahead du 01/01/2027 publiés par le professeur (onglet « 01/01 »)
            "da": getattr(config, "DA_0101", None),
        },
        "heures": {
            "q": [int(x) for x in grille["trimestre"]],
            "pk": [int(bool(x)) for x in grille["peak"]],
            "m": [int(x) for x in idx.month],
            "jour": [int(x) for x in idx.dayofyear],
        },
        "normal": {"res1": _arrondi(normal_res1), "pro1": _arrondi(normal_pro1)},
        "scen": scen,
        "defaults": defaults,
        "strategies": strategies,
    }


def ecrire_html(donnees):
    modele = MODELE_HTML.read_text(encoding="utf-8")
    marqueur = "/*__DONNEES__*/null"
    if marqueur not in modele:
        raise SystemExit("Marqueur de données introuvable dans dashboard_template.html")
    json_txt = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
    SORTIE_HTML.write_text(modele.replace(marqueur, json_txt), encoding="utf-8")
    taille = SORTIE_HTML.stat().st_size / 1e6
    print(f"\nTableau de bord écrit : {SORTIE_HTML} ({taille:.1f} Mo)")


if __name__ == "__main__":
    donnees = construire_donnees()
    ecrire_html(donnees)
    if "--no-open" not in sys.argv:
        webbrowser.open(SORTIE_HTML.as_uri())

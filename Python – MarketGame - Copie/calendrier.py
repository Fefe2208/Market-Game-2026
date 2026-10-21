"""
Alignement des années historiques sur le calendrier 2027.

Principe (guidelines §3.1) : on aligne PAR JOUR DE SEMAINE, pas par date,
et on déplace les jours fériés à leurs dates 2027.

Pour chaque jour 2027 on choisit UN jour source de l'année historique :
- jour ordinaire  -> jour de même type de semaine le plus proche
                     de la même date (décalage de -3 à +3 jours),
                     en évitant les jours fériés de l'année source ;
- jour férié 2027 -> le même jour férié de l'année source
                     (Noël -> Noël, lundi de Pâques -> lundi de Pâques).

La même table de correspondance est appliquée à la météo ET aux prix
d'un scénario : la corrélation prix-volume de l'année est conservée.
"""

from datetime import date, timedelta

import pandas as pd


# ============================================================
# JOURS FERIES FRANCAIS
# ============================================================

def paques(annee):
    """Dimanche de Pâques (algorithme de Meeus / Butcher)."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return date(annee, mois, jour)


def jours_feries_fr(annee):
    """Dictionnaire {nom: date} des 11 jours fériés légaux (métropole)."""
    p = paques(annee)
    return {
        "jour_an": date(annee, 1, 1),
        "lundi_paques": p + timedelta(days=1),
        "fete_travail": date(annee, 5, 1),
        "victoire_1945": date(annee, 5, 8),
        "ascension": p + timedelta(days=39),
        "lundi_pentecote": p + timedelta(days=50),
        "fete_nationale": date(annee, 7, 14),
        "assomption": date(annee, 8, 15),
        "toussaint": date(annee, 11, 1),
        "armistice": date(annee, 11, 11),
        "noel": date(annee, 12, 25),
    }


def type_jour(d, feries):
    """'ouvre', 'samedi' ou 'dim_ferie' (feries = ensemble de dates)."""
    if d in feries or d.weekday() == 6:
        return "dim_ferie"
    if d.weekday() == 5:
        return "samedi"
    return "ouvre"


# ============================================================
# TABLE DE CORRESPONDANCE JOUR CIBLE -> JOUR SOURCE
# ============================================================

def construire_correspondance(annee_source, annee_cible=2027):
    """
    Retourne un DataFrame avec une ligne par jour de l'année cible :
    date_cible, date_source, ferie_cible, decalage_jours
    """

    feries_src = jours_feries_fr(annee_source)
    feries_cib = jours_feries_fr(annee_cible)
    dates_feries_src = set(feries_src.values())
    nom_ferie_cible = {d: nom for nom, d in feries_cib.items()}

    lignes = []

    for jour in pd.date_range(
        f"{annee_cible}-01-01", f"{annee_cible}-12-31", freq="D"
    ):
        d_cible = jour.date()

        # Même date dans l'année source (29/02 -> 28/02)
        try:
            d0 = d_cible.replace(year=annee_source)
        except ValueError:
            d0 = date(annee_source, 2, 28)

        if d_cible in nom_ferie_cible:
            # Jour férié 2027 -> même férié dans l'année source
            d_source = feries_src[nom_ferie_cible[d_cible]]

        else:
            # Décalage vers le même jour de semaine, entre -3 et +3 jours
            delta = (d_cible.weekday() - d0.weekday()) % 7
            if delta > 3:
                delta -= 7
            base = d0 + timedelta(days=delta)

            # On évite les fériés source et on reste dans l'année source
            d_source = None
            for k in (0, -1, 1, -2, 2):
                candidat = base + timedelta(days=7 * k)
                if (
                    candidat.year == annee_source
                    and candidat not in dates_feries_src
                ):
                    d_source = candidat
                    break

        lignes.append(
            {
                "date_cible": d_cible,
                "date_source": d_source,
                "ferie_cible": d_cible in nom_ferie_cible,
                "decalage_jours": (d_source - d0).days,
            }
        )

    corr = pd.DataFrame(lignes)

    # Contrôle : même type de jour des deux côtés
    feries_cib_set = set(feries_cib.values())
    ok = [
        type_jour(r.date_cible, feries_cib_set)
        == type_jour(r.date_source, dates_feries_src)
        or r.ferie_cible
        for r in corr.itertuples()
    ]
    if not all(ok):
        raise ValueError("Correspondance incohérente sur certains jours")

    return corr


def correspondance_par_date(annee_source, annee_cible=2027):
    """
    Correspondance date à date (même jour/mois), utile pour les
    grandeurs purement saisonnières comme la température normale.
    """
    lignes = []
    for jour in pd.date_range(
        f"{annee_cible}-01-01", f"{annee_cible}-12-31", freq="D"
    ):
        d_cible = jour.date()
        try:
            d_source = d_cible.replace(year=annee_source)
        except ValueError:
            d_source = date(annee_source, 2, 28)
        lignes.append({"date_cible": d_cible, "date_source": d_source})
    return pd.DataFrame(lignes)


# ============================================================
# REMAPPING D'UNE SERIE TEMPORELLE
# ============================================================

def remapper_serie(
    df,
    colonnes,
    correspondance,
    annee_cible=2027,
    freq="30min",
    tz="Europe/Paris",
):
    """
    Remappe les colonnes d'une série historique (colonne 'horodate'
    tz-aware) sur la grille de l'année cible, jour par jour, selon la
    table de correspondance.

    Le rapprochement se fait sur (date source, heure, minute) en heure
    locale. Les doublons du changement d'heure d'automne sont moyennés,
    les trous (heure de printemps) sont interpolés.
    """

    src = df[["horodate"] + list(colonnes)].copy()
    src["horodate"] = src["horodate"].dt.tz_convert(tz)

    # Ramène la source à la résolution cible (ex : 15 min -> 30 min)
    src = (
        src.set_index("horodate")
        .resample(freq)
        .mean()
        .reset_index()
    )

    src["date_source"] = src["horodate"].dt.date
    src["heure"] = src["horodate"].dt.hour
    src["minute"] = src["horodate"].dt.minute

    src = src.groupby(
        ["date_source", "heure", "minute"], as_index=False
    )[list(colonnes)].mean()

    grille = pd.DataFrame(
        {
            "horodate": pd.date_range(
                start=f"{annee_cible}-01-01 00:00",
                end=f"{annee_cible}-12-31 23:59",
                freq=freq,
                tz=tz,
            )
        }
    )
    grille["date_cible"] = grille["horodate"].dt.date
    grille["heure"] = grille["horodate"].dt.hour
    grille["minute"] = grille["horodate"].dt.minute

    grille = grille.merge(
        correspondance[["date_cible", "date_source"]],
        on="date_cible",
        how="left",
    )

    grille = grille.merge(
        src, on=["date_source", "heure", "minute"], how="left"
    )

    manquants = grille[list(colonnes)].isna().sum().sum()

    grille[list(colonnes)] = grille[list(colonnes)].interpolate(
        method="linear", limit_direction="both"
    )

    if manquants > 8 * len(colonnes):
        print(
            f"  Attention : {manquants} valeurs interpolées "
            "(données source incomplètes ?)"
        )

    return grille.drop(columns=["heure", "minute", "date_cible"])

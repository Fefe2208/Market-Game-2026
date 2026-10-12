import requests
import pandas as pd

from pathlib import Path


# ============================================================
# CONFIGURATION API
# ============================================================

URL_BASE = (
    "https://opendata.enedis.fr/data-fair/api/v1/datasets/"
)

URL_PROFILS = (
    URL_BASE
    + "coefficients-des-profils/lines"
)

URL_TEMPERATURES = (
    URL_BASE
    + "donnees-de-temperature-et-de-pseudo-rayonnement/lines"
)

URL_GRADIENTS = (
    URL_BASE
    + "coefficients-gradients-profils-dynamiques/lines"
)


# ============================================================
# DOSSIER DE CACHE LOCAL
# ============================================================

DOSSIER_DATA = Path(__file__).resolve().parent / "data"


# ============================================================
# FONCTION GENERIQUE DE PAGINATION
# ============================================================

def recuperer_toutes_les_pages(
    url,
    params=None,
    taille_page=10000,
    nom_affichage="Données"
):
    """
    Récupère toutes les pages d'une API Data Fair Enedis.

    Paramètres
    ----------
    url : str
        URL du dataset.

    params : dict ou None
        Paramètres supplémentaires de requête.

    taille_page : int
        Nombre de lignes demandées par page.

    nom_affichage : str
        Nom utilisé dans les messages du terminal.

    Retour
    ------
    pandas.DataFrame
        Toutes les lignes récupérées.
    """

    if params is None:
        params = {}

    params = params.copy()
    params["size"] = taille_page

    toutes_les_lignes = []

    url_courante = url
    total = None
    premiere_page = True

    while url_courante is not None:

        reponse = requests.get(
            url_courante,
            params=params if premiere_page else None,
            timeout=30
        )

        reponse.raise_for_status()

        data = reponse.json()

        if total is None:
            total = data.get("total")

        nouvelles_lignes = data.get("results", [])

        toutes_les_lignes.extend(
            nouvelles_lignes
        )

        print(
            f"{nom_affichage} : "
            f"{len(toutes_les_lignes)} / {total} lignes récupérées"
        )

        url_courante = data.get("next")
        premiere_page = False

    return pd.DataFrame(
        toutes_les_lignes
    )


# ============================================================
# PROFILS DE CONSOMMATION
# ============================================================

def recuperer_profil(
    sous_profil,
    taille_page=10000
):
    """
    Récupère toutes les données Enedis
    d'un sous-profil donné.

    Exemple :
        RES1_BASE
        PRO1_BASE
    """

    params = {
        "qs": f'sous_profil:"{sous_profil}"'
    }

    return recuperer_toutes_les_pages(
        url=URL_PROFILS,
        params=params,
        taille_page=taille_page,
        nom_affichage=sous_profil
    )


def nettoyer_profil(df):
    """
    Nettoie les données de profil
    et garde uniquement les colonnes utiles.
    """

    colonnes_utiles = [
        "horodate",
        "sous_profil",
        "coefficient_dynamique",
        "coefficient_ajuste",
        "coefficient_prepare"
    ]

    df = df[
        colonnes_utiles
    ].copy()

    df["horodate"] = pd.to_datetime(
        df["horodate"],
        utc=True
    ).dt.tz_convert(
        "Europe/Paris"
    )

    df = df.sort_values(
        "horodate"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# TEMPERATURES
# ============================================================

def recuperer_temperatures(
    taille_page=10000
):
    """
    Récupère toutes les températures
    normales et réalisées d'Enedis.
    """

    return recuperer_toutes_les_pages(
        url=URL_TEMPERATURES,
        taille_page=taille_page,
        nom_affichage="Températures"
    )


def nettoyer_temperatures(df):
    """
    Garde uniquement les températures
    utiles au modèle.
    """

    colonnes_utiles = [
        "horodate",
        "temperature_normale_lissee_degc",
        "temperature_realisee_lissee_degc"
    ]

    df = df[
        colonnes_utiles
    ].copy()

    df["horodate"] = pd.to_datetime(
        df["horodate"],
        utc=True
    ).dt.tz_convert(
        "Europe/Paris"
    )

    df = df.sort_values(
        "horodate"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# GRADIENTS DE TEMPERATURE
# ============================================================

def recuperer_gradients(
    taille_page=10000
):
    """
    Récupère tous les coefficients
    de gradients dynamiques Enedis.
    """

    return recuperer_toutes_les_pages(
        url=URL_GRADIENTS,
        taille_page=taille_page,
        nom_affichage="Gradients"
    )


def nettoyer_gradients(df):
    """
    Garde uniquement les gradients
    RES1_BASE et PRO1_BASE.
    """

    colonnes_utiles = [
        "horodate",
        "res1_base",
        "pro1_base"
    ]

    df = df[
        colonnes_utiles
    ].copy()

    df["horodate"] = pd.to_datetime(
        df["horodate"],
        utc=True
    ).dt.tz_convert(
        "Europe/Paris"
    )

    df = df.sort_values(
        "horodate"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# CACHE LOCAL
# ============================================================

def sauvegarder_cache(
    df,
    nom_fichier
):
    """
    Sauvegarde un DataFrame dans le dossier data.
    """

    DOSSIER_DATA.mkdir(
        exist_ok=True
    )

    chemin = (
        DOSSIER_DATA
        / nom_fichier
    )

    df.to_csv(
        chemin,
        index=False
    )

    print(
        f"Sauvegardé : {chemin}"
    )


def charger_cache(
    nom_fichier
):
    """
    Charge un fichier CSV local s'il existe.

    Retourne None si le fichier
    n'existe pas.
    """

    chemin = (
        DOSSIER_DATA
        / nom_fichier
    )

    if not chemin.exists():
        return None

    print(
        f"Chargement local : {chemin}"
    )

    df = pd.read_csv(
        chemin
    )

    if "horodate" in df.columns:

        df["horodate"] = pd.to_datetime(
            df["horodate"],
            utc=True
        ).dt.tz_convert(
            "Europe/Paris"
        )

    return df



def charger_ou_actualiser(
    nom_fichier,
    fonction_recuperation,
    fonction_nettoyage,
    forcer_maj=False
):
    """
    Charge les données depuis le cache local.

    Si forcer_maj=True :
    - récupère les données actuelles de l'API
    - les nettoie
    - les fusionne avec l'historique déjà sauvegardé
    - remplace les valeurs communes par les valeurs les plus récentes de l'API
    - conserve les anciennes dates qui ne sont plus disponibles dans l'API
    - sauvegarde le nouveau cache complet
    """

    # --------------------------------------------------------
    # 1. Charger le cache existant
    # --------------------------------------------------------

    cache = charger_cache(
        nom_fichier
    )

    # --------------------------------------------------------
    # 2. Si aucune mise à jour demandée et cache disponible
    # --------------------------------------------------------

    if not forcer_maj and cache is not None:
        return cache

    # --------------------------------------------------------
    # 3. Récupération des nouvelles données API
    # --------------------------------------------------------

    print(
        f"Mise à jour API : {nom_fichier}"
    )

    nouvelles_donnees = fonction_recuperation()

    nouvelles_donnees = fonction_nettoyage(
        nouvelles_donnees
    )

    # --------------------------------------------------------
    # 4. Si aucun historique local n'existe
    # --------------------------------------------------------

    if cache is None:

        df_final = nouvelles_donnees.copy()

    else:

        # ----------------------------------------------------
        # 5. Fusion ancien historique + API actuelle
        # ----------------------------------------------------

        df_final = pd.concat(
            [
                cache,
                nouvelles_donnees
            ],
            ignore_index=True
        )

        # En cas de même horodate :
        # on conserve la valeur provenant de l'API la plus récente
        df_final = df_final.drop_duplicates(
            subset=["horodate"],
            keep="last"
        )

    # --------------------------------------------------------
    # 6. Tri chronologique
    # --------------------------------------------------------

    df_final = df_final.sort_values(
        "horodate"
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # 7. Sauvegarde du nouvel historique complet
    # --------------------------------------------------------

    sauvegarder_cache(
        df_final,
        nom_fichier
    )

    print(
        f"Historique complet : "
        f"{df_final['horodate'].min()} "
        f"-> "
        f"{df_final['horodate'].max()}"
    )

    print(
        f"Nombre total de lignes : "
        f"{len(df_final)}"
    )

    return df_final
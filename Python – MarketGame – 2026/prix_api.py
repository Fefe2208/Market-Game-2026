import requests
import pandas as pd

URL_PRIX = "https://api.energy-charts.info/price"


def recuperer_prix(annee_debut=2022, annee_fin=2025):
    """
    Récupère les prix day-ahead France, année par année.
    """
    morceaux = []

    for annee in range(annee_debut, annee_fin + 1):
        params = {
            "bzn": "FR",
            "start": f"{annee}-01-01",
            "end": f"{annee + 1}-01-01",
        }

        reponse = requests.get(URL_PRIX, params=params, timeout=60)
        reponse.raise_for_status()
        data = reponse.json()

        df = pd.DataFrame({
            "unix_seconds": data["unix_seconds"],
            "prix": data["price"],
        })

        print(f"Prix {annee} : {len(df)} lignes récupérées")
        morceaux.append(df)

    return pd.concat(morceaux, ignore_index=True)


def nettoyer_prix(df):
    """
    Convertit le temps en horodate (heure de Paris), garde horodate + prix.
    """
    df = df.copy()

    df["horodate"] = pd.to_datetime(
        df["unix_seconds"], unit="s", utc=True
    ).dt.tz_convert("Europe/Paris")

    df = df[["horodate", "prix"]].dropna()
    df = df.drop_duplicates(subset=["horodate"])
    df = df.sort_values("horodate").reset_index(drop=True)

    return df
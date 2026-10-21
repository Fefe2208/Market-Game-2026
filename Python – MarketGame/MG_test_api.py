import requests
import pandas as pd

# =========================
# API OPEN DATA ENEDIS
# =========================

print("JE LANCE BIEN LE BON FICHIER")
print("Fichier exécuté :", __file__)



URL_GRADIENTS = (
    "https://opendata.enedis.fr/data-fair/api/v1/"
    "datasets/coefficients-gradients-profils-dynamiques/lines"
)

params = {
    "size": 20
}

reponse = requests.get(
    URL_GRADIENTS,
    params=params,
    timeout=30
)

print("Code HTTP :", reponse.status_code)
print("URL appelée :", reponse.url)

reponse.raise_for_status()

data = reponse.json()

print("\nClés du JSON :")
print(data.keys())

df = pd.DataFrame(data["results"])

print("\nPremières lignes :")
print(df.head())

print("\nColonnes disponibles :")
print(df.columns.tolist())
from enedis_api import charger_ou_actualiser
from prix_api import recuperer_prix, nettoyer_prix

FORCER_MAJ_API = False

prix = charger_ou_actualiser("prix.csv", recuperer_prix, nettoyer_prix, FORCER_MAJ_API)

print(prix.head())
print(prix.tail())

print("\n--- CONTROLE PAR ANNEE ---")
print(prix.groupby(prix["horodate"].dt.year)["prix"].agg(["count", "mean", "min", "max"]))
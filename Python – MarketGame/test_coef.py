import pandas as pd

for f in ["res1.csv", "pro1.csv"]:
    df = pd.read_csv(f"C:/Users/Fefe/Desktop/Test Api/data/{f}")

    # Garde l'année 2025 sans convertir les dates (beaucoup plus rapide)
    d = df[df["horodate"].astype(str).str.startswith("2025")]

    print(f, len(d), "lignes",
          "| dynamique =", round(d["coefficient_dynamique"].mean(), 4),
          "| préparé =", round(d["coefficient_prepare"].mean(), 4))
import matplotlib.pyplot as plt


def tracer_load_normale(load):
    """
    Trace la load normale totale du portefeuille.
    """

    plt.figure(figsize=(14, 6))

    plt.plot(
        load["horodate"],
        load["load_normal_total_mw"]
    )

    plt.xlabel("Date")
    plt.ylabel("Puissance (MW)")
    plt.title(
        "Load normale du portefeuille RES1 + PRO1"
    )

    plt.grid()
    plt.tight_layout()

    plt.show()



def tracer_semaine(load, debut, fin):
    masque = (
        (load["horodate"] >= debut)
        & (load["horodate"] <= fin)
    )

    extrait = load.loc[masque]

    plt.figure(figsize=(14, 6))

    plt.plot(
        extrait["horodate"],
        extrait["load_normal_total_mw"]
    )

    plt.xlabel("Date")
    plt.ylabel("Puissance (MW)")
    plt.title(
        f"Load normale du {debut} au {fin}"
    )

    plt.grid()
    plt.tight_layout()
    plt.show()



def tracer_comparaison_load(load, debut, fin):
    """
    Compare la load normale et la load corrigée météo
    sur une période donnée.
    """

    masque = (
        (load["horodate"] >= debut)
        & (load["horodate"] <= fin)
    )

    extrait = load.loc[masque]

    plt.figure(figsize=(14, 6))

    plt.plot(
        extrait["horodate"],
        extrait["load_normal_total_mw"],
        label="Load normale"
    )

    plt.plot(
        extrait["horodate"],
        extrait["load_final_total_mw"],
        label="Load corrigée météo"
    )

    plt.xlabel("Date")
    plt.ylabel("Puissance (MW)")
    plt.title(
        f"Comparaison load normale / corrigée météo\n"
        f"{debut} → {fin}"
    )

    plt.grid()
    plt.legend()
    plt.tight_layout()

    plt.show()
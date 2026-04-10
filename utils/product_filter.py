"""
utils/product_filter.py — Demande à l'utilisateur sur quel statut de produits travailler.
"""


def ask_product_status():
    """
    Affiche un menu pour choisir le filtre de statut produit.
    Retourne "active", "draft", ou None (tous).
    """
    print("\n  Filtrer les produits par statut :\n")
    print("  1. Tous les produits")
    print("  2. Actifs uniquement")
    print("  3. Brouillons uniquement")
    choice = input("\nChoix [1] : ").strip()
    status_map = {"1": None, "2": "active", "3": "draft", "": None}
    status = status_map.get(choice)
    label = status or "tous"
    print(f"  → Filtre : {label}")
    return status

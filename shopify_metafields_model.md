# Shopify — Modèle Champs Méta & Métaobjets

> **Ce fichier est le modèle de référence pour tous les shops.**
> Toujours créer les champs méta et métaobjets avec exactement ces noms, types et structures.

---

## 1. Métaobjets (à créer en premier)

Les métaobjets sont des structures réutilisables. Ils doivent être créés **avant** les champs méta produit qui les référencent.

---

### 1.1 `avis_client`

Représente un avis client individuel avec photos, note et texte.

| Clé du champ | Nom affiché | Type             | Obligatoire |
| ------------ | ----------- | ---------------- | ----------- |
| `photo_1`    | Photo 1     | Image (Fichier)  | ✅          |
| `photo_2`    | Photo 2     | Image (Fichier)  | ✅          |
| `note`       | Note        | Texte une ligne  | ✅          |
| `titre`      | Titre       | Texte une ligne  | ✅          |
| `texte`      | Texte       | Texte multiligne | ✅          |
| `nom_auteur` | Nom auteur  | Texte une ligne  | ✅          |

**Options du métaobjet :**

- Statut Actif/Brouillon : ✅ activé
- Traductions : ✅ activé
- Publier en tant que pages web : ❌ désactivé
- Accès à l'API Storefront : ✅ activé

---

### 1.2 `section_feature`

Représente un bloc "feature" (avantage produit) avec image, titre et description. Utilisé pour les sections de mise en avant sur la page produit.

| Clé du champ  | Nom affiché | Type             | Obligatoire |
| ------------- | ----------- | ---------------- | ----------- |
| `image`       | Image       | Image (Fichier)  | ✅          |
| `titre`       | Titre       | Texte une ligne  | ✅          |
| `description` | Description | Texte multiligne | ✅          |

**Options du métaobjet :**

- Statut Actif/Brouillon : ✅ activé
- Traductions : ✅ activé
- Publier en tant que pages web : ❌ désactivé
- Accès à l'API Storefront : ✅ activé

---

### 1.3 `benefices_produit`

Regroupe les 3 bénéfices courts affichés dans le header de la page produit (bullets).

| Clé du champ | Nom affiché | Type            | Obligatoire |
| ------------ | ----------- | --------------- | ----------- |
| `benefice_1` | Bénéfice 1  | Texte une ligne | ✅          |
| `benefice_2` | Bénéfice 2  | Texte une ligne | ✅          |
| `benefice_3` | Bénéfice 3  | Texte une ligne | ✅          |

**Options du métaobjet :**

- Statut Actif/Brouillon : ✅ activé
- Traductions : ✅ activé
- Publier en tant que pages web : ❌ désactivé
- Accès à l'API Storefront : ✅ activé

---

## 2. Champs Méta Produit

> Namespace à utiliser : `custom`
> Référence Liquid : `product.metafields.custom.<cle>`

---

### 2.1 Champs simples (texte plat)

| Clé               | Nom affiché             | Type                   | Utilisation sur la page produit                          |
| ----------------- | ----------------------- | ---------------------- | -------------------------------------------------------- |
| `phrase`          | Phrase d'accroche       | Texte une ligne        | Sous-titre juste en dessous du titre produit             |
| `caracteristique` | Caractéristiques        | Texte plusieurs lignes | Contenu de l'accordéon "Caractéristiques"                |
| `note_globale`    | Note globale du produit | Texte une ligne        | Affichage de la note étoiles (ex: `4.8 \| 19 000+ avis`) |

---

### 2.2 Champs typés Métaobjet

| Clé             | Nom affiché       | Type métaobjet      | Utilisation sur la page produit                       |
| --------------- | ----------------- | ------------------- | ----------------------------------------------------- |
| `benefices`     | Bénéfices         | `benefices_produit` | Les 3 bullets dans le header produit                  |
| `feature_1`     | Feature Section 1 | `section_feature`   | 1ère section feature (image gauche ou droite + texte) |
| `feature_2`     | Feature Section 2 | `section_feature`   | 2ème section feature (image gauche ou droite + texte) |
| `avis_client_1` | Avis Clients 1    | `avis_client`       | Avis client n°1                                       |
| `avis_client_2` | Avis Clients 2    | `avis_client`       | Avis client n°2                                       |
| `avis_client_3` | Avis Clients 3    | `avis_client`       | Avis client n°3                                       |
| `avis_client_4` | Avis Clients 4    | `avis_client`       | Avis client n°4                                       |
| `avis_client_5` | Avis Clients 5    | `avis_client`       | Avis client n°5                                       |
| `avis_client_6` | Avis Clients 6    | `avis_client`       | Avis client n°6                                       |
| `avis_client_7` | Avis Clients 7    | `avis_client`       | Avis client n°7                                       |
| `avis_client_8` | Avis Clients 8    | `avis_client`       | Avis client n°8                                       |

---

## 3. Ordre de création dans Shopify Admin

Toujours respecter cet ordre pour éviter les erreurs de référence :

1. Créer le métaobjet **`benefices_produit`**
2. Créer le métaobjet **`section_feature`**
3. Créer le métaobjet **`avis_client`**
4. Créer les champs méta produit simples (`phrase`, `caracteristique`, `note_globale`)
5. Créer les champs méta produit typés métaobjet (`benefices`, `feature_1`, `feature_2`, `avis_client_1` → `avis_client_8`)
6. Remplir les entrées de métaobjets dans **Contenu > Métaobjets**
7. Associer les entrées aux produits dans la fiche produit

---

## 5. Récapitulatif visuel

```
Produit
├── phrase                  (texte)
├── caracteristique         (texte multiligne)
├── note_globale            (texte)
├── benefices ──────────────► benefices_produit
│                                ├── benefice_1
│                                ├── benefice_2
│                                └── benefice_3
├── feature_1 ──────────────► section_feature
│                                ├── image
│                                ├── titre
│                                └── description
├── feature_2 ──────────────► section_feature
│                                ├── image
│                                ├── titre
│                                └── description
├── avis_client_1 ──────────► avis_client
│                                ├── photo_1
│                                ├── photo_2
│                                ├── note
│                                ├── titre
│                                ├── texte
│                                └── nom_auteur
├── avis_client_2 ──────────► avis_client
│   ...
└── avis_client_8 ──────────► avis_client
```

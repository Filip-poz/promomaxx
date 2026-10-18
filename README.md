# Tableau des promos

Les promos de la semaine chez **Delhaize** et **Carrefour Market** (Belgique), comparées à la marque maison la moins chère du même magasin, au kilo, au litre ou à la pièce.

**Site :** https://filip-poz.github.io/tableau-des-promos/

## Ce que fait la page
- **Vraie affaire** : de combien une promo est moins chère que la marque maison équivalente. Une remise de −50 % sur un produit de marque qui reste plus cher que la marque maison n'en est pas une.
- Remise effective à la quantité exigée (1+1 = 50 %, 2+1 = 33 %, 2e à −50 % = 25 %…).
- Liste d'essentiels modifiable, panier rangé par rayon, promos masquables. Tout reste dans votre navigateur.
- Badges « À stocker », « Nouveau », « Souvent en promo », « Prix de base en hausse » à partir de l'historique hebdomadaire.

## Fonctionnement
Les promos sont relevées chaque semaine sur les sites publics des magasins (`scrape-browser.js`, à coller dans la console du navigateur), puis `build.py` calcule les comparaisons et génère la page :

```
python3 build.py <dossier-des-relevés> docs
```

`docs/index.html` est la page publiée. `history.json` garde les 12 dernières semaines.

Les prix en ligne peuvent différer légèrement du magasin. Projet personnel, sans lien avec Delhaize ni Carrefour.

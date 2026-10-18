# Promomaxx

Les promos de la semaine chez **Delhaize** et **Carrefour Market** (Belgique), comparées au produit de marque du magasin le moins cher, dans le même magasin, au kilo, au litre ou à la pièce.

**Site :** https://filip-poz.github.io/promomaxx/

## Ce que fait la page
- **Vraie affaire** : au moins 15 % moins chère que la référence du même magasin (« 28 % moins cher que la référence Carrefour »). Une remise de −50 % sur un produit de marque qui reste plus cher que la marque du magasin n'en est pas une.
- Prix à payer pour la quantité exigée (« 5,99 € pour 2 unités »), prix par unité et au kilo ou au litre, prix habituel. « Voir le calcul » détaille la réduction, la référence exacte et la portée de la comparaison. Une offre illisible est affichée telle quelle, sans calcul.
- Mes essentiels (catégories suivies, avec « Tout sélectionner »), « Ma liste » de courses rangée par magasin et par rayon, offres masquables. Tout reste dans votre navigateur.
- Étiquettes « Bon plan qui se garde », « Nouveau », « Souvent en promo », « Prix habituel en hausse » à partir de l'historique hebdomadaire.

## Fonctionnement
Les promos sont relevées chaque semaine sur les sites publics des magasins (`scrape-browser.js`, à coller dans la console du navigateur), puis `build.py` calcule les comparaisons et génère la page :

```
python3 build.py <dossier-des-relevés> docs
```

`docs/index.html` est la page publiée. `history.json` garde les 12 dernières semaines (un nouvel instantané seulement pour une nouvelle date de relevé). La logique de calcul et de comparaison est dans `promo.py`, testée par `python3 -m pytest tests -q`.

Les prix en ligne peuvent différer légèrement du magasin. Projet personnel, sans lien avec Delhaize ni Carrefour.

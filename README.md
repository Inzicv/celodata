# Celodata

Celodata pseudonymise des documents français sur votre machine avant leur envoi à une IA, puis remet les vraies valeurs dans la réponse.

Le projet est en cours de construction. Une première appli Windows existe et se lance depuis le code source. Il n'y a pas encore d'installeur.

## Pourquoi

Beaucoup d'entreprises interdisent les assistants IA par peur de la fuite de données. Celodata vise à leur donner un filtre local, vérifiable et en français, pour qu'elles puissent autoriser ces outils.

Celodata réduit le risque de fuite. Il ne garantit pas l'anonymat : une donnée pseudonymisée reste une donnée personnelle au sens du RGPD.

## État du projet

| Étape | Contenu | État |
|---|---|---|
| 0 | Structure du dépôt, jeu de faux documents, mesure des modèles | fait |
| 1 | Détection : règles françaises + modèle d'entités + fusion | fait |
| 2 | Jetons, table de correspondance chiffrée, réidentification | fait |
| 3 | Appli Windows | fait, à essayer sur un vrai échange avec une IA |
| 4 | Journal, fichiers Word et PDF, règles personnalisées | à faire |
| 5 | Passerelle serveur | à faire |

La conception est décrite dans [docs/conception.md](docs/conception.md).

## Lancer l'appli

Il faut [uv](https://docs.astral.sh/uv/). La première fois, le modèle d'entités doit être téléchargé (voir « Mesurer » ci-dessous). Ensuite l'appli tourne sans connexion.

```bash
uv run --extra modeles celodata
```

1. Choisir un mot de passe : il protège la table de correspondance, rangée dans `%LOCALAPPDATA%\Celodata`. Il n'existe aucun moyen de le récupérer.
2. Coller un texte, cliquer sur « Analyser », corriger l'aperçu.
3. « Copier le texte filtré », le coller dans l'IA.
4. Coller la réponse dans l'onglet « Restaurer ».

Sans le modèle d'entités, l'appli fonctionne avec les règles seules et l'indique : les noms ne sont alors pas détectés.

## Mesurer les modèles de détection

Il faut [uv](https://docs.astral.sh/uv/). Les modèles sont téléchargés depuis Hugging Face à la première utilisation (plusieurs centaines de Mo chacun).

```bash
uv sync --extra modeles
```

```bash
uv run celodata-mesure --details
```

Le jeu de test est dans [jeu_de_test](jeu_de_test/README.md). Il ne contient que des données inventées.

## Tests

```bash
uv run pytest
```

## Licence

Apache 2.0.

# Celodata

Celodata pseudonymise des documents français sur votre machine avant leur envoi à une IA, puis remet les vraies valeurs dans la réponse.

Le projet est en cours de construction. Rien n'est encore utilisable : la détection existe et se mesure, mais le remplacement par des jetons et l'appli ne sont pas faits.

## Pourquoi

Beaucoup d'entreprises interdisent les assistants IA par peur de la fuite de données. Celodata vise à leur donner un filtre local, vérifiable et en français, pour qu'elles puissent autoriser ces outils.

Celodata réduit le risque de fuite. Il ne garantit pas l'anonymat : une donnée pseudonymisée reste une donnée personnelle au sens du RGPD.

## État du projet

| Étape | Contenu | État |
|---|---|---|
| 0 | Structure du dépôt, jeu de faux documents, mesure des modèles | fait |
| 1 | Détection : règles françaises + modèle d'entités + fusion | fait |
| 2 | Jetons, table de correspondance chiffrée, réidentification | à faire |
| 3 | Appli Windows | à faire |
| 4 | Journal, fichiers Word et PDF, règles personnalisées | à faire |
| 5 | Passerelle serveur | à faire |

La conception est décrite dans [docs/conception.md](docs/conception.md).

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

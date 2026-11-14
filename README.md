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
| 4 | Journal, fichiers Word et PDF, règles personnalisées, dossier entier | fait, boîtes « Ouvrir » à essayer dans la vraie fenêtre |
| 5 | Passerelle serveur au format OpenAI | fait, essayé face à une fausse IA seulement |
| 6 | Fichiers Word et Excel filtrés et restaurés dans leur format | fait, à essayer sur de vrais fichiers ouverts dans Word et Excel |
| 7 | PDF rendus en Word filtré, PDF scannés lus sur le poste | fait, mesuré sur de faux scans seulement |

La conception est décrite dans [docs/conception.md](docs/conception.md). Pour essayer l'appli et la passerelle pas à pas avec de faux documents, suivre [docs/tutoriel-essai.md](docs/tutoriel-essai.md).

## Lancer l'appli

Il faut [uv](https://docs.astral.sh/uv/). La première fois, le modèle d'entités doit être téléchargé (voir « Mesurer » ci-dessous). Ensuite l'appli tourne sans connexion.

```bash
uv run --extra modeles celodata
```

1. Choisir un mot de passe : il protège la table de correspondance, rangée dans `%LOCALAPPDATA%\Celodata`. Il n'existe aucun moyen de le récupérer.
2. Coller un texte, cliquer sur « Analyser », corriger l'aperçu.
3. « Copier le texte filtré », le coller dans l'IA.
4. Coller la réponse dans l'onglet « Restaurer ».

Autres possibilités :

- **Fichiers** : déposer un fichier dans la zone de texte ou cliquer sur « Ouvrir un fichier… ». Sont lus les fichiers texte, Word (`.docx`), Excel (`.xlsx`) et PDF.
- **PDF** : après l'aperçu, « Enregistrer le fichier filtré… » produit un Word neuf qui contient le texte filtré. La mise en page du PDF n'est pas gardée, et rien de ce que le PDF pouvait cacher ne s'y retrouve.
- **PDF scanné** : les pages sans texte sont lues par la reconnaissance de caractères de Windows, sur le poste. Il faut que le français soit installé dans Windows. Une lecture de scan n'est jamais parfaite : un nom ou un numéro mal lu n'est pas masqué, donc l'aperçu doit être relu en entier. Pour cette raison, un scan n'est pas traité par « Filtrer un dossier… ».
- **Word et Excel dans leur format** : après l'aperçu, « Enregistrer le fichier filtré… » produit un Word ou un Excel filtré qui garde sa mise en forme, à joindre à l'IA à la place de l'original. Les propriétés du fichier (auteur, société) sont vidées. Les images qu'il contient ne sont pas filtrées : l'appli le signale.
- **Fichier rendu par l'IA** : dans l'onglet « Restaurer », « Restaurer un fichier… » remet les vraies valeurs dans un Word, un Excel ou un fichier texte.
- **Dossier entier** : « Filtrer un dossier… » traite tous les documents d'un dossier sans aperçu et range les fichiers filtrés dans un sous-dossier `celodata_filtré`. Un Word reste un Word, un Excel reste un Excel, un PDF devient un Word. Les originaux ne sont pas modifiés. Ces fichiers n'ont pas été vérifiés à l'écran : il faut les relire avant envoi.
- **Règles du projet** (onglet « Règles ») : termes toujours masqués, motifs (expressions régulières), termes jamais masqués.
- **Journal** (onglet « Journal ») : date, document, nombre de passages masqués par type et par origine. Aucune vraie valeur n'y figure.

Sans le modèle d'entités, l'appli fonctionne avec les règles seules et l'indique : les noms ne sont alors pas détectés.

## Lancer la passerelle

La passerelle sert aux entreprises qui utilisent une IA par son API : un outil de discussion qu'elles installent elles-mêmes (Open WebUI, LibreChat) ou leurs propres applications. Elle se place entre cet outil et l'IA, filtre chaque demande et restaure chaque réponse, sans geste de l'utilisateur.

Elle ne fonctionne pas avec les abonnements ChatGPT ou Claude utilisés sur le site de l'éditeur : pour ceux-là, il faut l'appli.

1. Copier [docs/passerelle.exemple.toml](docs/passerelle.exemple.toml) sous le nom `passerelle.toml` et y mettre l'adresse de l'IA.
2. Mettre la clé de l'IA dans la variable d'environnement `CELODATA_CLE_IA`.
3. Créer un utilisateur. Sa clé d'accès s'affiche une seule fois :

```bash
uv run --extra passerelle celodata-passerelle utilisateur alice
```

4. Lancer le serveur :

```bash
uv run --extra modeles --extra passerelle celodata-passerelle servir
```

5. Dans l'outil de discussion, indiquer `http://127.0.0.1:8787/v1` comme adresse de l'IA et la clé d'accès de l'utilisateur comme clé.

Chaque utilisateur a sa propre table chiffrée, protégée par sa clé d'accès. Une clé perdue rend ses anciens textes impossibles à restaurer. Il n'y a pas d'aperçu : ce que le détecteur rate part vers l'IA. La passerelle ne fait pas le HTTPS elle-même.

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

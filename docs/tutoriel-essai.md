# Essayer Celodata : l'appli et la passerelle

Ce tutoriel fait essayer l'appli Windows puis la passerelle, avec de faux documents uniquement. Rien ne sort de la machine, sauf à l'étape facultative « vraie IA », où seul du texte filtré de faux documents est envoyé.

Compter 30 minutes pour l'appli et 10 minutes pour la passerelle.

## 0. Préparer

Toutes les commandes se lancent depuis le dossier du projet, celui qui contient `pyproject.toml`.

Installer ce qu'il faut (une seule fois) :

```bash
uv sync --extra modeles --extra passerelle
```

Fabriquer les faux fichiers d'essai :

```bash
uv run python outils/fabriquer_essais.py
```

Un dossier `essais` apparaît, avec cinq faux documents :

| Fichier | Sert à essayer |
|---|---|
| `mail_paie.txt` | le texte collé |
| `contrat_travail.docx` | un Word, avec du gras |
| `fichier_clients.xlsx` | un Excel |
| `reclamation.pdf` | un PDF de texte |
| `note_rh_scannee.pdf` | un PDF scanné |

Le dossier `essais` n'est pas suivi par git. Il peut être supprimé à tout moment.

## 1. L'appli

### Lancer

```bash
uv run --extra modeles celodata --table essais/essai.celodata
```

L'option `--table` range la table d'essai dans le dossier `essais`, à part de la vraie table.

1. Choisir un mot de passe d'au moins 8 caractères et le confirmer.
2. Attendre que « Chargement du modèle… », en bas à gauche du rail, devienne « Noms et numéros détectés ».

Si l'appli affiche « Règles seules : les noms ne sont pas détectés », le modèle n'est pas sur la machine.

### Essai 1 : un texte collé

1. Ouvrir `essais/mail_paie.txt` dans le Bloc-notes et tout copier.
2. Dans l'appli, laisser « Pseudonymiser », cliquer sur « Coller un texte », coller, puis « Analyser le texte ».
3. Le document apparaît. Vérifier que les noms, le téléphone, le matricule et l'IBAN sont surlignés, et listés à droite par type.
4. Décocher une ligne de la liste : le passage est barré dans le document, et toutes ses autres occurrences aussi. Cliquer sur un passage surligné fait la même chose.
5. Cliquer sur une valeur de la liste : le document défile jusqu'à elle.
6. Sélectionner un mot à la souris dans le document : la boîte « Masquer comme » apparaît. Choisir un type, cliquer sur « Masquer ».
7. Cliquer sur le bouton « Pseudonymiser … » en bas à droite, puis « Copier pour l'IA ». Le texte s'affiche dessous et se trouve dans le presse-papiers.

### Essai 2 : le retour

1. Aller dans l'onglet « Restaurer ».
2. Coller le texte (il est encore dans le presse-papiers).
3. Avant de cliquer, abîmer un jeton à la main, par exemple `PERSONNE_1` en `Personne 1`, et ajouter un jeton inventé comme `PERSONNE_99`.
4. Cliquer sur « Restaurer ».

À vérifier : le texte d'origine revient, `Personne 1` est restauré et signalé « forme approchée », `PERSONNE_99` est laissé tel quel et signalé « absent de la table ».

### Essai 3 : un Word

1. Onglet « Protéger », « Protéger un autre document » si besoin, puis « Choisir un fichier » et `essais/contrat_travail.docx`. On peut aussi glisser le fichier dans la fenêtre.
2. Le texte ne s'affiche pas tout de suite : l'appli montre « Analyse de… », puis le document déjà surligné.
3. Cliquer sur « Pseudonymiser … », puis « Enregistrer le Word », garder le nom proposé.
4. Ouvrir le fichier produit dans Word.

À vérifier dans Word : les jetons à la place des valeurs, le gras toujours là, et dans Fichier > Informations, plus d'auteur « Camille Faux-Nom ».

Puis le retour : onglet « Restaurer », « Restaurer un fichier », choisir le fichier filtré, enregistrer. Le Word restauré doit être identique à l'original.

### Essai 4 : un Excel

Même parcours avec `essais/fichier_clients.xlsx`. À vérifier dans Excel : chaque cellule a son propre jeton, le tableau a gardé sa forme.

### Essai 5 : caviarder un PDF, puis un PDF scanné

1. Sur l'écran « Déposer », choisir « Caviarder », puis ouvrir `essais/reclamation.pdf`. Cliquer sur « Caviarder … », puis « Enregistrer le PDF ».
2. Ouvrir le PDF produit. Il doit avoir la même mise en page, avec des rectangles noirs sur les données. Essayer d'y sélectionner du texte : il n'y en a plus, chaque page est une image.
3. Ouvrir `essais/note_rh_scannee.pdf`. Un avertissement demande de relire tout le document.
4. Regarder de près les erreurs de lecture (un `10` lu `IO`, par exemple) et ce qui reste en clair à cause d'elles. C'est la limite à connaître.
5. Cliquer sur « Caviarder … », puis « Enregistrer le PDF ». Vérifier les rectangles noirs sur le scan.

Pour comparer : sur le même PDF, « Pseudonymiser » produit un Word qui contient le texte avec des jetons.

Tampons et signatures : les faux PDF d'essai n'en ont pas. Pour essayer, ouvrir un PDF qui en contient (un faux, ou un document sans enjeu), puis cliquer sur « Pages » à l'étape « Vérifier ». Les zones noires sont celles qui seront recouvertes. Cliquer sur une zone la laisse visible. Tracer un rectangle à la souris en ajoute une. Le PDF caviardé doit correspondre à ce que montre cette vue.

### Essai 6 : un dossier entier

1. Sur le premier écran, laisser « Pseudonymiser », ouvrir « Traiter un dossier entier » et cliquer sur « Choisir le dossier ». Choisir le dossier `essais`.
2. Attendre le tableau de résultats.
3. Basculer sur « Caviarder » plus haut, puis recommencer.

À vérifier : `essais/celodata_filtré` contient le Word, l'Excel, le texte et le PDF (devenu Word). `essais/celodata_caviardé` contient le Word, l'Excel, le texte et le PDF (resté PDF, en images). Le PDF scanné est traité lui aussi, avec la mention « scan lu par reconnaissance de caractères, à relire ». La colonne « À vérifier » compte les fonctions (DRH, PDG) laissées en clair.

### Essai 7 : le dossier surveillé

1. Créer un dossier vide, par exemple `essais/depots`.
2. Onglet « Dossier surveillé », « Choisir un dossier », choisir ce dossier.
3. Dans l'Explorateur, copier `essais/reclamation.pdf` dans ce dossier.
4. Revenir à l'appli sans rien cliquer : en quelques secondes, le document apparaît dans la liste, « Prêt », et un compteur s'affiche sur l'onglet.
5. Cliquer sur « Vérifier » : le document s'ouvre déjà analysé. Cliquer sur « Caviarder … » (ou « Pseudonymiser … »), puis enregistrer le fichier.

À vérifier : rien n'a été écrit dans le dossier avant l'enregistrement, et la ligne passe à « Exporté ». Fermer puis rouvrir l'appli : le dossier est toujours surveillé.

### Essai 8 : les règles et le journal

1. Onglet « Règles ». Ajouter « Toujours masquer » avec un mot du mail, par exemple `régularisation`.
2. Revenir à « Protéger », recoller le mail, « Analyser le texte » : le mot est maintenant surligné.
3. Dans « Règles », la liste montre aussi les passages décochés à l'essai 1. « Retirer » les supprime.
4. Onglet « Journal » : une ligne par traitement, qui dit s'il s'agit d'une pseudonymisation ou d'un caviardage, avec des décomptes et aucune vraie valeur. Le bouton « Exporter en CSV » enregistre le journal complet.

### Essai 9 (facultatif) : une vraie IA

Uniquement avec le faux mail, jamais avec un vrai document.

1. Pseudonymiser `mail_paie.txt` et copier le texte.
2. Le coller dans Claude ou ChatGPT avec une demande, par exemple « Résume ce mail en trois points et propose une réponse ».
3. Copier la réponse, la coller dans « Restaurer ».

À vérifier : la réponse restaurée se lit normalement, avec les vrais noms. Noter ce que l'IA a fait des jetons (recopiés, déformés, inventés).

### Fermer et rouvrir

Fermer la fenêtre, relancer la même commande : l'appli demande le mot de passe. Un mauvais mot de passe est refusé. Recoller le mail : les mêmes valeurs reçoivent les mêmes jetons.

## 2. La passerelle

La passerelle s'essaie avec une fausse IA, qui affiche ce qu'elle reçoit et le répète. Il faut trois terminaux, tous ouverts dans le dossier du projet.

### Terminal 1 : la fausse IA

```bash
uv run --extra passerelle python outils/fausse_ia.py
```

Elle reste ouverte et affichera tout ce qui lui arrive.

### Terminal 2 : la passerelle

Créer un utilisateur. Sa clé d'accès s'affiche une seule fois : la copier.

```bash
uv run --extra passerelle celodata-passerelle --reglages outils/passerelle.essai.toml utilisateur celine
```

Donner à la passerelle la clé de l'IA. Pour la fausse IA, n'importe quel mot convient. Dans PowerShell :

```bash
$env:CELODATA_CLE_IA = "essai"
```

Lancer le serveur, dans le même terminal :

```bash
uv run --extra modeles --extra passerelle celodata-passerelle --reglages outils/passerelle.essai.toml servir
```

Le serveur est prêt quand la ligne « Uvicorn running on http://127.0.0.1:8787 » apparaît (le modèle met quelques secondes à se charger).

### Terminal 3 : poser une question

```bash
uv run --extra passerelle python outils/demander.py essais/mail_paie.txt
```

Coller la clé d'accès quand elle est demandée (elle ne s'affiche pas), puis Entrée.

À vérifier :

| Où | Ce qu'on doit voir |
|---|---|
| Terminal 1, la fausse IA | Le mail avec des jetons, aucun nom ni numéro. La mention « clé d'un utilisateur Celodata reçue : non ». |
| Terminal 3, la réponse | Le mail avec les vraies valeurs, sauf les secrets, remplacés par `[SECRET_SUPPRIMÉ]`. |

Puis la même chose avec une réponse mot à mot :

```bash
uv run --extra passerelle python outils/demander.py essais/mail_paie.txt --flux
```

La réponse s'affiche progressivement et aucun morceau de jeton ne doit apparaître.

### Deux contrôles de sécurité

1. Relancer la commande du terminal 3 et taper une clé fausse : la réponse doit être « Erreur 401 », et le terminal 1 ne doit rien afficher de nouveau.
2. Regarder le dossier `essais/passerelle` : il contient `celine.celodata` (sa table chiffrée) et `utilisateurs.json`, qui ne contient que l'empreinte de la clé, pas la clé.

### Arrêter

Ctrl+C dans les terminaux 1 et 2.

### Avec une vraie IA ou un vrai outil de discussion (facultatif)

Copier `docs/passerelle.exemple.toml` sous le nom `passerelle.toml`, y mettre l'adresse de l'IA, mettre la vraie clé dans `CELODATA_CLE_IA`, puis lancer `servir` avec `--reglages passerelle.toml`. Dans l'outil de discussion (Open WebUI, par exemple), indiquer `http://127.0.0.1:8787/v1` comme adresse et la clé d'accès Celodata comme clé. À n'essayer qu'avec de faux documents.

## 3. Ce qui doit alerter

| Constat | Ce que ça veut dire |
|---|---|
| Un nom ou un numéro en clair dans le document, non surligné | Le détecteur l'a raté. Le masquer à la main et le noter : c'est un cas à ajouter au jeu de test. |
| Beaucoup de mots ordinaires surlignés | Le modèle masque trop. Les démasquer : l'appli s'en souvient. |
| Une valeur en clair dans le terminal de la fausse IA | Fuite par la passerelle, qui n'a pas d'aperçu. À noter avec le texte concerné. |
| Un Word ou un Excel filtré qui ne s'ouvre pas | Défaut du fichier produit : ils n'ont été relus que par programme. |
| Un rectangle noir décalé, ou une donnée qui dépasse du rectangle | Défaut du caviardage. À noter avec le PDF concerné. |
| Un tampon ou une signature sans zone noire dans la vue « Pages » | Le repérage l'a raté. Tracer la zone à la main et le noter. |
| Beaucoup de zones noires sur du texte imprimé | La lecture du scan a raté ces lignes : elles sont recouvertes par prudence. |
| Un document déposé qui n'apparaît pas dans « Dossier surveillé » | La surveillance n'a été essayée que par programme. |
| Un bouton « Ouvrir » ou « Enregistrer » qui ne fait rien | Les boîtes de Windows n'ont pas été essayées dans la vraie fenêtre. |

## 4. Nettoyer

Supprimer le dossier `essais` efface les faux fichiers, la table d'essai de l'appli et celle de la passerelle.

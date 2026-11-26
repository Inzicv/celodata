# Conception de Celodata

Ce document décrit ce qu'on construit, dans quel ordre, et pourquoi. Il s'appuie sur le cadrage et sur les décisions du brainstorm, rangés dans le dossier `.claude`.

## 1. Ce que le système doit faire

- Détecter dans un texte français les données personnelles et, en option, les données confidentielles (montants, noms de projets).
- Les remplacer par des jetons stables : la même valeur donne toujours le même jeton dans un projet.
- Montrer à l'utilisateur ce qui a été détecté et le laisser corriger avant tout envoi.
- Remettre les vraies valeurs dans la réponse de l'IA.
- Tracer chaque traitement sans jamais conserver de vraie valeur dans le journal.

## 2. Contraintes

| Contrainte | Conséquence |
|---|---|
| Projet mené par une personne | Réutiliser l'existant (Presidio, GLiNER). Petites étapes, chacune utilisable. |
| V1 en interface graphique sur Windows | Pas de ligne de commande utilisateur ni de Mac ou Linux au départ. |
| Tout tourne sur le poste, sans connexion sortante | Modèles téléchargés à l'installation, aucune télémétrie. |
| PC de bureau sans carte graphique | Modèle d'entités léger, quelques secondes par page au plus. |
| Licence Apache 2.0 | Seuls des modèles et bibliothèques à licence compatible. |
| Documents avant logs | Le premier profil est le texte libre : mails, courriers, contrats. |

## 3. Vue d'ensemble

```
   Appli Windows (étapes 3-4)         Passerelle serveur (étape 5)
            │                                   │
            └───────────────┬───────────────────┘
                            ▼
                  Moteur Celodata (Python)
  ┌────────────┬────────────┬──────────┬───────────────┬──────────┐
  │ Détection  │   Fusion   │  Jetons  │ Table         │ Journal  │
  │ règles FR  │ + 2e passe │          │ chiffrée      │          │
  │ + modèle   │            │          │               │          │
  └────────────┴────────────┴──────────┴───────────────┴──────────┘
```

Le moteur est une bibliothèque Python. L'appli et la passerelle sont deux habillages du même moteur et de la même table.

### Trajet d'un texte

1. **Détection** : les règles et le modèle d'entités produisent chacun une liste de passages à masquer.
2. **Fusion** : les chevauchements sont réglés, les trois règles sur les fonctions sont appliquées, puis chaque valeur déjà connue de la table est recherchée littéralement dans tout le texte.
3. **Aperçu** : l'utilisateur voit les passages surlignés, en ajoute ou en retire. Chaque correction devient une règle du projet.
4. **Remplacement** : chaque valeur reçoit son jeton, la table est mise à jour.
5. **Retour** : dans la réponse de l'IA, les jetons sont retrouvés, même déformés, et remplacés par les vraies valeurs. Les jetons inconnus sont signalés.

## 4. Les briques

### Détection

Tous les détecteurs respectent le même contrat (`Detecteur` dans `src/celodata/detection/base.py`) : ils reçoivent un texte et rendent une liste de `Detection` (position, type, score, source). Changer de modèle revient à changer une ligne de configuration.

| Couche | Rôle | Choix |
|---|---|---|
| Règles | Formats fixes : NIR, SIRET, IBAN, plaques, téléphones, mails, IP, dates | Presidio comme ossature, règles françaises écrites pour Celodata, avec vérification des clés de contrôle |
| Modèle d'entités | Noms, organisations, adresses, fonctions, montants, projets | GLiNER2-PII au départ (`fastino/gliner2-privacy-filter-PII-multi`) |
| Listes | Termes toujours ou jamais masqués, données sensibles de l'article 9 | Listes par projet, plus une liste de termes de santé et de syndicat |
| Modèle de langage local | Combinaisons rares, cas ambigus | En option, plus tard |

### Fusion

- En cas de chevauchement, la détection la plus longue l'emporte, puis le score le plus élevé.
- Les règles l'emportent sur le modèle pour les formats fixes.
- Données indirectes, trois règles validées :
  1. un lieu ou une organisation accolé à une fonction est toujours masqué ;
  2. une fonction unique (DRH, PDG, délégué syndical) est signalée dans l'aperçu ;
  3. une donnée sensible de l'article 9 est masquée par défaut.

### Jetons

- Format lisible, du type `PERSONNE_12`.
- Relecture tolérante au retour : `Personne 12`, `PERSONNE-12`, `[PERSONNE_12]` sont reconnus.
- Les secrets (mots de passe, clés) sont supprimés et ne reçoivent pas de jeton réversible.

### Table de correspondance

- Un fichier SQLite par projet, qui ne quitte pas la machine.
- Chaque valeur est chiffrée en AES-GCM. La clé est dérivée d'un mot de passe (Argon2id).
- Pour retrouver le jeton d'une valeur sans tout déchiffrer, la table garde une empreinte à clé (HMAC) de chaque valeur.
- Durée de vie paramétrable. Table détruite ou mot de passe perdu : réidentification impossible, c'est voulu.

### Journal

- Contient : date, fichier, mode (aperçu ou dossier), nombre d'éléments masqués par type et par origine, scores, réidentifications, version de l'outil.
- Ne contient jamais de vraie valeur. Le nom du fichier est chiffré, parce qu'il peut contenir un nom.
- Il est rangé dans le fichier de la table du projet.

### Interface

- Une fenêtre Windows qui affiche une interface HTML (`pywebview`), sans serveur ouvert sur le réseau.
- Quatre gestes : déposer ou coller, vérifier l'aperçu, copier le texte filtré, coller la réponse pour la restaurer.

## 5. Choix et contreparties

| Choix | Pourquoi | Contrepartie |
|---|---|---|
| Moteur séparé de l'interface | Les deux produits le partagent | Un peu plus de structure dès le départ |
| Modèle interchangeable | Les modèles évoluent vite, le classement peut changer | Un contrat commun à maintenir |
| GLiNER2-PII au départ | Meilleur compromis mesuré, licence Apache 2.0, accepte nos propres types | Rate les données de l'article 9, d'où les listes |
| Interface HTML dans une fenêtre | Aperçu surligné simple à faire, écran réutilisable pour la passerelle | Installeur plus lourd |
| Chiffrement valeur par valeur | Plus simple à installer sur Windows qu'une base entièrement chiffrée | Les types et le nombre de valeurs restent lisibles dans le fichier |
| Jetons lisibles | Se repèrent au retour même déformés | Le texte filtré est moins naturel qu'avec de fausses valeurs réalistes |

Modèles écartés : Piiranha (licence non commerciale), les modèles à liste de types figée comme modèle principal (CamemBERT NER, Privacy Filter), parce qu'ils ne peuvent pas chercher un montant ou un nom de projet.

## 6. Mesure

Le jeu de test (`jeu_de_test`) sert d'arbitre. Chaque changement de règle ou de modèle est mesuré dessus.

- **Formats fixes** : objectif 100 %.
- **Texte libre** : on compte les valeurs distinctes jamais détectées. La cible sera fixée quand le moteur de l'étape 1 existera.
- **Détections hors cible** : suivies pour que l'aperçu reste utilisable.
- **Aller-retour** : un texte filtré puis restauré doit être identique à l'original.

Limite : dix documents donnent une tendance. Le jeu grandira à chaque cas raté rencontré.

### Résultat de l'étape 1 (14 novembre 2026)

| Détecteur | Texte libre | Formats fixes | Hors cible |
|---|---|---|---|
| `regles` seules | 37/134 | 83/83 | 9 |
| `gliner2-pii` seul | 118/134 | 68/83 | 88 |
| `celodata` (règles + modèle + fusion) | 133/134 | 83/83 | 89 |

Les règles ont été écrites en regardant ce jeu : le 100 % prouve qu'elles fonctionnent sur ces cas, pas sur des documents jamais vus. Il faudra de nouveaux faux documents pour le vérifier.

Reste à faire dans la détection :

- la règle 2 (fonction unique signalée « à vérifier »), qui a besoin de l'aperçu de l'étape 3 ;
- les initiales (« P.-Y. Le Bihan »), seul raté du jeu ;
- les détections hors cible du modèle (89), à réduire par le seuil ou une liste de termes jamais masqués ;
- le choix des dates à masquer : aujourd'hui toutes les dates complètes le sont.

### Résultat de l'étape 2 (14 novembre 2026)

Les dix faux documents, filtrés puis restaurés, redonnent l'original au caractère près, secrets mis à part (ils sont supprimés). Les formes déformées d'un jeton (`Personne 12`, `PERSONNE-12`, `[PERSONNE_12]`) sont reconnues et signalées comme approximatives.

Limites connues :

- une même personne écrite de deux façons (« Stéphane Girard » puis « Girard ») reçoit deux jetons : l'IA y voit deux personnes ;
- la lecture tolérante peut prendre un texte ordinaire pour un jeton (« date 3 ») si un jeton `DATE_3` existe : ces cas sont listés comme approximatifs pour vérification ;
- les types, le nombre de valeurs et leur date d'ajout restent lisibles dans le fichier de la table ;
- l'aller-retour n'a pas encore été essayé avec la réponse d'une vraie IA.

### Résultat de l'étape 3 (14 novembre 2026)

L'appli (`src/celodata/appli`) ouvre une fenêtre Windows sans serveur ni port ouvert. La boucle a été déroulée dans la vraie fenêtre : mot de passe, analyse, aperçu, filtrage, copie, restauration.

- Cliquer sur un passage le démasque partout où la même valeur apparaît. Sélectionner du texte permet de le masquer.
- Les corrections deviennent la mémoire du projet : une valeur démasquée n'est plus proposée (seule son empreinte est gardée), une valeur ajoutée est retrouvée dans les textes suivants.
- Règle 2 : les fonctions uniques (DRH, PDG...) sont signalées « à vérifier » et ne sont masquées que sur un clic.
- Le texte collé n'est jamais écrit sur disque.

Reste à faire : l'essai sur un vrai échange avec une IA, un installeur, le choix entre plusieurs projets, le changement de mot de passe.

### Résultat de l'étape 4 (14 novembre 2026)

Le jeu de dix faux documents, réparti en fichiers texte, Word et PDF, passe en une fois : 10 documents filtrés en 12 secondes, aucune valeur annotée restée en clair, un PDF sans texte signalé comme non lu.

- **Fichiers** (`documents.py`) : texte, Word `.docx` (`python-docx`) et PDF (`pypdf`), lus en mémoire. Seul le texte est repris.
- **Dossier** (`lot.py`) : chaque document donne un fichier texte filtré dans `celodata_filtré`. Une même valeur garde le même jeton dans tout le dossier.
- **Règles du projet** : termes toujours masqués, motifs, termes jamais masqués. Elles sont chiffrées dans la table et passent avant le détecteur.
- **Journal** : une ligne par filtrage et par restauration, dans le fichier de la table. Les décomptes sont en clair, le nom du fichier est chiffré.

Limites connues :

- le traitement d'un dossier se fait sans aperçu : les fonctions « à vérifier » restent en clair et sont seulement comptées ;
- le fichier filtré garde le nom du document d'origine, qui peut contenir un nom de personne ;
- la mise en forme Word et PDF est perdue, les PDF scannés et les anciens `.doc` ne sont pas lus ;
- l'ordre du texte d'un PDF en colonnes ou en tableaux dépend de `pypdf` et n'a été essayé que sur des PDF simples ;
- un motif mal écrit peut ralentir fortement l'analyse ;
- le journal ne s'exporte pas encore, et ses dates et décomptes sont lisibles dans le fichier de la table ;
- les boîtes de Windows « Ouvrir un fichier » et « Filtrer un dossier » n'ont pas été essayées dans la vraie fenêtre.

### Résultat de l'étape 5 (14 novembre 2026)

La passerelle (`src/celodata/passerelle`) est un petit relais écrit pour Celodata, au format OpenAI. Elle a été essayée lancée pour de vrai, modèle chargé, face à une fausse IA locale qui répète ce qu'elle reçoit : sur les dix faux documents, aucune valeur annotée n'est arrivée en clair à la fausse IA, et la réponse restaurée est identique à l'original sur neuf documents, y compris quand elle arrive en morceaux de trois caractères. Le dixième diffère d'un mot : un identifiant que le modèle a pris pour un secret et supprimé.

Choix faits :

- **Relais maison plutôt que LiteLLM ou PrivAiTe** : peu de code, tout dans le dépôt, donc facile à auditer. Une entreprise qui veut beaucoup de fournisseurs peut placer LiteLLM derrière.
- **Trois adresses seulement** : `chat/completions`, `models`, `sante`. Tout le reste est refusé, pour que rien ne parte sans être filtré.
- **Une table par utilisateur** : la clé d'accès de l'utilisateur sert de mot de passe à sa table. Le serveur ne garde que l'empreinte de la clé et ne peut pas ouvrir une table sans son utilisateur.
- **La clé de l'IA reste sur le serveur** : les utilisateurs n'ont que leur clé Celodata.
- **Réponses en flux** : la fin d'un morceau est retenue tant qu'elle peut être le début d'un jeton.
- **Ce qui ne se filtre pas est refusé** : images et fichiers joints.

Limites connues :

- **elle ne sert qu'aux usages par API** (outil de discussion installé par l'entreprise, applications internes). Elle ne peut pas s'intercaler devant ChatGPT Enterprise ou Claude Team, où le navigateur parle directement à l'éditeur ;
- pas d'aperçu : un nom raté par le détecteur part vers l'IA, et les fonctions « à vérifier » restent en clair ;
- le modèle prend parfois une valeur ordinaire pour un secret et la supprime pour de bon (vu sur un identifiant après « password for ») ;
- une table ouverte reste déchiffrable en mémoire tant que le serveur tourne ;
- une demande à la fois passe dans le détecteur : compter une à deux secondes par page nouvelle ;
- pas de HTTPS : pour l'ouvrir à d'autres postes, il faut la placer derrière un serveur qui le fait ;
- pas de changement de clé pour un utilisateur, pas de quotas ni de suivi des coûts, pas de règles du projet réglables à distance ;
- les définitions d'outils (`tools`) écrites par un développeur sont transmises telles quelles ;
- aucun essai avec une vraie IA ni avec un vrai outil de discussion (Open WebUI, LibreChat).

### Résultat de l'étape 6 (14 novembre 2026)

Un fichier Word ou Excel peut être filtré puis restauré en gardant son format (`fichiers.py`). Les dix faux documents, mis en Word (un mot sur trois en gras) et en Excel, ont été filtrés avec le modèle puis restaurés : sur les vingt fichiers, aucune valeur annotée n'est restée en clair et le texte restauré est identique à l'original.

Principe : le fichier est vu comme une suite d'emplacements de texte (bouts de phrase, cellules) et de séparateurs. Mis bout à bout, ils donnent le texte que lit le détecteur. Chaque remplacement est reporté dans son emplacement d'origine, sans toucher à la mise en forme.

- **Word** : lu directement dans son archive. Corps, tableaux, en-têtes, pieds, notes, commentaires, zones de texte, texte supprimé en suivi des modifications, liens externes. Les propriétés (auteur, société, titre) sont vidées.
- **Excel** (`openpyxl`) : noms de feuilles, cellules de texte, nombres et dates (lus comme du texte, parce qu'un nombre peut être un SIRET), formules, commentaires, liens.
- **Passage à cheval** : un nom dont une partie est en gras reçoit un seul jeton. Un passage qui traverse deux cellules ou deux paragraphes reçoit un jeton par cellule, pour que le tableau garde sa forme.
- **Dans l'appli** : l'aperçu et les corrections s'appliquent au fichier, puis « Enregistrer le fichier filtré… ». « Restaurer un fichier… » pour le retour. Le dossier entier garde aussi les formats.

Limites connues :

- les images, objets incorporés et propriétés personnalisées d'un Word ne sont pas filtrés : l'appli le signale, sans les retirer ;
- les graphiques et images d'un Excel ne sont pas repris dans le fichier produit, et les en-têtes, pieds de page et noms définis ne sont pas filtrés ;
- une cellule de nombre ou de date masquée devient du texte, et le reste après restauration ;
- une formule qui cite une feuille renommée par un jeton ne fonctionne plus dans le fichier filtré ;
- dans un tableau, le détecteur n'a pas le titre de la colonne pour s'aider : une colonne « Nom » remplie de prénoms seuls peut être moins bien détectée qu'une phrase ;
- un grand classeur est long à analyser (une à deux secondes par page de texte) ;
- les anciens `.doc` et `.xls` ne sont pas lus ;
- les fichiers produits n'ont pas été ouverts dans Word ni dans Excel : ils ont été relus par `python-docx` et `openpyxl` ;
- les boîtes de Windows (ouvrir, enregistrer) n'ont pas été essayées dans la vraie fenêtre.

### Résultat de l'étape 7 (14 novembre 2026)

Les PDF sont le format des contrats. L'usage visé est l'analyse et le résumé : c'est le contenu qui compte, pas l'aspect.

- **PDF de texte** : le texte est filtré puis rendu dans un Word neuf (`texte_en_word`). Rien de ce que le PDF pouvait cacher (propriétés, signets, calques, pièces jointes) ne s'y retrouve, puisque le fichier est reconstruit.
- **PDF scanné** (`ocr.py`) : une page sans texte est rendue en image (`pypdfium2`) puis lue par la reconnaissance de caractères de Windows, en français. Tout se passe sur le poste, sans modèle à télécharger. Un PDF qui mélange pages de texte et pages scannées est lu page par page.
- **Garde-fou** : un scan n'est lu que dans l'appli, où un avertissement demande de relire tout l'aperçu. Le traitement d'un dossier le refuse, parce qu'il n'a pas d'aperçu.

Choix écartés : réécrire le texte dans le PDF lui-même (la seule bibliothèque qui le fait bien, PyMuPDF, est sous licence AGPL ou payante), et masquer sur l'image des pages (l'IA lirait moins bien, pour un usage qui n'a pas besoin de l'aspect).

Mesure sur les dix faux documents transformés en faux scans (page dessinée, légèrement tournée, floutée, bruitée, compressée) :

| Entrée | Valeurs lues exactement | Valeurs restées en clair après filtrage |
|---|---|---|
| Texte direct | 217/217 | 1/214 |
| Faux scan propre | non mesuré | 7/214 |
| Faux scan moyen | 189/217 | 2/214 |

Une valeur compte comme restée en clair si un morceau d'au moins 60 % de sa longueur se retrouve dans le texte filtré. Le modèle reconnaît donc la plupart des valeurs mal lues (« 04 72 OO 11 22 », un IBAN qui a perdu son « F »). La lecture prend environ 0,1 seconde par page.

Limites connues :

- ces chiffres viennent de faux scans fabriqués par programme, avec une seule police : de vrais scans (tampons, signatures, écriture à la main, pages de travers, mauvaise photocopie) seront moins bien lus ;
- l'écriture manuscrite n'est pas lue ;
- les colonnes et les tableaux d'un scan sont rendus ligne par ligne, sans garantie d'ordre ;
- la lecture des scans ne fonctionne que sous Windows, avec le français installé ;
- la mise en page du PDF est perdue, et ses images ne sont pas reprises ;
- la passerelle ne lit pas de fichiers : cette étape ne concerne que l'appli.

### Résultat de l'étape 8 (15 novembre 2026)

Trois demandes après le premier essai de l'appli sur de vrais documents : un écran plus simple, le caviardage, un dossier surveillé.

**Caviardage.** Le choix entre pseudonymiser et caviarder se fait à l'export, après la vérification. Le caviardage ne range rien dans la table.

| Fichier | Résultat du caviardage |
|---|---|
| Texte, Word, Excel | Chaque passage devient `█████`, toujours de la même longueur. Le format est gardé. |
| PDF de texte ou scanné | PDF neuf fait d'images à 200 points par pouce, un rectangle noir sur chaque passage. |

Pour un PDF, la place de chaque caractère vient de pdfium, et celle de chaque mot d'un scan vient de la reconnaissance de caractères de Windows. Le PDF produit ne contient aucun texte : rien n'est récupérable sous les rectangles, et rien de ce que le PDF d'origine cachait n'est repris. Contrepartie : le texte du PDF caviardé ne peut plus être sélectionné ni cherché.

Pour que les positions correspondent, tous les PDF sont maintenant lus par pdfium (`src/celodata/pdf.py`), et plus par pypdf.

**Tampons et signatures.** Sur chaque page d'un PDF, rendue à 50 points par pouce, le texte lu est effacé et les taches d'encre qui restent sont gardées si elles font au moins 8 mm sur 5 mm environ. Les traits fins et les cadres presque vides sont écartés. Les zones trouvées sont recouvertes par défaut en caviardage. La vue « Pages » de l'appli permet d'en décocher une ou d'en tracer une à la main. Effet voulu : un passage imprimé que la lecture d'un scan a raté ressort comme une zone, donc il est recouvert au lieu de partir sans contrôle. Limite : le repérage est approché (un logo est pris, un tampon très pâle peut être manqué), et il n'y a pas de correction dans un dossier traité sans aperçu.

**Scans dans un dossier.** Ils étaient refusés par prudence. Ils sont maintenant traités comme les autres et signalés « à relire » dans les résultats (décision du 15 novembre 2026) : aucun fichier d'un dossier n'est relu à l'écran de toute façon, et le but est de gagner du temps.

**Dossier surveillé.** L'appli relit le dossier toutes les deux secondes et analyse chaque nouveau document en tâche de fond. Elle n'écrit rien : le document attend dans l'onglet, prêt à vérifier. Ce choix garde la règle de l'aperçu, surtout pour les scans. Le chemin du dossier est rangé chiffré dans la table.

**Écran.** Trois étapes : déposer, vérifier, exporter. Le texte d'un fichier n'est plus affiché avant l'analyse. La vérification montre le document à gauche et la liste des données à droite, classée par type.

Vérifié par programme et dans un navigateur, sur les faux documents d'essai :

- un PDF caviardé relu par pypdf ne rend aucun texte ;
- un PDF caviardé relu par la reconnaissance de caractères ne rend plus les valeurs recouvertes ;
- un faux tampon et une fausse signature sont repérés puis recouverts, un trait de soulignement ne l'est pas ;
- 100 tests passent.

Non vérifié : la vraie fenêtre Windows, de vrais scans, de vrais tampons et signatures, des PDF tournés ou à plusieurs colonnes, la tenue en mémoire sur de gros PDF.

### Résultat de l'étape 9 (26 novembre 2026)

Deux demandes : régler plus finement ce qui est masqué, et mieux protéger la table sur le poste.

**Traitement et préréglage au dépôt.** Le choix entre pseudonymiser et caviarder se fait maintenant à l'étape « Déposer », avant l'analyse, pour un texte, un document ou un dossier. Il remplace le choix à l'export de l'étape 8.

**Catégories plus fines.** La détection range à part les rôles et métiers, les termes génériques, les durées, les dates de textes de loi et les âges. Un préréglage dit quelles catégories restent en clair : elles sont quand même listées, décochées. Quatre préréglages d'origine, modifiables dans l'onglet Règles ; l'appli démarre sur « RH / paie ». Les termes imposés et les secrets sont toujours masqués. Un faux contrat de stage rejoint le jeu de test.

**Enveloppe des clés.** Les clés de la table sont tirées au hasard et rangées dans le fichier sous une enveloppe chiffrée. Seule la clé de l'enveloppe vient du mot de passe (Argon2id). Une table d'avant l'étape 9 est reprise telle quelle : ses clés sont gardées et mises sous enveloppe à sa première ouverture dans l'appli.

**Lien au poste.** Dans l'appli, la clé de l'enveloppe dépend aussi d'un secret de 32 octets gardé par Windows pour ce compte et ce poste (DPAPI), dans un fichier `.poste` à côté de la table. Une table copiée ailleurs ne s'ouvre pas, même avec le mot de passe. L'ancien sel est effacé du fichier (`secure_delete`) quand une table est liée. « Déplacer la table » enregistre une copie que le mot de passe seul ouvre, liée au nouveau poste à sa première ouverture. La passerelle n'est pas concernée : ses tables restent protégées par la clé d'accès de chaque utilisateur.

**Windows Hello.** Demandé après le mot de passe, et avant « Déplacer la table », si le poste en a un. C'est une barrière d'accès à l'appli, pas un chiffrement. Un refus ou un silence de deux minutes laisse la table fermée.

Contreparties :

- une session Windows perdue ou réinstallée fait perdre la table, comme un mot de passe oublié ;
- une sauvegarde faite avant le lien s'ouvre encore avec le mot de passe seul ;
- Windows Hello ne protège pas contre quelqu'un qui a déjà le mot de passe et la session Windows ouverte.

Vérifié par programme : table liée refusée sans son secret ou avec un autre, ancienne table reprise puis liée, copie déplacée ouverte avec le mot de passe seul puis liée au nouveau poste, mot de passe vérifié avant toute demande Windows Hello, vrai secret DPAPI créé, relu et refusé quand il vient d'ailleurs. 123 tests passent. Windows Hello est disponible sur le poste d'essai.

Non vérifié : la vraie demande Windows Hello dans la fenêtre de l'appli, et l'ouverture d'une table copiée sur un second poste réel.

## 7. Étapes

| Étape | Contenu | C'est fini quand |
|---|---|---|
| 0 | Structure du dépôt, jeu de faux documents, script de mesure | Le script sort un score par détecteur sur dix faux documents |
| 1 | Règles françaises, modèle d'entités, fusion | 100 % sur les formats fixes du jeu de test |
| 2 | Jetons, table chiffrée, réidentification | L'aller-retour redonne le texte d'origine, même avec des jetons déformés |
| 3 | Appli Windows : coller, aperçu, corriger, copier, restaurer | La boucle complète fonctionne sur un vrai échange avec une IA |
| 4 | Journal, fichiers Word et PDF, règles personnalisées | Un dossier de documents passe en une fois |
| 5 | Passerelle serveur au format OpenAI | Une demande filtrée et sa réponse restaurée passent par le serveur, face à une fausse IA |
| 6 | Fichiers Word et Excel filtrés et restaurés dans leur format | Un Word et un Excel filtrés puis restaurés redonnent leur contenu, mise en forme gardée |
| 7 | PDF rendus en Word filtré, PDF scannés lus sur le poste | Un PDF de texte et un PDF scanné donnent chacun un Word filtré |
| 8 | Caviardage, PDF caviardés en image, dossier surveillé, nouvel écran | Un PDF de texte et un PDF scanné sortent caviardés, sans texte sous les rectangles |
| 9 | Préréglages, table liée au poste, Windows Hello | Une table copiée sur un autre poste ne s'ouvre pas, même avec le mot de passe |

L'extension de navigateur, un temps envisagée, est écartée (décision du 14 novembre 2026, voir la section 8).

## 8. À revoir plus tard

- Le format des jetons, quand on aura vu comment plusieurs IA les déforment.
- Le stockage de la clé : la table de l'appli est liée au poste par DPAPI depuis l'étape 9. Reste le coffre d'entreprise, et la passerelle.
- Le traitement en flux pour les gros logs, et les fausses valeurs qui gardent le format (IP, chemins), au moment du profil logs.
- Un adaptateur pour brancher le moteur dans LiteLLM, si une entreprise le demande.
- La formulation « 100 % hors ligne » : elle vaut pour l'appli. La passerelle envoie par nature le texte filtré vers l'IA, et rien d'autre.
- L'extension de navigateur est écartée (décision du 14 novembre 2026). Raisons : un employé qui veut contourner le peut toujours (autre navigateur, téléphone, connecteurs cloud, applis de bureau), et le vrai risque est dans les fichiers joints, qu'une extension ne règle pas sans que le moteur sache d'abord produire un fichier filtré. Celodata reste sur deux produits : la passerelle et l'appli déployée sur les postes. Le but est de sensibiliser l'employé et de lui donner le moyen de bien faire, pas de l'empêcher.
- Ce que cette décision demande à l'appli : un fichier filtré qui garde son format et la restauration d'un fichier rendu par l'IA (faits à l'étape 6), puis un installeur pour la déployer et un guide court pour l'employé (à faire).
- Les secrets trouvés par le modèle seul. Décision du 14 novembre 2026 : ils sont supprimés pour de bon, comme ceux trouvés par une règle. Sur le faux jeu (trois secrets), le modèle seul trouve un vrai secret que les règles ratent, et un faux. Un faux secret se voit dans la réponse (`[SECRET_SUPPRIMÉ]`) et le document d'origine n'est pas touché ; un vrai secret gardé dans la table ne se verrait pas. À reposer avec un jeu plus grand, après avoir ajouté la règle qui manque.

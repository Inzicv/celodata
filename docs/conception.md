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
   Appli Windows (étape 3)            Passerelle serveur (étape 5)
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

- Contient : date, fichier, mode, nombre d'éléments masqués par type, règles appliquées, scores, réidentifications, version de l'outil.
- Ne contient jamais de vraie valeur.

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

## 7. Étapes

| Étape | Contenu | C'est fini quand |
|---|---|---|
| 0 | Structure du dépôt, jeu de faux documents, script de mesure | Le script sort un score par détecteur sur dix faux documents |
| 1 | Règles françaises, modèle d'entités, fusion | 100 % sur les formats fixes du jeu de test |
| 2 | Jetons, table chiffrée, réidentification | L'aller-retour redonne le texte d'origine, même avec des jetons déformés |
| 3 | Appli Windows : coller, aperçu, corriger, copier, restaurer | La boucle complète fonctionne sur un vrai échange avec une IA |
| 4 | Journal, fichiers Word et PDF, règles personnalisées | Un dossier de documents passe en une fois |
| 5 | Passerelle serveur | À cadrer à ce moment-là |

## 8. À revoir plus tard

- Le format des jetons, quand on aura vu comment plusieurs IA les déforment.
- Le stockage de la clé : trousseau Windows, puis coffre d'entreprise.
- Le traitement en flux pour les gros logs, et les fausses valeurs qui gardent le format (IP, chemins), au moment du profil logs.
- La forme de la passerelle : repartir de LiteLLM ou de PrivAiTe, et faire ou non de Celodata la fenêtre de discussion.
- La formulation « 100 % hors ligne » pour la passerelle, qui envoie par nature le texte filtré vers l'IA.

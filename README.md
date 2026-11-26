# Celodata

[![CI](https://github.com/Inzicv/celodata/actions/workflows/ci.yml/badge.svg)](https://github.com/Inzicv/celodata/actions/workflows/ci.yml)
[![Licence Apache 2.0](https://img.shields.io/badge/licence-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Celodata remplace les données personnelles d'un document français par des jetons, sur votre machine, avant l'envoi à une IA. Il remet ensuite les vraies valeurs dans la réponse.

Il sait aussi **caviarder** un document : les données sont alors retirées pour de bon, sans retour possible.

```
Document d'origine        Ce que l'IA reçoit              Réponse restaurée
------------------        ------------------              -----------------
Bonjour Mme Durand,       Bonjour Mme PERSONNE_1,         Mme Durand doit
votre IBAN FR76 3000…     votre IBAN IBAN_1 est           confirmer son IBAN
est enregistré.           enregistré.                     FR76 3000…
```

![Écran de vérification de Celodata sur un faux contrat PDF](docs/apercu-appli.png)

> Projet libre sous licence Apache 2.0 · distribué depuis les sources via `uv` (installeur Windows prévu).

## Sommaire

- [Pourquoi](#pourquoi)
- [Ce que Celodata fait et ne fait pas](#ce-que-celodata-fait-et-ne-fait-pas)
- [Les deux façons de l'utiliser](#les-deux-façons-de-lutiliser)
- [Installer et démarrer](#installer-et-démarrer)
- [Comment ça marche](#comment-ça-marche)
- [L'appli Windows](#lappli-windows)
- [La passerelle serveur](#la-passerelle-serveur)
- [Sécurité](#sécurité)
- [Architecture, mesure et tests](#architecture-mesure-et-tests)
- [Limites connues](#limites-connues)
- [Feuille de route et contribution](#feuille-de-route-et-contribution)

## Pourquoi

Beaucoup d'entreprises freinent l'usage des assistants IA par crainte de fuite de données, ou doivent caviarder manuellement des contrats et dossiers RH avant de les transmettre à un tiers. Celodata leur donne un filtre local, vérifiable et pensé pour le français (NIR, SIRET, IBAN, données de santé article 9, syndicats, fonctions uniques). L'aperçu sensibilise aussi l'utilisateur en lui montrant ce que son document contient avant qu'il ne parte.

## Ce que Celodata fait et ne fait pas

| Il fait | Il ne fait pas |
|---|---|
| Détecter les données personnelles d'un texte français et les remplacer par des jetons | Garantir l'anonymat : une donnée pseudonymisée reste une donnée personnelle au sens du RGPD |
| Montrer ce qui a été détecté et laisser corriger avant l'envoi | Empêcher un employé de coller un document non filtré dans une IA |
| Remettre les vraies valeurs dans la réponse de l'IA | Filtrer les images contenues dans un Word ou un Excel |
| Caviarder un document : rectangles noirs sur un PDF, marque `█████` ailleurs | Restaurer un document caviardé |
| Supprimer pour de bon les mots de passe, jetons et clés d'API | Rendre un secret supprimé : il n'est pas restauré au retour |
| Tout traiter sur le poste, sans connexion sortante ni télémétrie | Récupérer une table dont le mot de passe est perdu |

## Les deux façons de l'utiliser

| | Appli Windows | Passerelle serveur |
|---|---|---|
| Pour qui | L'employé qui utilise ChatGPT, Claude ou un autre assistant sur le site de l'éditeur, ou qui doit caviarder des documents | L'entreprise qui appelle une IA par son API (Open WebUI, LibreChat, applications internes) |
| Où elle tourne | Sur le poste de l'employé (Windows 10/11) | Sur un serveur de l'entreprise (Linux, macOS ou Windows), entre l'outil et l'IA |
| Geste de l'utilisateur | Filtrer, vérifier, copier/exporter, restaurer la réponse | Aucun : chaque demande est filtrée, chaque réponse restaurée |
| Aperçu avant envoi | Oui | Non : ce que le détecteur rate part vers l'IA |
| Table | Une par poste, liée à la session Windows | Une par utilisateur, protégée par sa clé d'accès |

La passerelle ne s'intercale pas devant ChatGPT ou Claude utilisés sur le site de l'éditeur : pour ceux-là, il faut l'appli.

## Installer et démarrer

Prérequis : [uv](https://docs.astral.sh/uv/) et Python 3.11–3.13 (Windows 10/11 pour l'appli ; Linux, macOS ou Windows pour la passerelle et le moteur).

1. Installer les dépendances depuis le dossier du projet :

```bash
uv sync --extra modeles --extra passerelle
```

2. Télécharger une seule fois le modèle d'entités local ([`fastino/gliner2-privacy-filter-PII-multi`](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi), quelques centaines de Mo, licence Apache 2.0) :

```bash
uv run --extra modeles celodata --telecharger-modele
```

Ensuite, **aucune connexion sortante** n'est ouverte par l'appli (`HF_HUB_OFFLINE=1` est forcé au démarrage) et tout tourne sur CPU sans carte graphique (~1 à 2 s par page).

3. Lancer l'appli :

```bash
uv run --extra modeles celodata
```

Pour un premier essai guidé avec de faux documents fournis, suivre [docs/tutoriel-essai.md](docs/tutoriel-essai.md).

## Comment ça marche

Un texte suit cinq étapes :

1. **Détection.** Deux détecteurs lisent le texte :
   - Les **règles françaises** (`regex`) reconnaissent les formats fixes (mail, téléphone, NIR, SIRET/SIREN, TVA, IBAN, BIC, plaque, IP, MAC, dates, termes de santé et syndicats) et vérifient les clés de contrôle.
   - Le **modèle d'entités local** — par défaut `fastino/gliner2-privacy-filter-PII-multi` (GLiNER2-PII, Apache 2.0, interchangeable avec `urchade/gliner_multi_pii-v1` ou `Jean-Baptiste/camembert-ner` dans `src/celodata/detection/modeles.py`) — reconnaît ce qui n'a pas de format : noms, organisations, adresses, matricules, montants, noms de projets.
2. **Fusion.** En cas de chevauchement, les règles passent avant le modèle, puis la détection la plus longue et au score le plus élevé. Chaque valeur trouvée est propagée dans tout le texte. Les règles du projet passent avant le reste.
3. **Aperçu.** L'utilisateur voit les passages surlignés et peut en retirer ou en ajouter. Chaque correction est retenue pour les documents suivants.
4. **Remplacement.** Chaque valeur reçoit un jeton lisible (`PERSONNE_12`), stable dans la table. Les secrets deviennent `[SECRET_SUPPRIMÉ]` et ne sont jamais stockés.
5. **Retour.** Dans la réponse de l'IA, les jetons sont restaurés même s'ils ont été déformés (`Personne 12`, `PERSONNE-12`, `[PERSONNE_12]`). Les jetons inconnus sont laissés tels quels et signalés.

### Pseudonymiser ou caviarder

Le choix se fait au dépôt du document, avant l'analyse (et reste modifiable à l'export). Il vaut aussi pour un dossier entier.

| | Pseudonymiser | Caviarder |
|---|---|---|
| Ce que devient une donnée | Un jeton, par exemple `PERSONNE_1` | Une marque noire (`█████` ou rectangle noir) |
| Retour possible | Oui, avec la table | Non |
| Rangé dans la table | La valeur, chiffrée | Rien |
| Usage | Travailler avec une IA puis restaurer sa réponse | Transmettre un document à un tiers |

### Types de fichiers

| Fichier | Pseudonymisé | Caviardé |
|---|---|---|
| Texte (`.txt`, `.md`, `.csv`, `.log`, `.json`) | texte | texte |
| Word (`.docx`) | Word, mise en forme gardée, propriétés (auteur, société) vidées | Word, même chose |
| Excel (`.xlsx`) | Excel, un jeton par cellule, propriétés vidées | Excel, même chose |
| PDF de texte | Word neuf contenant le texte, sans la mise en page | PDF fait d'images, rectangles noirs sur les données |
| PDF scanné | Word neuf, à relire en entier | PDF fait d'images, rectangles noirs sur les données |
| Tampon, signature, mot manuscrit d'un PDF | non repris dans le Word | recouvert d'un rectangle noir |
| Anciens formats (`.doc`, `.xls`) | non lus, signalés | non lus, signalés |

Un PDF scanné est lu par la reconnaissance de caractères de Windows, sur le poste. Un PDF caviardé ne contient plus aucun texte : chaque page est rendue en image à 200 DPI, mise en page gardée.

## L'appli Windows

1. **Ouvrir** : choisir un mot de passe (table rangée dans `%LOCALAPPDATA%\Celodata`, liée au poste, protégée par Windows Hello si disponible).
2. **Déposer** : choisir le traitement (pseudonymiser ou caviarder) et le préréglage, puis glisser un fichier, le choisir ou coller un texte.
3. **Vérifier** : le document apparaît surligné, avec la liste classée par type à droite. Décocher ce qui peut rester, sélectionner du texte pour en masquer davantage. Pour un PDF, la vue « Pages » permet de contrôler ou tracer les zones graphiques (tampons, signatures).
4. **Exporter** : enregistrer le fichier ou copier le texte.
5. **Restaurer** : pour un document pseudonymisé, coller la réponse de l'IA dans l'onglet « Restaurer » ou y ouvrir le fichier qu'elle a rendu.

L'appli a cinq onglets :

| Onglet | Contenu |
|---|---|
| Protéger | Les trois étapes ci-dessus, plus le traitement d'un dossier entier (résultats dans `celodata_filtré` ou `celodata_caviardé`, originaux intacts). |
| Restaurer | Remet les vraies valeurs dans une réponse collée ou dans un fichier Word, Excel ou texte. |
| Dossier surveillé | Les documents déposés dans un dossier choisi sont analysés en tâche de fond (en mémoire) et attendent ici, prêts à vérifier. |
| Règles | Préréglages par métier, termes toujours/jamais masqués, motifs (regex), gestion de la table (déplacer vers un autre poste, changer le mot de passe, purger les anciennes valeurs). |
| Journal | Historique des traitements (décomptes par type et par origine, aucune vraie valeur) et export en CSV. |

> **Sans le modèle d'entités**, l'appli fonctionne avec les règles seules et l'indique dans le rail en bas à gauche (les noms propres ne sont alors pas détectés).

## La passerelle serveur

La passerelle expose le format OpenAI sur trois adresses uniquement : `POST /v1/chat/completions`, `GET /v1/models` et `GET /sante`.

1. Copier [docs/passerelle.exemple.toml](docs/passerelle.exemple.toml) sous le nom `passerelle.toml` et y mettre l'adresse de l'IA.
2. Mettre la clé de l'IA dans la variable d'environnement `CELODATA_CLE_IA`.
3. Créer un utilisateur (sa clé d'accès s'affiche une seule fois et sert aussi de mot de passe à sa table) :

```bash
uv run --extra passerelle celodata-passerelle utilisateur alice
```

4. Lancer le serveur :

```bash
uv run --extra modeles --extra passerelle celodata-passerelle servir
```

5. Dans votre outil de discussion (Open WebUI, LibreChat…), indiquer `http://127.0.0.1:8787/v1` et la clé de l'utilisateur.

À savoir :

- La clé de l'utilisateur n'est jamais transmise à l'IA : la passerelle la remplace par celle de l'entreprise.
- Les réponses en flux (SSE) sont restaurées au fil de l'eau, sans laisser passer de morceau de jeton.
- Les images et fichiers joints à une demande sont refusés, car ils ne peuvent pas être filtrés.
- Les tables ouvertes en mémoire expirent automatiquement après inactivité (`ttl_session`, 30 min par défaut).
- La passerelle ne gère pas le HTTPS elle-même : la placer derrière un reverse proxy (Caddy, Nginx…).

## Sécurité

| Sujet | Ce qui est fait |
|---|---|
| Table de correspondance | Fichier SQLite. Chaque valeur est chiffrée en AES-GCM (jeton authentifié en AAD). Les clés sont sous enveloppe chiffrée dérivée du mot de passe via Argon2id. |
| Lien au poste (appli Windows) | La clé d'enveloppe dépend aussi d'un secret protégé par Windows DPAPI (`.poste`). Une table copiée sur un autre poste ne s'ouvre pas, même avec le mot de passe. |
| Windows Hello (appli Windows) | Demandé après le mot de passe si le poste en a un. Barrière d'accès à l'appli (la protection cryptographique vient du mot de passe et de DPAPI). |
| Changer de poste / mot de passe | « Déplacer la table » crée une copie protégée par le mot de passe seul (liée au nouveau poste à l'ouverture). Le mot de passe se change dans l'onglet Règles sans rechiffrer les valeurs. |
| Mot de passe ou session perdus | Aucune récupération possible : la réidentification devient définitivement impossible. |
| Recherche de valeurs connues | Par empreinte HMAC : aucune valeur en clair dans la table. |
| Secrets (mots de passe, clés d'API) | Supprimés pour de bon, jamais rangés dans la table, jamais restaurés. |
| Journal | Décomptes seulement, nom de fichier chiffré. Exportable en CSV. |
| Réseau | L'appli n'ouvre aucune connexion sortante (`HF_HUB_OFFLINE=1`). La passerelle ne parle qu'à l'API configurée. |
| Fichiers Word et Excel | Auteur, société et autres propriétés vidés ; suivi des modifications et commentaires également filtrés dans Word. |

## Architecture, mesure et tests

Le moteur est une bibliothèque Python partagée par l'appli et la passerelle :

```
        Appli Windows                    Passerelle serveur
      (celodata/appli)                 (celodata/passerelle)
              │                                  │
              └────────────────┬─────────────────┘
                               ▼
                     Moteur (celodata/moteur.py)
   ┌─────────────┬─────────────┬──────────────┬─────────────┐
   │  Détection  │   Fichiers  │    Table     │   Journal   │
   │  detection/ │ documents.py│   table.py   │  journal.py │
   │             │ fichiers.py │   poste.py   │             │
   │             │ pdf.py/ocr  │              │             │
   └─────────────┴─────────────┴──────────────┴─────────────┘
```

<details>
<summary>Détail des fichiers du dépôt</summary>

| Fichier (dans `src/celodata`) | Rôle |
|---|---|
| `detection/base.py` | Contrat commun (`Detecteur`, `Detection`). |
| `detection/regles.py`, `regle.py`, `controles.py` | Règles françaises (`regex`) et clés de contrôle (Luhn, NIR, IBAN, TVA, IPv6). |
| `detection/listes.py` | Termes de santé et syndicat (article 9), rôles, fonctions uniques à signaler. |
| `detection/modeles.py` | Modèles d'entités locaux (GLiNER2-PII par défaut, interchangeable). |
| `detection/fusion.py` | Résolution des chevauchements, déclassement des génériques et propagation. |
| `moteur.py` | Analyse (avec protection anti-ReDoS), pseudonymisation, caviardage, restauration tolérante. |
| `table.py`, `poste.py` | Table chiffrée SQLite (Argon2id + AES-GCM + HMAC) et secret de poste DPAPI. |
| `prereglages.py`, `journal.py`, `suivi.py` | Préréglages par métier, journal chiffré, suivi d'avancement et annulation. |
| `documents.py`, `fichiers.py` | Lecture et filtrage/restauration avec mise en forme (Word, Excel, texte). |
| `pdf.py`, `ocr.py` | Lecture PDF (pdfium + OCR Windows), repérage tampons/signatures, caviardage en images. |
| `lot.py` | Traitement d'un dossier entier. |
| `appli/fenetre.py`, `api.py`, `hello.py`, `ecran.{html,css,js}` | Interface Windows (`pywebview`), Windows Hello et API locale. |
| `passerelle/relais.py`, `serveur.py` | Relais OpenAI (y compris streaming SSE) et serveur Starlette. |
| `mesure.py` | Évaluation d'un détecteur sur le jeu de test. |

Autres dossiers : [docs](docs/conception.md) (conception, cadrage CNIL, tutoriel), [jeu_de_test](jeu_de_test/README.md) (11 faux documents français annotés, aucune donnée réelle), `outils` (scripts d'essai), `tests` (suite `pytest`).

</details>

### Mesure et tests

Sur le jeu de test interne (11 faux documents français ; résultats indicatifs, voir [docs/conception.md](docs/conception.md)) : **100 % sur les formats fixes** (83/83) et **133/134 sur le texte libre** avec `celodata` (règles + GLiNER2-PII + fusion).

```bash
# Mesurer un détecteur sur le jeu de test
uv run --extra modeles celodata-mesure --details

# Lancer les vérifications (lint, syntaxe JS, tests)
uv run ruff check src tests outils
node --check src/celodata/appli/ecran.js
uv run pytest
```

## Limites connues

- Aucun détecteur ne trouve tout. L'aperçu de l'appli sert à rattraper ce qui est raté ; la passerelle n'a pas d'aperçu.
- Une personne peut rester reconnaissable par recoupement (fonction unique, lieu, date) même sans son nom. L'appli signale les fonctions uniques sans les masquer d'office.
- Une même personne écrite de deux façons (« Stéphane Girard » puis « Girard ») reçoit deux jetons distincts.
- Le jeu de test est petit (11 documents) : les chiffres mesurés ne valent que pour lui.
- Les images d'un Word ou d'un Excel ne sont pas filtrées (l'appli le signale).
- Le repérage des tampons et signatures sur PDF est approché : il peut prendre un logo ou manquer un tampon très pâle. La vue « Pages » sert à corriger.
- Le dossier surveillé n'est suivi que lorsque l'appli est ouverte, sans ses sous-dossiers.
- L'appli de bureau ne fonctionne que sous Windows (la passerelle et le moteur fonctionnent aussi sous Linux et macOS).

## Feuille de route et contribution

Chantiers à venir : installeur Windows (sans installation manuelle de Python/`uv`), évaluation d'ONNX Runtime pour alléger le modèle et accélérer l'inférence CPU, regroupement de variantes d'un même nom (« Prénom Nom » / « Nom »).

Les contributions sont les bienvenues sous licence Apache 2.0 : ajout de faux documents français au jeu de test (jamais de données réelles), signalement de faux négatifs ou faux positifs, amélioration des règles ou de l'interface.

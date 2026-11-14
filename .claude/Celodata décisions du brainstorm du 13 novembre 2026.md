# Celodata : décisions du brainstorm des 13 et 14 novembre 2026

Ce document complète « Celodata cadre CNIL et données à traiter.md ». Quand les deux se contredisent, c'est celui-ci qui fait foi (voir la section 7).

## 1. Le problème que Celodata doit régler

- Des entreprises interdisent l'IA (Claude, ChatGPT) par peur de la fuite de données.
- Leurs salariés la contournent : ils photographient l'écran avec leur téléphone et posent la question à ChatGPT, parce qu'ils n'ont pas d'IA sur leur poste de travail.
- Objectif : redonner confiance aux entreprises pour qu'elles autorisent l'IA, en leur donnant un filtre qui pseudonymise les données avant qu'elles n'atteignent l'IA.
- Le destinataire de l'outil est donc l'entreprise qui interdit, pas seulement le salarié.

## 2. Décisions de Céline

| Sujet | Décision |
|---|---|
| Logs HP NonStop | Pas une priorité. Céline ne veut pas en faire le cœur du projet. |
| Concurrence | Ne pas réinventer la roue. Le but est d'être utile, pas d'être unique. Réutiliser ce qui existe. |
| V1 | Interface graphique sur Windows uniquement. Pas de ligne de commande, pas de Mac ni de Linux au départ. |
| Seuil de 95 % | Abandonné. Il venait du modèle, pas de Céline. Remplacé par les mesures de la section 4. |
| Base technique | Presidio comme base de détection, avec le principe de Céline pour la réversibilité : jetons courts et cohérents, table de correspondance chiffrée qui reste sur la machine. |
| Deux produits | L'appli de bureau et la passerelle serveur sont deux produits différents, tous deux intéressants. |
| Passerelle serveur | Installable par l'entreprise, sur ses propres serveurs ou chez son hébergeur. |
| Ce qui intéresse le plus Céline | La partie « filtre » : ce qui se place entre les données et l'IA. |
| Approche générale | Réunir le meilleur de plusieurs outils existants plutôt que tout écrire. |
| Données indirectes | Les trois règles de la section 5 sont validées. |
| Accord de l'entreprise (DPO, RSSI) | Pas le sujet pour l'instant. Il faut d'abord un outil qui inspire confiance. |

## 3. Les deux produits

Les deux reposent sur le même moteur de détection et la même table de correspondance.

### Appli de bureau (premier produit)

La boucle en quatre gestes :

1. Je dépose un fichier ou je colle un texte.
2. Je vois ce qui a été détecté et je corrige.
3. Je récupère la version pseudonymisée pour l'IA.
4. Je colle la réponse de l'IA et je retrouve les vraies valeurs.

### Passerelle serveur (second produit)

- Elle se place entre les salariés et l'IA, et filtre tout ce qui passe.
- Elle remet les vraies valeurs dans la réponse avant de l'afficher.
- Elle réutilise le moteur de l'appli. Elle peut s'appuyer sur un outil existant (LiteLLM ou PrivAiTe) plutôt qu'être écrite de zéro.

### Propositions de Claude, pas encore tranchées

- Commencer par le moteur seul, sous forme de bibliothèque Python, puisque les deux produits en dépendent.
- Pour qu'un filtre ne puisse pas être contourné, Celodata devrait être la fenêtre de discussion elle-même, avec un panneau « ce que l'IA a vu ». Céline n'a pas validé cette forme.
- Une variante légère de l'appli : deux raccourcis clavier qui pseudonymisent puis réidentifient le presse-papier.
- Le MCP qui enveloppe les sources ne peut pas avoir d'aperçu humain. Deux options : ne servir que des fichiers déjà validés dans l'appli, ou filtrer en direct en mode strict.
- Ordre des profils : les documents (mails, contrats) parlent à plus de monde que les logs, mais les logs sont plus faciles à réussir.

## 4. Mesure de la détection

- **Formats fixes** (IP, mails, IBAN, NIR, SIRET, plaques) : 100 %.
- **Noms et texte libre** : compter les valeurs distinctes jamais détectées, pas les occurrences.
- **Deuxième passe** : chaque valeur déjà présente dans la table est recherchée littéralement dans tout le corpus. Un nom repéré une fois est masqué partout.
- Le chiffre cible pour les noms sera fixé quand un vrai jeu de test existera.

## 5. Données indirectes : les trois règles validées

Exemple : « la directrice du site de Lyon ». Principe : casser la combinaison plutôt que masquer la fonction, pour que l'IA comprenne toujours le rôle.

1. **Lieux et organisations toujours masqués** quand ils sont accolés à une fonction. Résultat : « la directrice du site de VILLE_1 ».
2. **Fonctions uniques signalées dans l'aperçu** (DRH, PDG, délégué syndical) : affichées « à vérifier », l'utilisateur décide.
3. **Données sensibles de l'article 9** (mandat syndical, santé) : masquées par défaut, pas seulement signalées.

Limites connues :

- Les combinaisons rares (« une infirmière de 54 ans habitant Morlaix ») ne sont pas réglées par ces règles. Un modèle de langage local en option pourrait aider. Le rapport de risque pour le DPO doit le dire.
- Si le fournisseur d'IA sait déjà de quelle entreprise vient le texte, la fonction seule peut suffire à identifier.

## 6. Résultats des tests

Test du 13 novembre sur un faux document français contenant 31 valeurs à masquer. Un seul document, une seule passe : c'est une tendance, pas une mesure.

| Outil | Valeurs entièrement masquées | Ce qu'il rate |
|---|---|---|
| GLiNER (`urchade/gliner_multi_pii-v1`) | 26 / 31 | SIRET, numéro client, noms de serveurs, un mail coupé en deux |
| PrivAiTe 0.8.2 (réglages par défaut) | 24 / 31 | plaque, BIC, numéro de contrat, un nom de serveur, le login sur une ligne, montant, nom de projet |
| Presidio en français (spaCy `fr_core_news_lg`) | 16 / 31 | NIR, SIRET, plaque, date de naissance en toutes lettres, numéros client et contrat, login, montant, projet, « Rose Petit » |
| CamemBERT NER (`Jean-Baptiste/camembert-ner`) | 11 / 31 | tout sauf les noms, organisations et lieux |
| spaCy français seul | 8 / 31 | pareil, plus « Rose Petit » |

Ce qu'on en retient :

- Aucun outil existant ne masque tout.
- Ce que GLiNER rate, ce sont des formats fixes, donc des règles simples. Ce que les règles ne peuvent pas trouver (noms, montants, projets), GLiNER le trouve. Règles françaises + GLiNER couvriraient a priori les 31 valeurs.
- Les règles françaises (NIR, SIRET, plaques, dates en toutes lettres) manquent partout : c'est la valeur ajoutée de Celodata.
- GLiNER repère aussi les fonctions (« directrice », « DRH », « responsable de la paie ») et les lieux associés, sans entraînement. Vérifié sur quatre phrases seulement.
- PrivAiTe est construit sur Presidio et LiteLLM, plus un modèle de détection d'OpenAI. L'aller-retour (filtrer puis restaurer) redonne le texte d'origine. Ses étiquettes sont souvent fausses (SIRET classé « téléphone », NIR classé « financier »).

Non testé :

- La passerelle LiteLLM elle-même (seul Presidio, qui fait sa détection, a été lancé).
- Les modèles de langage locaux (Mistral).
- Les fichiers de test sont restés dans un dossier temporaire et n'ont pas été copiés dans le dépôt.

## 7. Ce qui change dans le document de cadrage

| Dans le cadrage | Maintenant |
|---|---|
| V1 en ligne de commande et interface graphique, Windows, Mac et Linux | V1 en interface graphique sur Windows uniquement |
| Taux de détection de 95 % minimum | Remplacé par les mesures de la section 4 |
| Piste différenciante : logs EMS HP NonStop | Pas une priorité |
| Choix techniques laissés à Claude Code (langage, modèle) | Python, Presidio comme base, GLiNER comme modèle d'entités pressenti |
| Données indirectes listées comme « piège » sans solution | Trois règles validées (section 5) |
| Fonctionnement 100 % hors ligne, aucune connexion sortante | Reste vrai pour l'appli de bureau. À reformuler pour la passerelle : rien ne sort sauf le texte filtré, vers l'IA choisie par l'entreprise. Pas encore tranché. |

## 8. Modèles open source en français

- **GLiNER** : le meilleur du test. On lui donne en clair la liste des types à chercher. Tourne sans carte graphique.
- **CamemBERT NER** : entraîné sur du français, trouve tous les noms du test, mais ne connaît que trois types.
- **spaCy français** : très rapide, le plus faible sur les noms.
- **Mistral** : une partie des modèles est en poids ouverts sous licence Apache 2.0 et tourne en local sans API (avec Ollama, par exemple). D'autres sont sous licence restreinte ou accessibles seulement par l'API. La licence est à vérifier modèle par modèle. Rôle prévu : troisième couche en option, pour les cas ambigus et les combinaisons rares.

## 9. Outils existants repérés

Les descriptions viennent surtout des éditeurs eux-mêmes et n'ont pas été vérifiées, sauf pour Presidio et PrivAiTe.

- **Passerelles open source** : LiteLLM + Presidio, PrivAiTe, CloakPipe, Sentinel, Grepture.
- **Produits commerciaux** : Private AI / PrivateGPT, Protecto, Nightfall, Lakera (Check Point).
- **Côté français** : ELY (projet personnel), Tensoria (conseil), Cheops Technology (hébergement).
- Aucun produit français installable réunissant détection française, interface en français, journal pour DPO et aperçu n'a été trouvé. La recherche a été rapide.

## 10. Points ouverts pour la suite

- Commencer par le moteur seul, ou directement par l'appli ?
- Celodata comme fenêtre de discussion qui appelle l'IA : oui ou non ?
- Passerelle : repartir de PrivAiTe, de LiteLLM, ou la construire ?
- Profil de départ : logs ou documents ?
- Copier le faux document et les scripts de test dans le dépôt.
- Lire la version finale des lignes directrices CEPD (la consultation s'est terminée le 30 octobre 2026).
- Vérifier la clause de propriété intellectuelle du contrat de travail.

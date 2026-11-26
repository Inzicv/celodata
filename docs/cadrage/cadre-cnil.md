# Celodata : cadre CNIL et données à traiter

## 1. Ce que dit la CNIL

- **Pseudonymisation** : on remplace les identifiants directs (nom, prénom...) par des alias ou numéros. On ne peut plus rattacher la donnée à une personne sans information supplémentaire (la clé).
- **Une donnée pseudonymisée reste une donnée personnelle** : le RGPD et la loi Informatique et Libertés continuent de s'appliquer.
- **L'anonymisation est irréversible** : c'est la seule qui fait sortir la donnée du RGPD.
- **Pas d'obligation générale d'anonymiser** dans le RGPD, mais la pseudonymisation est une mesure recommandée pour limiter les risques.
- **IA générative grand public** : la CNIL recommande de ne jamais y partager de données personnelles ou confidentielles.
- **Développement d'IA** : anonymiser à bref délai, ou à défaut pseudonymiser.
- **Associer le DPO** au choix et à l'évaluation des techniques.
- **CEPD, 7 juillet 2026** : nouvelles lignes directrices européennes sur l'anonymisation, à lire en détail.

## 2. Les trois critères d'une vraie anonymisation (CEPD)

- **Individualisation** : impossible d'isoler une personne
- **Corrélation** : impossible de relier deux jeux de données sur la même personne
- **Inférence** : impossible de déduire une info sur une personne

## 2 bis. Lignes directrices CEPD du 7 juillet 2026 : ce que ça change pour Celodata

L'anonymat se juge **par rapport à celui qui détient la donnée** : la même donnée peut être anonyme pour l'un et identifiable pour l'autre.

- **Définition** : une donnée est anonyme si elle ne concerne pas une personne identifiée ou identifiable. Le lien peut venir du contenu, de la finalité ou des effets de l'information.
- **Identifiable** = on peut distinguer la personne des autres dans un contexte précis, avec des moyens raisonnablement susceptibles d'être utilisés.
- **Approche contextuelle** : on évalue les capacités de chaque acteur. L'entreprise qui garde la clé fait de la pseudonymisation. Pour le fournisseur d'IA sans clé, on pourrait défendre un anonymat, à condition qu'aucun indice indirect ne reste.
- **Approche simplifiée** : on ignore ces différences et on traite la donnée comme non anonyme. Plus prudente, plus simple à défendre.
- **Test en 3 critères** : pas d'individualisation, pas de corrélation, pas d'inférence. Si un critère échoue, analyse approfondie.
- **Idée produit** : générer un rapport de risque sur ces 3 critères pour le DPO.
- **Statut** : texte soumis à consultation publique jusqu'au 30 octobre 2026, version finale à surveiller. Ne pas vendre l'outil comme garantissant l'anonymat.

Sources : [article CNIL](https://www.cnil.fr/fr/cepd-ia-generative-chaines-blocs), [lignes directrices CEPD (PDF)](https://www.edpb.europa.eu/system/files/2026-07/edpb_guidelines_202602_anonymisation_v1_en_0.pdf)

## 3. Les trois modes de l'outil

- **Pseudonymiser** : réversible avec la clé, pour réidentifier après le traitement IA
- **Anonymiser** : définitif, aucune table de correspondance conservée
- **Supprimer** : la donnée est retirée

## 4. Données communes à tous les métiers

- Noms, prénoms
- Adresses mail
- Numéros de téléphone
- Adresses postales
- IBAN, BIC
- Dates de naissance
- Numéro de sécurité sociale (NIR)
- Numéros de pièces d'identité
- SIRET, SIREN (quand ils identifient un indépendant)
- Numéros client, numéros de contrat, numéros de dossier
- Plaques d'immatriculation

## 5. Données spécifiques aux logs informatiques

- Adresses IP (v4 et v6), adresses MAC
- Noms de machines, hostnames, noms de domaine internes
- Chemins réseau et chemins de fichiers (UNC, montages, volumes)
- Identifiants et logins utilisateurs
- Mots de passe, tokens, clés API, secrets (à supprimer, jamais pseudonymiser)
- Noms de bases, de files MQ, de serveurs applicatifs
- URL internes avec paramètres
- Numéros de compte ou de transaction présents dans les messages
- Noms de clients dans les messages

## 5 bis. Formats de logs de la première version

- Texte ligne par ligne (syslog, logs applicatifs)
- JSON
- CSV
- Logs web Apache et Nginx
- **Règles maison** dans un fichier de config : chacun ajoute les formats et motifs de son client sans toucher au code
- Piste différenciante : logs EMS HP NonStop
- **Préserver le format** : une IP devient une fausse IP, un chemin réseau un faux chemin, pour que l'IA comprenne toujours la structure
- **Cohérence** : la même valeur donne toujours le même jeton dans un projet

## 5 ter. Clé et table de correspondance

- Une **table de correspondance** jeton vers valeur réelle, qui ne quitte jamais la machine
- Table **chiffrée**, une par client ou par projet
- Déverrouillage par mot de passe ou trousseau du système ; coffre-fort de clés d'entreprise en option plus tard
- **Durée de vie paramétrable** : suppression automatique de la table après une durée choisie (décision de Céline)
- Table détruite = réidentification impossible

## 5 quater. Architecture et points d'entrée

Un seul moteur local, deux points d'entrée, tous deux dans le périmètre du projet.

**Moteur de détection en 3 couches**

1. **Règles et regex** : données à format fixe (IP, mails, IBAN, NIR, chemins, hostnames). Rapide et fiable.
2. **Modèle de détection d'entités local** (pistes : GLiNER, spaCy français) : noms et organisations dans le texte libre. Tourne sur un PC grand public.
3. **Petit LLM local en option** (via Ollama) : cas ambigus uniquement, plus lent et moins prévisible.

**Point d'entrée 1 : appli fichiers et dossiers**

- Traite un fichier seul ou un dossier complet
- Garde l'arborescence et les noms de fichiers (pseudonymisés si besoin)
- Mêmes jetons sur tous les fichiers d'un même projet
- Chemin retour : on redonne à l'appli le résultat produit par l'IA (rapport, analyse), elle réidentifie avec la clé

**Point d'entrée 2 : MCP qui enveloppe les sources**

- Se place entre les sources de données (bases, fichiers, outils) et le modèle
- Filtre ce qui sort des sources avant que l'IA le voie
- Règle impérative : le modèle n'a jamais d'accès direct à la source brute, sinon le filtrage ne sert à rien
- Un MCP appelé par le modèle pour anonymiser un texte qu'il a déjà lu ne protège rien

**Ordre de construction conseillé pour Claude Code**

1. Moteur + appli fichiers et dossiers
2. Réidentification et gestion des tables
3. MCP enveloppe des sources

## 5 quinquies. Profil PME

Deuxième profil métier dès le départ, à côté des logs informatiques.

- **Documents visés** : factures, contrats, fichiers clients, dossiers RH, rapports financiers, documents internes en général
- **Formats de fichiers** : Word, PDF, Excel, mails, beaucoup de texte libre (détection plus difficile que dans les logs)
- **Dossiers RH** : peuvent contenir des données sensibles au sens de l'article 9 du RGPD (santé, syndicat...), à traiter avec un niveau de prudence renforcé
- **Rapports financiers** : le sensible est souvent du secret des affaires (montants, noms de clients, projets), pas des données personnelles
- Décision : option au choix pour pseudonymiser aussi les données confidentielles non personnelles (montants, noms de projets). Point à cadrer : préserver les ordres de grandeur pour que l'IA puisse encore calculer.

### Montants et calculs (exemple : KPI 2027 à partir d'un rapport financier)

Problème : un KPI est un nouveau chiffre calculé par l'IA, absent de la table de correspondance, donc impossible à réidentifier par simple remplacement.

- **Mode principal, les formules** : l'IA rend la méthode de calcul (ex : marge = chiffre d'affaires moins charges) avec les jetons des montants ; l'appli refait le calcul en local avec les vrais chiffres.
- **Consigne automatique** : l'appli ajoute elle-même au fichier préparé l'instruction de rendre les résultats sous forme de formules, avec un format de réponse imposé pour pouvoir les relire et recalculer automatiquement. On ne compte pas sur l'utilisateur pour y penser.
- **Option rapide, le facteur secret** : tous les montants multipliés par un même nombre caché. Ratios, marges et taux de croissance restent justes ; les totaux sont redivisés au retour. Limites : casse les seuils fixes (tranches d'impôt...) et un seul montant réel connu révèle le facteur.

### Gabarits par zones (tout document répétitif : factures, bulletins, bons de commande...)

- Idée de Céline : l'utilisateur charge un document modèle (ex : une facture PDF) et dessine les zones à masquer
- Le gabarit s'applique ensuite à tous les documents du même type (même fournisseur, même mise en page)
- PDF scannés : reconnaissance de texte (OCR) nécessaire
- Le texte sous la zone doit être réellement supprimé, pas seulement recouvert d'un rectangle noir (sinon récupérable par copier-coller)

## Aperçu avant envoi

## Décisions prises

- **Aperçu obligatoire** avant tout envoi à l'IA (décision de Céline) : éléments détectés surlignés, ajout d'un élément oublié, retrait d'un faux positif
- Proposition pour les gros dossiers : vue résumée des éléments détectés regroupés par type (ex : 47 IP, 12 noms, 3 IBAN), validation globale, ouverture d'un fichier en détail au besoin
- Proposition : chaque correction devient une règle réutilisée sur tout le projet

### Score de fiabilité

- Idée de Céline : une **notation de la fiabilité** de chaque détection
- Les règles et regex donnent une confiance quasi certaine ; le modèle d'entités fournit une probabilité
- L'aperçu affiche d'abord les détections douteuses, avec un seuil réglable
- Limite à afficher clairement : le score ne porte que sur ce qui a été détecté. Un élément raté n'a pas de score, donc un document « tout vert » ne garantit pas qu'aucune donnée ne fuit

## Règles personnalisées

L'utilisateur peut ajouter ses propres règles, pour tous les profils (décision de Céline).

- **Liste noire** : termes toujours masqués (noms de clients, de projets, de serveurs)
- **Liste blanche** : termes jamais masqués (nom de sa propre entreprise, termes techniques)
- **Motifs** (regex) pour les utilisateurs techniques
- Création possible depuis l'interface graphique, sans écrire de regex
- **Export, import et partage** des règles par client ou par projet, pour les collègues

## Journal de traçabilité

L'appli tient un journal d'activité conforme, présentable à un DPO (décision de Céline).

- **Contient** : date et heure, utilisateur, fichier traité, mode (pseudonymiser, anonymiser, supprimer), nombre d'éléments masqués par type, règles appliquées, scores de fiabilité, réidentifications effectuées, version de l'outil
- **Ne contient jamais** : les vraies valeurs ni la table de correspondance
- Durée de conservation du journal paramétrable
- Export d'un rapport lisible pour le DPO

## Modes de déploiement

Deux versions (décision de Céline) : une uniquement locale, une installable sur un serveur interne.

- **Version locale** : un poste, une personne, tables stockées sur la machine
- **Version serveur interne** : tables partagées entre collègues, comptes utilisateurs, droits (qui peut pseudonymiser, qui peut réidentifier), toujours sans connexion vers l'extérieur
- Risque : un serveur qui centralise toutes les clés devient une cible prioritaire, sécurité à renforcer
- Ordre conseillé : version locale d'abord, version serveur ensuite

* **Infra hébergée** : le « serveur interne » peut être un serveur loué chez un hébergeur (OVH, Scaleway...). Dans ce cas, « hors ligne » signifie aucune connexion en dehors de l'infrastructure de l'entreprise
* Point souveraineté : un hébergeur soumis au droit américain (Cloud Act) pose question ; choix laissé à l'entreprise, à mentionner dans la documentation

## Version minimale (V1)

Ce qui doit exister pour présenter Celodata aux collègues (validé par Céline).

1. Appli locale, en ligne de commande **et** interface graphique
2. Profil logs informatiques
3. Pseudonymisation avec table de correspondance chiffrée
4. Aperçu avant envoi
5. Réidentification au retour

Ensuite : profil PME, gabarits par zones, MCP enveloppe des sources, version serveur.

Nom du projet : **Celodata** (aucun dépôt GitHub du même nom trouvé ; noms proches : CelerData, Celo).

## Critères de réussite

- **Jeu de test** : faux logs et faux documents générés, avec des données identifiantes connues cachées dedans
- **Taux de détection** : 95 % minimum sur l'ensemble (décision de Céline)
- Décision : 100 % sur les données à format fixe (IP, mails, IBAN, NIR, chemins)
- Suivre aussi le taux de faux positifs, pour que l'aperçu reste utilisable
- Réidentification : le retour doit restituer exactement les valeurs d'origine

## Exigences techniques critiques

- **Jetons modifiés par l'IA** : l'IA peut réécrire un jeton (ex : IP\_12 devient IP-12 ou IP 12) et casser la réidentification. Prévoir un format de jeton robuste et signaler au retour les jetons inconnus ou altérés.
- **Perte de la clé** : sans clé, réidentification impossible. Décision de Céline : aucune récupération possible, c'est voulu. L'appli doit avertir clairement l'utilisateur avant.
- **Fuites par l'appli elle-même** : fichiers temporaires, presse-papier, journaux d'erreurs, rapports de plantage. Rien de réel ne doit traîner sur le disque.
- **Secrets** (mots de passe, tokens, clés API) : toujours supprimés, jamais pseudonymisés.
- **Gros volumes** : logs de plusieurs Go, traitement en flux sans tout charger en mémoire.
- **Ré-identification indirecte** : messages libres dans les logs, combinaisons rares, horodatages.
- **Choix techniques** laissés à Claude Code : langage, modèle de détection, framework d'interface.
- **Juridique** : clause de propriété intellectuelle du contrat de travail à vérifier.

## Idées complémentaires retenues

- **Bibliothèque de règles communautaire** sur le GitHub : chacun partage ses règles par type de logs (NonStop, SAP, Oracle...)
- **Mode « tuyau » en ligne de commande** : la sortie d'une commande passe directement dans Celodata, sans fichier intermédiaire
- **Comparatif avec Microsoft Presidio** sur le même jeu de faux logs et documents français, pour démontrer l'avantage sur le français

* **Confiance** : versions signées sur GitHub et une page expliquant comment signaler une faille de sécurité

- Deux points d'entrée dans le périmètre : appli fichiers et dossiers, MCP qui enveloppe les sources
- Deux profils au départ : logs informatiques et PME
- Appli en ligne de commande et interface graphique
- Windows, Mac et Linux
- Projet perso open source sur GitHub, présenté ensuite aux collègues de Capgemini
- Durée de vie des tables de correspondance paramétrable
  - Fonctionnement 100 % hors ligne : aucune connexion sortante, modèles téléchargés à l'installation, mises à jour manuelles
- Tests uniquement avec de faux logs et faux documents générés, jamais de vraies données client
- Licence : Apache 2.0
  - Interface, documentation et détection en français (positionnement souverain assumé) ; README en français et en anglais
- À vérifier : clause de propriété intellectuelle du contrat de travail

## 6. Données indirectes (le piège)

- Fonctions précises ("la directrice du site de Lyon")
- Combinaisons rares : âge + ville + métier
- Horodatages croisés avec un planning

## 7. Points ouverts

- Lire les lignes directrices CEPD de juillet 2026
- Choix du stockage et de la protection de la clé de réidentification
- Liste des formats de logs à supporter en premier

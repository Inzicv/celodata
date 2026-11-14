# Jeu de test

Dix faux documents français, avec la liste des valeurs qui doivent être masquées dans chacun.

Toutes les données sont inventées. Les IBAN, numéros de sécurité sociale et SIRET ont une clé de contrôle valide pour que les règles de détection puissent les vérifier, mais ils ne correspondent à personne. Ne jamais ajouter ici de vraies données.

## Format

Chaque document est un fichier `.txt`, accompagné d'un fichier `.json` du même nom :

```json
[
  {"categorie": "nom", "valeur": "Rose Petit"},
  {"categorie": "telephone", "valeur": "06 01 02 03 04"}
]
```

La valeur doit apparaître telle quelle dans le texte. Elle est considérée comme masquée seulement si toutes ses occurrences sont entièrement couvertes par des détections.

## Catégories

| Famille | Catégories | Objectif |
|---|---|---|
| Formats fixes | `telephone`, `mail`, `nir`, `iban`, `bic`, `siret`, `plaque`, `identifiant`, `ip`, `machine` | 100 %, par des règles |
| Texte libre | `nom`, `organisation`, `adresse`, `lieu`, `date_naissance`, `date`, `login`, `secret`, `montant`, `projet`, `sante`, `syndicat` | à fixer quand le moteur existera |

`lieu` désigne un lieu accolé à une fonction (« la directrice du site de Lyon ») : le masquer suffit à casser la combinaison qui identifie la personne.

`sante` et `syndicat` sont des données sensibles au sens de l'article 9 du RGPD.

## Documents

| Fichier | Ce qu'il met à l'épreuve |
|---|---|
| `01_courrier_client` | courrier administratif, extrait de log, noms qui sont aussi des mots courants |
| `02_mail_paie` | noms en majuscules ou tout en minuscules, santé, syndicat |
| `03_facture` | tableau de montants, SIRET, TVA, IBAN |
| `04_contrat_travail` | phrases juridiques longues, numéros sans espaces |
| `05_compte_rendu_reunion` | prénoms seuls, initiales, fonctions accolées à un lieu |
| `06_mail_reclamation` | texte sans majuscules, téléphones sans séparateurs |
| `07_fichier_clients` | fichier à colonnes séparées par des points-virgules |
| `08_cv` | organisations nombreuses, adresse, lien de profil |
| `09_ticket_support` | logs, IPv4, IPv6, adresse MAC, logins, secrets |
| `10_note_rh` | données sensibles de l'article 9 |

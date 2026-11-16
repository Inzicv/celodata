"""Fusion des détections venues des règles et du modèle d'entités.

1. Les chevauchements sont réglés : les règles passent avant le modèle, puis la détection
   la plus longue, puis le score le plus élevé.
2. Chaque valeur retenue est recherchée littéralement dans tout le texte, pour rattraper
   les occurrences qu'un détecteur a vues une fois et ratées ailleurs.
"""

import re
from dataclasses import replace

from celodata.detection.base import Detecteur, Detection

SOURCE_REGLES = "regles"
SOURCE_PROPAGATION = "propagation"

# Types dont la valeur n'est pas recherchée ailleurs : trop courts ou trop communs.
_SANS_PROPAGATION = frozenset({"DATE", "DATE_NAISSANCE", "DATE_LOI", "DUREE", "AGE", "MONTANT", "SANTE", "SYNDICAT"})
_LONGUEUR_MIN_PROPAGATION = 4


# Un nom d'organisation, de lieu ou de projet sans majuscule ni chiffre est un terme générique
# (« l'organisme de formation », « grande échelle ») : il est rangé à part, pour rester en clair.
_GENERIQUES = frozenset({"ORGANISATION", "VILLE", "PROJET"})
TYPE_GENERIQUE = "COMMUN"
_ARTICLE = re.compile(
    r"^(?:l['’]|les? |la |une? |des? |du |d['’]|aux? |ses? |son |sa |leurs? |notre |nos |votre |vos |ce |cet |cette |ces )+",
    re.IGNORECASE,
)


# Des mots ordinaires : lettres, espaces, apostrophes et traits d'union, sans chiffre ni signe.
_MOTS = re.compile(r"[^\W\d_]+(?:[ '’-][^\W\d_]+)*")


def _sans_majuscules(texte: str) -> bool:
    """Vrai pour un texte écrit sans majuscules : on ne peut alors rien conclure d'un nom en minuscules."""
    lettres = [c for c in texte if c.isalpha()]
    return sum(c.isupper() for c in lettres) < len(lettres) / 100


def declasser(texte: str, detections: list[Detection]) -> list[Detection]:
    """Range en « terme générique » ce que le modèle a pris pour un nom propre sans majuscule."""
    if _sans_majuscules(texte):
        return detections
    sortie = []
    for d in detections:
        valeur = texte[d.debut : d.fin]
        if d.source != SOURCE_REGLES and d.type in _GENERIQUES:
            nom = _ARTICLE.sub("", valeur)
            if _MOTS.fullmatch(nom) and not any(c.isupper() for c in nom):
                d = replace(d, type=TYPE_GENERIQUE)
        elif d.source != SOURCE_REGLES and d.type == "ROLE" and not _MOTS.fullmatch(valeur):
            # « svc_backup » n'est pas un métier : ce qui ressemble à un identifiant reste un identifiant.
            d = replace(d, type="LOGIN")
        sortie.append(d)
    return sortie


def regler_chevauchements(detections: list[Detection]) -> list[Detection]:
    ordre = sorted(
        detections,
        key=lambda d: (d.source != SOURCE_REGLES, -(d.fin - d.debut), -d.score, d.debut),
    )
    retenues: list[Detection] = []
    for d in ordre:
        if d.fin > d.debut and all(d.fin <= r.debut or d.debut >= r.fin for r in retenues):
            retenues.append(d)
    return sorted(retenues, key=lambda d: d.debut)


def propager(texte: str, detections: list[Detection]) -> list[Detection]:
    """Ajoute les autres occurrences des valeurs déjà détectées.

    Une valeur d'un seul mot est recherchée à l'identique, pour ne pas masquer « rose » parce
    que « Rose » est un prénom. Une valeur de plusieurs mots est recherchée sans tenir compte
    de la casse (« NGUYEN Thi Lan » et « nguyen thi lan »).
    """
    ajouts = []
    vues = set()
    for d in detections:
        valeur = texte[d.debut : d.fin].strip()
        if d.type in _SANS_PROPAGATION or len(valeur) < _LONGUEUR_MIN_PROPAGATION or valeur in vues:
            continue
        vues.add(valeur)
        casse = re.IGNORECASE if re.search(r"\s", valeur) else 0
        for m in re.finditer(rf"(?<![\w-]){re.escape(valeur)}(?![\w-])", texte, casse):
            ajouts.append(Detection(m.start(), m.end(), d.type, d.score, SOURCE_PROPAGATION))
    # Les détections d'origine passent avant leurs copies.
    retenues = list(detections)
    for a in sorted(ajouts, key=lambda d: -(d.fin - d.debut)):
        if all(a.fin <= r.debut or a.debut >= r.fin for r in retenues):
            retenues.append(a)
    return sorted(retenues, key=lambda d: d.debut)


class DetecteurCompose:
    """Fait tourner plusieurs détecteurs et fusionne leurs résultats."""

    def __init__(self, nom: str, detecteurs: list[Detecteur]) -> None:
        self.nom = nom
        self._detecteurs = detecteurs

    def detecter(self, texte: str) -> list[Detection]:
        detections = [d for detecteur in self._detecteurs for d in detecteur.detecter(texte)]
        return propager(texte, regler_chevauchements(declasser(texte, detections)))

"""Fusion des détections venues des règles et du modèle d'entités.

1. Les chevauchements sont réglés : les règles passent avant le modèle, puis la détection
   la plus longue, puis le score le plus élevé.
2. Chaque valeur retenue est recherchée littéralement dans tout le texte, pour rattraper
   les occurrences qu'un détecteur a vues une fois et ratées ailleurs.
"""

import re

from celodata.detection.base import Detecteur, Detection

SOURCE_REGLES = "regles"
SOURCE_PROPAGATION = "propagation"

# Types dont la valeur n'est pas recherchée ailleurs : trop courts ou trop communs.
_SANS_PROPAGATION = frozenset({"DATE", "DATE_NAISSANCE", "MONTANT", "SANTE", "SYNDICAT"})
_LONGUEUR_MIN_PROPAGATION = 4


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
        return propager(texte, regler_chevauchements(detections))

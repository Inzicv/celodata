"""Contrat commun à tous les détecteurs.

Le moteur ne connaît que ce contrat : changer de modèle revient à changer de détecteur,
sans toucher au reste.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Detection:
    """Un passage du texte à masquer. `debut` et `fin` sont des positions de caractères."""

    debut: int
    fin: int
    type: str
    score: float
    source: str


class Detecteur(Protocol):
    nom: str

    def detecter(self, texte: str) -> list[Detection]: ...


def blocs(texte: str) -> Iterator[tuple[int, str]]:
    """Découpe le texte en lignes non vides, avec la position de chacune.

    Les modèles d'entités ont une longueur d'entrée limitée : on leur donne une ligne à la fois.
    """
    position = 0
    for ligne in texte.split("\n"):
        if ligne.strip():
            yield position, ligne
        position += len(ligne) + 1

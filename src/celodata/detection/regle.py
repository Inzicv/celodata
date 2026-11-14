"""Description d'une règle de détection, indépendante de Presidio."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Regle:
    nom: str
    type: str
    motif: str
    score: float
    # Rend True, False ou None (voir controles.py). Une clé juste porte le score à 1.
    validation: Callable[[str], bool | None] | None = None
    ignorer_casse: bool = False

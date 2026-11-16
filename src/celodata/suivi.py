"""Suivi d'un travail long : où il en est, et de quoi l'arrêter.

Les boucles longues (pages d'un PDF, blocs de texte donnés au modèle) passent par `parcourir`.
Celui qui lance le travail pose un rappel avec `suivre` : il reçoit l'étape et l'avancement,
et lève `Annule` pour arrêter. Le rappel est propre au fil qui l'a posé : un travail de fond
(dossier surveillé, dossier entier) n'est ni suivi ni arrêté par celui de l'écran.
"""

import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

Rappel = Callable[[str, int, int], None]

_fil = threading.local()


class Annule(Exception):
    """Le travail en cours a été arrêté à la demande de l'utilisateur."""


@contextmanager
def suivre(rappel: Rappel) -> Iterator[None]:
    ancien = getattr(_fil, "rappel", None)
    _fil.rappel = rappel
    try:
        yield
    finally:
        _fil.rappel = ancien


def pas(etape: str, fait: int, total: int) -> None:
    rappel = getattr(_fil, "rappel", None)
    if rappel is not None:
        rappel(etape, fait, total)


def parcourir[T](etape: str, elements: Iterable[T]) -> Iterator[T]:
    """Rend les éléments un à un, en signalant l'avancement avant chacun."""
    if getattr(_fil, "rappel", None) is None:
        yield from elements
        return
    elements = list(elements)
    for numero, element in enumerate(elements):
        pas(etape, numero, len(elements))
        yield element
    pas(etape, len(elements), len(elements))

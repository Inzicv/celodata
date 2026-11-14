"""Remplacement des valeurs par des jetons, puis restauration dans la réponse de l'IA.

Un jeton s'écrit `PERSONNE_12`. Au retour, on reconnaît aussi les formes qu'une IA produit
en le recopiant : `Personne 12`, `PERSONNE-12`, `[PERSONNE_12]`, `**personne_12**`.

Les secrets (mots de passe, clés) ne reçoivent pas de jeton : ils sont supprimés pour de bon.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from celodata.detection.base import Detecteur, Detection
from celodata.table import Table

TYPE_SECRET = "SECRET"
MARQUE_SECRET = "[SECRET_SUPPRIMÉ]"

_FORME_EXACTE = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z_]*)_(\d+)(?!\d)")


@dataclass
class Filtrage:
    texte: str
    # Nombre de passages remplacés par type. Aucune vraie valeur ici.
    par_type: Counter = field(default_factory=Counter)


@dataclass
class Restauration:
    texte: str
    # Jetons bien formés mais absents de la table : inventés par l'IA, ou table purgée.
    inconnus: list[str] = field(default_factory=list)
    # Jetons reconnus sous une forme déformée. À montrer à l'utilisateur pour vérification.
    approximatifs: list[str] = field(default_factory=list)


def analyser(texte: str, detecteur: Detecteur, table: Table) -> list[Detection]:
    """Détecte, puis applique la mémoire du projet.

    - Les valeurs que l'utilisateur a démasquées ne sont plus proposées.
    - Les valeurs déjà dans la table sont recherchées littéralement dans tout le texte.
    """
    detections = [
        d for d in detecteur.detecter(texte) if not table.est_ignoree(texte[d.debut : d.fin])
    ]
    connues = sorted(table.valeurs(), key=lambda tv: -len(tv[1]))
    for type_, valeur in connues:
        if len(valeur) < 3 or table.est_ignoree(valeur):
            continue
        for m in re.finditer(rf"(?<![\w-]){re.escape(valeur)}(?![\w-])", texte):
            if all(m.end() <= d.debut or m.start() >= d.fin for d in detections):
                detections.append(Detection(m.start(), m.end(), type_, 1.0, "table"))
    return sorted(detections, key=lambda d: d.debut)


def pseudonymiser(texte: str, detections: list[Detection], table: Table) -> Filtrage:
    """Remplace chaque passage détecté par son jeton. Les détections ne doivent pas se chevaucher."""
    resultat = Filtrage(texte)
    morceaux = []
    position = 0
    for d in sorted(detections, key=lambda d: d.debut):
        if d.debut < position:
            raise ValueError("Les détections se chevauchent : passer d'abord par la fusion.")
        morceaux.append(texte[position : d.debut])
        if d.type == TYPE_SECRET:
            morceaux.append(MARQUE_SECRET)
        else:
            morceaux.append(table.jeton(d.type, texte[d.debut : d.fin]))
        resultat.par_type[d.type] += 1
        position = d.fin
    morceaux.append(texte[position:])
    resultat.texte = "".join(morceaux)
    return resultat


def _motif_tolerant(types: list[str]) -> re.Pattern | None:
    if not types:
        return None
    # DATE_NAISSANCE accepte « date naissance », « Date-Naissance », « DATE_NAISSANCE ».
    formes = sorted((t.replace("_", "[ _-]?") for t in types), key=len, reverse=True)
    return re.compile(
        rf"(?<![A-Za-z0-9_\[])(\[)?({'|'.join(formes)})[ _\-]{{0,2}}(\d+)(?!\d)(?(1)\])",
        re.IGNORECASE,
    )


def restaurer(texte: str, table: Table) -> Restauration:
    """Remet les vraies valeurs à la place des jetons, même déformés."""
    resultat = Restauration(texte)
    types = {re.sub(r"[ _-]", "", t).upper(): t for t in table.types()}

    def remplacer(m: re.Match) -> str:
        type_ = types[re.sub(r"[ _-]", "", m.group(2)).upper()]
        jeton = f"{type_}_{int(m.group(3))}"
        valeur = table.valeur(type_, int(m.group(3)))
        if valeur is None:
            return m.group(0)
        if m.group(0) not in (jeton, f"[{jeton}]"):
            resultat.approximatifs.append(m.group(0))
        return valeur

    motif = _motif_tolerant(list(types.values()))
    if motif:
        resultat.texte = motif.sub(remplacer, texte)
    # Ce qui ressemble encore à un jeton après restauration n'est pas dans la table.
    connus = set(types.values())
    for m in _FORME_EXACTE.finditer(resultat.texte):
        if m.group(1) in connus and m.group(0) not in resultat.inconnus:
            resultat.inconnus.append(m.group(0))
    return resultat

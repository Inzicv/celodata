"""Remplacement des valeurs par des jetons, puis restauration dans la réponse de l'IA.

Un jeton s'écrit `PERSONNE_12`. Au retour, on reconnaît aussi les formes qu'une IA produit
en le recopiant : `Personne 12`, `PERSONNE-12`, `[PERSONNE_12]`, `**personne_12**`.

Les secrets (mots de passe, clés) ne reçoivent pas de jeton : ils sont supprimés pour de bon.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from celodata.detection.base import Detecteur, Detection
from celodata.prereglages import retenir
from celodata.table import Table

TYPE_SECRET = "SECRET"
MARQUE_SECRET = "[SECRET_SUPPRIMÉ]"
# Caviardage : toujours la même marque, pour ne pas laisser deviner la longueur de ce qui est caché.
MARQUE_CAVIARD = "█████"

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


def _libre(debut: int, fin: int, detections: list[Detection]) -> bool:
    return all(fin <= d.debut or debut >= d.fin for d in detections)


def _regles_projet(texte: str, table: Table) -> list[Detection]:
    """Applique les règles ajoutées par l'utilisateur : termes toujours masqués et motifs."""
    trouvees = []
    for regle in table.regles():
        try:
            if regle["genre"] == "terme":
                motif = re.compile(rf"(?<![\w-]){re.escape(regle['texte'])}(?![\w-])", re.IGNORECASE)
            else:
                motif = re.compile(regle["texte"])
        except re.error:
            continue
        trouvees += [
            Detection(m.start(), m.end(), regle["type"], 1.0, "projet")
            for m in motif.finditer(texte)
            if m.end() > m.start()
        ]
    retenues: list[Detection] = []
    # La règle la plus longue l'emporte.
    for d in sorted(trouvees, key=lambda d: (d.debut - d.fin, d.debut)):
        if _libre(d.debut, d.fin, retenues):
            retenues.append(d)
    return retenues


def analyser(
    texte: str, detecteur: Detecteur, table: Table, en_clair: frozenset[str] = frozenset()
) -> list[Detection]:
    """Détecte, puis applique la mémoire du projet.

    `en_clair` : les catégories que le préréglage laisse en clair. Leurs passages ne sont pas rendus.

    - Les règles du projet passent avant le détecteur.
    - Les valeurs que l'utilisateur a démasquées ne sont plus proposées.
    - Les valeurs déjà dans la table sont recherchées littéralement dans tout le texte.
    """
    detections = _regles_projet(texte, table)
    detections += [d for d in detecteur.detecter(texte) if _libre(d.debut, d.fin, detections)]
    detections = [d for d in detections if not table.est_ignoree(texte[d.debut : d.fin])]
    connues = sorted(table.valeurs(), key=lambda tv: -len(tv[1]))
    for type_, valeur in connues:
        if len(valeur) < 3 or table.est_ignoree(valeur):
            continue
        for m in re.finditer(rf"(?<![\w-]){re.escape(valeur)}(?![\w-])", texte):
            if _libre(m.start(), m.end(), detections):
                detections.append(Detection(m.start(), m.end(), type_, 1.0, "table"))
    return sorted(retenir(detections, en_clair), key=lambda d: d.debut)


Remplacement = tuple[int, int, str]  # début, fin, texte à mettre à la place


def appliquer(texte: str, remplacements: list[Remplacement]) -> str:
    morceaux, position = [], 0
    for debut, fin, nouveau in remplacements:
        morceaux += [texte[position:debut], nouveau]
        position = fin
    return "".join([*morceaux, texte[position:]])


def remplacements_jetons(texte: str, detections: list[Detection], table: Table) -> list[Remplacement]:
    """Le jeton à mettre à la place de chaque passage détecté. Les détections ne doivent pas se chevaucher."""
    sortie: list[Remplacement] = []
    position = 0
    for d in sorted(detections, key=lambda d: d.debut):
        if d.debut < position:
            raise ValueError("Les détections se chevauchent : passer d'abord par la fusion.")
        jeton = MARQUE_SECRET if d.type == TYPE_SECRET else table.jeton(d.type, texte[d.debut : d.fin])
        sortie.append((d.debut, d.fin, jeton))
        position = d.fin
    return sortie


def pseudonymiser(texte: str, detections: list[Detection], table: Table) -> Filtrage:
    """Remplace chaque passage détecté par son jeton. Les détections ne doivent pas se chevaucher."""
    texte_filtre = appliquer(texte, remplacements_jetons(texte, detections, table))
    return Filtrage(texte_filtre, Counter(d.type for d in detections))


def remplacements_caviard(detections: list[Detection]) -> list[Remplacement]:
    """La marque noire à mettre à la place de chaque passage. Rien n'est rangé dans la table."""
    sortie: list[Remplacement] = []
    position = 0
    for d in sorted(detections, key=lambda d: d.debut):
        if d.debut < position:
            raise ValueError("Les détections se chevauchent : passer d'abord par la fusion.")
        sortie.append((d.debut, d.fin, MARQUE_CAVIARD))
        position = d.fin
    return sortie


def caviarder(texte: str, detections: list[Detection]) -> Filtrage:
    """Retire chaque passage détecté pour de bon : aucun retour possible."""
    return Filtrage(appliquer(texte, remplacements_caviard(detections)), Counter(d.type for d in detections))


def texte_motif_jetons(types: list[str]) -> str | None:
    """L'expression qui reconnaît un jeton de ces types, même déformé. À compiler sans tenir compte de la casse."""
    if not types:
        return None
    # DATE_NAISSANCE accepte « date naissance », « Date-Naissance », « DATE_NAISSANCE ».
    formes = sorted((t.replace("_", "[ _-]?") for t in types), key=len, reverse=True)
    return rf"(?<![A-Za-z0-9_\[])(\[)?({'|'.join(formes)})[ _\-]{{0,2}}(\d+)(?!\d)(?(1)\])"


def _motif_tolerant(types: list[str]) -> re.Pattern | None:
    texte = texte_motif_jetons(types)
    return re.compile(texte, re.IGNORECASE) if texte else None


def restaurer(texte: str, table: Table) -> Restauration:
    """Remet les vraies valeurs à la place des jetons, même déformés."""
    return restaurer_avec_positions(texte, table)[0]


def restaurer_avec_positions(texte: str, table: Table) -> tuple[Restauration, list[Remplacement]]:
    """Comme `restaurer`, et rend aussi où chaque valeur revient : utile pour un fichier mis en forme."""
    resultat = Restauration(texte)
    types = {re.sub(r"[ _-]", "", t).upper(): t for t in table.types()}
    remplacements: list[Remplacement] = []
    motif = _motif_tolerant(list(types.values()))
    for m in motif.finditer(texte) if motif else ():
        type_ = types[re.sub(r"[ _-]", "", m.group(2)).upper()]
        jeton = f"{type_}_{int(m.group(3))}"
        valeur = table.valeur(type_, int(m.group(3)))
        if valeur is None:
            continue
        if m.group(0) not in (jeton, f"[{jeton}]"):
            resultat.approximatifs.append(m.group(0))
        remplacements.append((m.start(), m.end(), valeur))
    resultat.texte = appliquer(texte, remplacements)
    # Ce qui ressemble encore à un jeton après restauration n'est pas dans la table.
    connus = set(types.values())
    for m in _FORME_EXACTE.finditer(resultat.texte):
        if m.group(1) in connus and m.group(0) not in resultat.inconnus:
            resultat.inconnus.append(m.group(0))
    return resultat, remplacements

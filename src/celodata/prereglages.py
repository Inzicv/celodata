"""Préréglages : les catégories laissées en clair selon le métier ou le type de document.

Un préréglage ne dit pas quoi chercher : tout est cherché, et les passages d'une catégorie
laissée en clair sont montrés décochés. Il dit seulement ce qui est masqué d'office.

Les préréglages modifiés ou créés par l'utilisateur sont rangés chiffrés dans la table.
"""

import json

from celodata.detection.base import Detection
from celodata.table import Table

# Catégories qu'un préréglage peut laisser en clair, dans l'ordre où l'écran les montre.
CATEGORIES = (
    "PERSONNE", "ROLE", "ORGANISATION", "COMMUN", "ADRESSE", "VILLE", "LIEU", "PROJET",
    "TELEPHONE", "MAIL", "DATE_NAISSANCE", "AGE", "DATE", "DATE_LOI", "DUREE", "MONTANT",
    "NIR", "IBAN", "BIC", "SIRET", "TVA", "PLAQUE",
    "IDENTIFIANT", "MATRICULE", "NUM_CLIENT", "NUM_CONTRAT",
    "LOGIN", "IP", "MAC", "MACHINE", "URL",
    "SANTE", "SYNDICAT",
)  # fmt: skip
# Les secrets sont toujours supprimés, et ce que l'utilisateur a demandé lui-même est toujours masqué.
SOURCES_IMPOSEES = frozenset({"projet", "manuel"})

_INDICATIONS = ("ROLE", "COMMUN", "DATE_LOI", "DUREE")
ORIGINE: dict[str, tuple[str, ...]] = {
    "Tout masquer": (),
    "Contrat / juridique": (*_INDICATIONS, "MONTANT"),
    "RH / paie": _INDICATIONS,
    "Informatique": (*_INDICATIONS, "DATE", "MONTANT"),
}
# Au départ : tout ce qui touche une personne est masqué, seules les indications restent en clair.
DEFAUT = "RH / paie"
LONGUEUR_MAX_NOM = 40


def _modifies(table: Table) -> dict[str, list[str]]:
    try:
        lus = json.loads(table.reglage("prereglages") or "{}")
    except ValueError:
        return {}
    return {nom: [t for t in types if t in CATEGORIES] for nom, types in lus.items()}


def tous(table: Table) -> dict[str, tuple[str, ...]]:
    """Nom -> catégories laissées en clair. Ceux d'origine d'abord, puis ceux de l'utilisateur."""
    modifies = _modifies(table)
    liste = {nom: tuple(modifies.get(nom, laisses)) for nom, laisses in ORIGINE.items()}
    liste.update({nom: tuple(laisses) for nom, laisses in modifies.items() if nom not in ORIGINE})
    return liste


def courant(table: Table) -> str:
    nom = table.reglage("prereglage")
    return nom if nom in tous(table) else DEFAUT


def laisses(table: Table) -> frozenset[str]:
    """Les catégories que le préréglage en cours laisse en clair."""
    return frozenset(tous(table)[courant(table)])


def choisir(table: Table, nom: str) -> None:
    if nom not in tous(table):
        raise ValueError("Préréglage inconnu.")
    table.regler("prereglage", nom)


def enregistrer(table: Table, nom: str, types: list[str]) -> None:
    """Crée un préréglage, ou modifie un préréglage existant, y compris d'origine."""
    nom = nom.strip()
    if not nom or len(nom) > LONGUEUR_MAX_NOM:
        raise ValueError(f"Le nom doit faire entre 1 et {LONGUEUR_MAX_NOM} caractères.")
    modifies = _modifies(table)
    modifies[nom] = [t for t in CATEGORIES if t in set(types)]
    table.regler("prereglages", json.dumps(modifies, ensure_ascii=False))


def supprimer(table: Table, nom: str) -> None:
    """Supprime un préréglage créé par l'utilisateur, ou remet un préréglage d'origine comme au départ."""
    modifies = _modifies(table)
    modifies.pop(nom, None)
    table.regler("prereglages", json.dumps(modifies, ensure_ascii=False) if modifies else None)


def est_laisse(detection: Detection, en_clair: frozenset[str]) -> bool:
    return detection.type in en_clair and detection.source not in SOURCES_IMPOSEES


def retenir(detections: list[Detection], en_clair: frozenset[str]) -> list[Detection]:
    """Les passages à masquer d'office : ceux dont la catégorie n'est pas laissée en clair."""
    return [d for d in detections if not est_laisse(d, en_clair)]

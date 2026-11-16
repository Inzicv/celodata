"""Mesure la qualité d'un détecteur sur le jeu de faux documents.

Usage : celodata-mesure [--jeu jeu_de_test] [--detecteurs gliner2-pii,camembert] [--details]

Pour chaque valeur attendue, on vérifie qu'elle est entièrement couverte par des détections,
à chacune de ses occurrences. Une valeur à moitié masquée compte comme ratée.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from celodata.detection.base import Detecteur, Detection

# Catégories à format fixe : l'objectif est 100 %, elles relèvent des règles et non du modèle.
FORMATS_FIXES = frozenset(
    {"telephone", "mail", "nir", "iban", "bic", "siret", "plaque", "identifiant", "ip", "machine"}
)


@dataclass(frozen=True)
class Attendu:
    categorie: str
    valeur: str


@dataclass
class Bilan:
    libre_ok: int = 0
    libre_total: int = 0
    fixe_ok: int = 0
    fixe_total: int = 0
    hors_cible: int = 0
    duree: float = 0.0
    rates: list[tuple[str, Attendu]] = field(default_factory=list)

    def ajouter(self, autre: "Bilan") -> None:
        self.libre_ok += autre.libre_ok
        self.libre_total += autre.libre_total
        self.fixe_ok += autre.fixe_ok
        self.fixe_total += autre.fixe_total
        self.hors_cible += autre.hors_cible
        self.duree += autre.duree
        self.rates += autre.rates


def charger_jeu(dossier: Path) -> list[tuple[str, str, list[Attendu]]]:
    """Retourne (nom, texte, attendus) pour chaque document du jeu."""
    documents = []
    for fichier in sorted(dossier.glob("*.txt")):
        texte = fichier.read_text(encoding="utf-8")
        annotations = json.loads(fichier.with_suffix(".json").read_text(encoding="utf-8"))
        attendus = [Attendu(a["categorie"], a["valeur"]) for a in annotations]
        for a in attendus:
            if a.valeur not in texte:
                raise ValueError(f"{fichier.name} : valeur annotée absente du texte : {a.valeur!r}")
        documents.append((fichier.stem, texte, attendus))
    if not documents:
        raise ValueError(f"Aucun document dans {dossier}")
    return documents


def evaluer(nom: str, texte: str, attendus: list[Attendu], detections: list[Detection]) -> Bilan:
    couvert = [False] * len(texte)
    for d in detections:
        for i in range(max(d.debut, 0), min(d.fin, len(texte))):
            couvert[i] = True

    bilan = Bilan()
    cible = [False] * len(texte)
    for attendu in attendus:
        masque = True
        position = texte.find(attendu.valeur)
        while position != -1:
            for i in range(position, position + len(attendu.valeur)):
                cible[i] = True
                if not texte[i].isspace() and not couvert[i]:
                    masque = False
            position = texte.find(attendu.valeur, position + len(attendu.valeur))
        if attendu.categorie in FORMATS_FIXES:
            bilan.fixe_total += 1
            bilan.fixe_ok += masque
        else:
            bilan.libre_total += 1
            bilan.libre_ok += masque
        if not masque:
            bilan.rates.append((nom, attendu))

    bilan.hors_cible = sum(1 for d in detections if not any(cible[d.debut : d.fin]))
    return bilan


def mesurer(
    detecteur: Detecteur,
    documents: list[tuple[str, str, list[Attendu]]],
    en_clair: frozenset[str] = frozenset(),
) -> Bilan:
    """`en_clair` : catégories qu'un préréglage laisse en clair, pour mesurer ce qu'il masque vraiment."""
    total = Bilan()
    for nom, texte, attendus in documents:
        debut = time.perf_counter()
        detections = [d for d in detecteur.detecter(texte) if d.type not in en_clair]
        bilan = evaluer(nom, texte, attendus, detections)
        bilan.duree = time.perf_counter() - debut
        total.ajouter(bilan)
    return total


def main(argv: list[str] | None = None) -> int:
    from celodata.detection.modeles import DETECTEURS, creer_detecteur
    from celodata.prereglages import DEFAUT, ORIGINE

    parser = argparse.ArgumentParser(description="Mesure les détecteurs sur le jeu de faux documents.")
    parser.add_argument("--jeu", type=Path, default=Path("jeu_de_test"))
    parser.add_argument("--detecteurs", default=",".join(DETECTEURS))
    parser.add_argument("--prereglage", default=DEFAUT, choices=list(ORIGINE), help="préréglage appliqué")
    parser.add_argument("--details", action="store_true", help="liste les valeurs ratées")
    args = parser.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8")
    documents = charger_jeu(args.jeu)
    print(f"{len(documents)} documents, {sum(len(a) for _, _, a in documents)} valeurs à masquer\n")
    print(f"{'détecteur':14} {'texte libre':>12} {'formats fixes':>14} {'hors cible':>11} {'durée':>8}")
    for nom in args.detecteurs.split(","):
        bilan = mesurer(creer_detecteur(nom.strip()), documents, frozenset(ORIGINE[args.prereglage]))
        print(
            f"{nom:14} {f'{bilan.libre_ok}/{bilan.libre_total}':>12} "
            f"{f'{bilan.fixe_ok}/{bilan.fixe_total}':>14} {bilan.hors_cible:>11} {bilan.duree:>7.1f}s"
        )
        if args.details:
            for document, attendu in bilan.rates:
                print(f"    raté  {document:28} {attendu.categorie:15} {attendu.valeur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

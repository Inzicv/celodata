"""Traitement d'un dossier entier, sans aperçu.

Chaque document lisible donne un fichier texte filtré dans le dossier de sortie.
Les documents d'origine ne sont pas modifiés.
"""

from dataclasses import dataclass
from pathlib import Path

from celodata import journal
from celodata.detection.base import Detecteur
from celodata.detection.listes import fonctions_a_verifier
from celodata.documents import EXTENSIONS, EXTENSIONS_TEXTE, DocumentIllisible, lire_fichier
from celodata.moteur import analyser, pseudonymiser
from celodata.table import Table

DOSSIER_SORTIE = "celodata_filtré"


@dataclass
class ResultatFichier:
    fichier: str
    ok: bool
    masques: int = 0
    # Fonctions uniques (DRH, PDG...) laissées en clair : à relire avant envoi.
    a_verifier: int = 0
    erreur: str = ""


def traiter_dossier(dossier: Path, sortie: Path, detecteur: Detecteur, table: Table) -> list[ResultatFichier]:
    dossier, sortie = Path(dossier), Path(sortie)
    fichiers = sorted(
        f
        for f in dossier.rglob("*")
        if f.is_file() and f.suffix.lower() in EXTENSIONS | {".doc"} and sortie not in f.parents
    )
    resultats = []
    for f in fichiers:
        relatif = f.relative_to(dossier)
        try:
            texte = lire_fichier(f)
        except (DocumentIllisible, OSError) as e:
            resultats.append(ResultatFichier(str(relatif), False, erreur=str(e)))
            continue
        detections = analyser(texte, detecteur, table)
        filtre = pseudonymiser(texte, detections, table)
        a_verifier = sum(
            1
            for s in fonctions_a_verifier(texte)
            if all(s.fin <= d.debut or s.debut >= d.fin for d in detections)
            and not table.est_ignoree(texte[s.debut : s.fin])
        )
        # « contrat.docx » donne « contrat.docx.txt » : pas de collision avec « contrat.pdf ».
        cible = sortie / relatif
        if f.suffix.lower() not in EXTENSIONS_TEXTE:
            cible = cible.with_name(cible.name + ".txt")
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(filtre.texte, encoding="utf-8")
        journal.filtrage(table, detections, mode="lot", detecteur=detecteur.nom, fichier=str(relatif))
        resultats.append(ResultatFichier(str(relatif), True, len(detections), a_verifier))
    return resultats

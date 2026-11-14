"""Traitement d'un dossier entier, sans aperçu.

Chaque document lisible donne un fichier filtré dans le dossier de sortie : un Word reste un Word,
un Excel reste un Excel, les autres deviennent du texte. Les documents d'origine ne sont pas modifiés.
"""

from dataclasses import dataclass
from pathlib import Path

from celodata import journal
from celodata.detection.base import Detecteur
from celodata.detection.listes import fonctions_a_verifier
from celodata.documents import EXTENSIONS, EXTENSIONS_TEXTE, DocumentIllisible, lire
from celodata.fichiers import FORMATS, filtrer_fichier, ouvrir
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
    # Ce qui n'a pas pu être filtré dans le fichier (images...).
    remarque: str = ""


def traiter_dossier(dossier: Path, sortie: Path, detecteur: Detecteur, table: Table) -> list[ResultatFichier]:
    dossier, sortie = Path(dossier), Path(sortie)
    fichiers = sorted(
        f
        for f in dossier.rglob("*")
        if f.is_file() and f.suffix.lower() in EXTENSIONS | {".doc", ".xls"} and sortie not in f.parents
    )
    resultats = []
    for f in fichiers:
        relatif = f.relative_to(dossier)
        extension = f.suffix.lower()
        cible = sortie / relatif
        remarque = ""
        try:
            contenu = f.read_bytes()
            if extension in FORMATS:
                texte = ouvrir(f.name, contenu).texte
                filtre = filtrer_fichier(f.name, contenu, detecteur, table)
                detections, produit, remarque = filtre.detections, filtre.contenu, ", ".join(filtre.avertissements)
            else:
                texte = lire(f.name, contenu)
                detections = analyser(texte, detecteur, table)
                produit = pseudonymiser(texte, detections, table).texte.encode("utf-8")
                # « contrat.pdf » donne « contrat.pdf.txt » : pas de collision avec « contrat.txt ».
                if extension not in EXTENSIONS_TEXTE:
                    cible = cible.with_name(cible.name + ".txt")
        except (DocumentIllisible, OSError) as e:
            resultats.append(ResultatFichier(str(relatif), False, erreur=str(e)))
            continue
        a_verifier = sum(
            1
            for s in fonctions_a_verifier(texte)
            if all(s.fin <= d.debut or s.debut >= d.fin for d in detections)
            and not table.est_ignoree(texte[s.debut : s.fin])
        )
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(produit)
        journal.filtrage(table, detections, mode="lot", detecteur=detecteur.nom, fichier=str(relatif))
        resultats.append(ResultatFichier(str(relatif), True, len(detections), a_verifier, remarque=remarque))
    return resultats

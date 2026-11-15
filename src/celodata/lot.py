"""Traitement d'un dossier entier, sans aperçu.

Chaque document lisible donne un fichier filtré dans le dossier de sortie : un Word reste un Word,
un Excel reste un Excel, un PDF devient un Word, les autres restent du texte. Les documents d'origine ne sont pas modifiés.
"""

from dataclasses import dataclass
from pathlib import Path

from celodata import journal, pdf
from celodata.detection.base import Detecteur
from celodata.detection.listes import fonctions_a_verifier
from celodata.documents import EXTENSIONS, DocumentIllisible, lire
from celodata.fichiers import FORMATS, appliquer_caviardage, filtrer_fichier, ouvrir, texte_en_word
from celodata.moteur import analyser, caviarder, pseudonymiser
from celodata.table import Table

DOSSIER_SORTIE = "celodata_filtré"
DOSSIER_CAVIARDE = "celodata_caviardé"
CAVIARDAGE = "caviardage"


def dossier_sortie(traitement: str) -> str:
    return DOSSIER_CAVIARDE if traitement == CAVIARDAGE else DOSSIER_SORTIE


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


def traiter_dossier(
    dossier: Path, sortie: Path, detecteur: Detecteur, table: Table, traitement: str = "pseudonymisation"
) -> list[ResultatFichier]:
    """`traitement` vaut "pseudonymisation" (jetons, réversible) ou "caviardage" (définitif).

    En caviardage, un PDF reste un PDF, fait d'images, où les tampons et signatures sont aussi recouverts.
    Un PDF scanné est traité comme les autres, et signalé : sa lecture peut contenir des erreurs.
    """
    dossier, sortie = Path(dossier), Path(sortie)
    caviardage = traitement == CAVIARDAGE
    produits = {dossier / DOSSIER_SORTIE, dossier / DOSSIER_CAVIARDE, sortie}
    fichiers = sorted(
        f
        for f in dossier.rglob("*")
        if f.is_file() and f.suffix.lower() in EXTENSIONS | {".doc", ".xls"} and not produits & set(f.parents)
    )
    resultats = []
    for f in fichiers:
        relatif = f.relative_to(dossier)
        extension = f.suffix.lower()
        cible = sortie / relatif
        remarque = ""
        try:
            contenu = f.read_bytes()
            if extension in FORMATS and caviardage:
                document = ouvrir(f.name, contenu)
                texte, remarque = document.texte, ", ".join(document.avertissements)
                detections = document.decouper(analyser(texte, detecteur, table))
                produit = appliquer_caviardage(document, detections)
            elif extension == ".pdf":
                lu = pdf.lire(contenu)
                texte = lu.texte
                detections = analyser(texte, detecteur, table)
                notes = []
                if lu.pages_scannees:
                    # Une lecture de scan fait des erreurs : ce fichier est à relire en priorité.
                    notes.append("scan lu par reconnaissance de caractères, à relire")
                if caviardage:
                    zones = pdf.zones_graphiques(contenu, lu)
                    produit, perdus = pdf.caviarder(contenu, lu, detections, zones)
                    if perdus:
                        raise DocumentIllisible(f"{perdus} passage(s) n'ont pas pu être placés sur la page.")
                    if zones:
                        notes.append(f"{len(zones)} zone(s) sans texte recouverte(s) : tampon, signature, image")
                else:
                    # « contrat.pdf » donne « contrat.pdf.docx » : pas de collision avec « contrat.docx ».
                    produit = texte_en_word(pseudonymiser(texte, detections, table).texte)
                    cible = cible.with_name(cible.name + ".docx")
                remarque = ", ".join(notes)
            elif extension in FORMATS:
                texte = ouvrir(f.name, contenu).texte
                filtre = filtrer_fichier(f.name, contenu, detecteur, table)
                detections, produit, remarque = filtre.detections, filtre.contenu, ", ".join(filtre.avertissements)
            else:
                texte = lire(f.name, contenu)
                detections = analyser(texte, detecteur, table)
                if caviardage:
                    produit = caviarder(texte, detections).texte.encode("utf-8")
                else:
                    produit = pseudonymiser(texte, detections, table).texte.encode("utf-8")
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
        journal.filtrage(
            table,
            detections,
            mode="lot",
            detecteur=detecteur.nom,
            fichier=str(relatif),
            traitement=CAVIARDAGE if caviardage else "pseudonymisation",
        )
        resultats.append(ResultatFichier(str(relatif), True, len(detections), a_verifier, remarque=remarque))
    return resultats

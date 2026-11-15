"""PDF : rendu en Word filtré, et lecture des PDF scannés par la reconnaissance de caractères de Windows."""

import io
from pathlib import Path

import pytest
from docx import Document

from celodata import ocr
from celodata.appli.api import Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles
from celodata.documents import DocumentIllisible, lire, lire_detail
from celodata.fichiers import texte_en_word
from celodata.lot import DOSSIER_SORTIE, traiter_dossier
from celodata.table import Table
from test_documents import pdf

OPTIONS = {"memoire_kio": 64, "iterations": 1}
TELEPHONE = "04 72 99 88 77"
LIGNES = ["Contrat de prestation", f"Contact : Girard, {TELEPHONE}", "Fait le 12/03/2024"]
POLICE = Path("C:/Windows/Fonts/arial.ttf")

lecture_des_scans = pytest.mark.skipif(
    not (ocr.disponible() and POLICE.exists()), reason="reconnaissance de caractères de Windows absente"
)


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


def scan(lignes: list[str]) -> bytes:
    """Un PDF d'une page qui ne contient qu'une image, comme un document numérisé."""
    from PIL import Image, ImageDraw, ImageFont

    page = Image.new("L", (2480, 3508), 255)
    dessin = ImageDraw.Draw(page)
    police = ImageFont.truetype(str(POLICE), 60)
    for i, ligne in enumerate(lignes):
        dessin.text((250, 300 + i * 110), ligne, font=police, fill=0)
    sortie = io.BytesIO()
    page.save(sortie, "PDF", resolution=300)
    return sortie.getvalue()


def paragraphes(chemin) -> list[str]:
    return [p.text for p in Document(str(chemin)).paragraphs]


def test_un_texte_devient_un_word_neuf():
    document = Document(io.BytesIO(texte_en_word("Ligne 1\n\nLigne 3")))
    assert [p.text for p in document.paragraphs] == ["Ligne 1", "", "Ligne 3"]
    assert document.core_properties.author == "Celodata"


def test_appli_rend_un_pdf_filtre_en_word(tmp_path):
    (tmp_path / "contrat.pdf").write_bytes(pdf(LIGNES))
    choix = {"fichier": str(tmp_path / "contrat.pdf"), "enregistrer": str(tmp_path / "contrat_filtré.docx")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("mot de passe de test")

    charge = a.ouvrir_fichier()
    assert charge["format"] is True and charge["pages_scannees"] == 0
    analyse = a.analyser(charge["texte"])
    assert a.enregistrer_filtre(charge["texte"], analyse["detections"], [])["ok"]
    assert paragraphes(tmp_path / "contrat_filtré.docx") == [
        "Contrat de prestation", "Contact : Girard, TELEPHONE_1", "Fait le DATE_1",
    ]


def test_un_dossier_rend_les_pdf_en_word(tmp_path):
    (tmp_path / "contrat.pdf").write_bytes(pdf(LIGNES))
    with Table.ouvrir(":memory:", "mot de passe de test", **OPTIONS) as table:
        resultats = traiter_dossier(tmp_path, tmp_path / DOSSIER_SORTIE, regles_seules()[0], table)
    assert [(r.fichier, r.ok) for r in resultats] == [("contrat.pdf", True)]
    assert "TELEPHONE_1" in paragraphes(tmp_path / DOSSIER_SORTIE / "contrat.pdf.docx")[1]


@lecture_des_scans
def test_un_pdf_scanne_est_lu():
    lecture = lire_detail("scan.pdf", scan(LIGNES))
    assert lecture.pages_scannees == 1
    assert TELEPHONE in lecture.texte and "Girard" in lecture.texte and "Contrat de prestation" in lecture.texte
    # Un appelant peut refuser les scans.
    with pytest.raises(DocumentIllisible, match="scanné"):
        lire("scan.pdf", scan(LIGNES), scans=False)
    with pytest.raises(DocumentIllisible, match="scanné"):
        lire("blanc.pdf", scan([]))


@lecture_des_scans
def test_appli_filtre_un_scan_et_un_dossier_le_signale(tmp_path):
    (tmp_path / "scan.pdf").write_bytes(scan(LIGNES))
    choix = {"fichier": str(tmp_path / "scan.pdf"), "enregistrer": str(tmp_path / "scan_filtré.docx")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("mot de passe de test")

    charge = a.ouvrir_fichier()
    assert charge["pages_scannees"] == 1 and charge["format"] is True
    analyse = a.analyser(charge["texte"])
    assert a.enregistrer_filtre(charge["texte"], analyse["detections"], [])["ok"]
    filtre = "\n".join(paragraphes(tmp_path / "scan_filtré.docx"))
    assert "TELEPHONE_1" in filtre and TELEPHONE not in filtre

    with Table.ouvrir(":memory:", "mot de passe de test", **OPTIONS) as table:
        resultats = traiter_dossier(tmp_path, tmp_path / DOSSIER_SORTIE, regles_seules()[0], table)
    # Un scan est traité comme les autres dans un dossier, et signalé comme à relire.
    resultat = [r for r in resultats if r.fichier == "scan.pdf"][0]
    assert resultat.ok and "scan" in resultat.remarque and "relire" in resultat.remarque
    filtre = "\n".join(paragraphes(tmp_path / DOSSIER_SORTIE / "scan.pdf.docx"))
    assert "TELEPHONE_1" in filtre and TELEPHONE not in filtre

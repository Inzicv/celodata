"""Fichiers Word et Excel filtrés puis restaurés dans leur format."""

import datetime
import io
import zipfile

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment

from celodata.appli.api import Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles
from celodata.documents import DocumentIllisible, lire
from celodata.fichiers import Formate, Piece, filtrer_fichier, ouvrir, restaurer_fichier
from celodata.lot import DOSSIER_SORTIE, traiter_dossier
from celodata.table import Table

OPTIONS = {"memoire_kio": 64, "iterations": 1}
TELEPHONE = "04 72 99 88 77"
MAIL = "s.lemoine@fonderies-exemple.fr"
VALEURS = [TELEPHONE, MAIL, "Lefèvre", "12/03/1984", "1984-03-12"]


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


@pytest.fixture
def table():
    with Table.ouvrir(":memory:", "mot de passe de test", **OPTIONS) as t:
        t.ajouter_regle("terme", "Lefèvre", "PERSONNE")
        yield t


def word() -> bytes:
    document = Document()
    document.core_properties.author = "Claire Lefèvre"
    document.sections[0].header.paragraphs[0].text = "Dossier de Mme Lefèvre"
    p = document.add_paragraph("Appeler le ")
    # Le numéro est à cheval sur deux bouts de phrase, dont un en gras.
    p.add_run("04 72 ").bold = True
    p.add_run("99 88 77 avant vendredi.")
    t = document.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Lefèvre"
    t.cell(0, 1).text = MAIL
    document.part.relate_to(f"mailto:{MAIL}", RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    sortie = io.BytesIO()
    document.save(sortie)
    return sortie.getvalue()


def excel() -> bytes:
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Lefèvre"
    feuille.append(["Nom", "Téléphone", "Naissance", "Salaire", "Total"])
    feuille.append(["Lefèvre", TELEPHONE, datetime.datetime(1984, 3, 12), 2150.5, "=D2*12"])
    feuille["A2"].comment = Comment(f"Joindre au {TELEPHONE}", "Claire Lefèvre")
    feuille["B2"].hyperlink = f"mailto:{MAIL}"
    feuille["D2"].font = feuille["D2"].font.copy(bold=True)
    classeur.properties.creator = "Claire Lefèvre"
    sortie = io.BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


def brut(contenu: bytes) -> bytes:
    """Tout ce que contient l'archive du fichier, décompressé."""
    with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
        return b"\n".join(archive.read(n) for n in archive.namelist())


def aucune_valeur(contenu: bytes) -> None:
    donnees = brut(contenu)
    for valeur in VALEURS:
        assert valeur.encode("utf-8") not in donnees, valeur


def test_remplacement_a_cheval_sur_plusieurs_emplacements():
    ecrits = {}
    document = Formate()
    for i, texte in enumerate(["Appeler le 04 ", "72 99", " 88 77 demain"]):
        document.pieces.append(Piece(texte, lambda s, i=i: ecrits.__setitem__(i, s)))
        document.pieces.append(Piece("\n"))
    assert document.texte == "Appeler le 04 \n72 99\n 88 77 demain\n"
    document.remplacer([(0, 7, "Joindre"), (11, 27, "TELEPHONE_1")])
    assert ecrits == {0: "Joindre le TELEPHONE_1", 1: "", 2: " demain"}
    assert document.texte == "Joindre le TELEPHONE_1\n\n demain\n"


def test_un_passage_a_cheval_sur_deux_cellules_donne_un_jeton_par_cellule(table):
    from celodata.detection.base import Detection

    classeur = Workbook()
    classeur.active.append(["BERNARD", "Lucie ", "Paris"])
    sortie = io.BytesIO()
    classeur.save(sortie)
    document = ouvrir("c.xlsx", sortie.getvalue())
    debut = document.texte.index("BERNARD")
    # Un détecteur peut prendre « BERNARD<tab>Lucie » pour un seul nom.
    morceaux = document.decouper([Detection(debut, debut + len("BERNARD\tLucie \t"), "PERSONNE", 0.9, "modele")])
    assert [document.texte[d.debut : d.fin] for d in morceaux] == ["BERNARD", "Lucie"]
    document.remplacer([(d.debut, d.fin, f"PERSONNE_{i}") for i, d in enumerate(morceaux, 1)])
    feuille = load_workbook(io.BytesIO(document.enregistrer())).active
    assert [c.value for c in feuille[1]] == ["PERSONNE_1", "PERSONNE_2 ", "Paris"]


def test_word_filtre_puis_restaure(table):
    filtre = filtrer_fichier("c.docx", word(), regles_seules()[0], table)
    aucune_valeur(filtre.contenu)

    document = Document(io.BytesIO(filtre.contenu))
    paragraphe = document.paragraphs[0]
    assert paragraphe.text == "Appeler le TELEPHONE_1 avant vendredi."
    # La mise en forme est gardée : le bout de phrase en gras l'est toujours.
    assert [r.bold for r in paragraphe.runs] == [None, True, None]
    assert document.sections[0].header.paragraphs[0].text == "Dossier de Mme PERSONNE_1"
    assert [c.text for c in document.tables[0].rows[0].cells] == ["PERSONNE_1", "MAIL_1"]
    assert document.core_properties.author == ""

    restaure, bilan = restaurer_fichier("c.docx", filtre.contenu, table)
    assert (bilan.inconnus, bilan.approximatifs) == ([], [])
    assert ouvrir("c.docx", restaure).texte == ouvrir("c.docx", word()).texte
    assert Document(io.BytesIO(restaure)).paragraphs[0].text == f"Appeler le {TELEPHONE} avant vendredi."


def test_word_signale_ce_qui_n_est_pas_filtre(table):
    with zipfile.ZipFile(io.BytesIO(word())) as source:
        sortie = io.BytesIO()
        with zipfile.ZipFile(sortie, "w") as cible:
            for nom in source.namelist():
                cible.writestr(nom, source.read(nom))
            cible.writestr("word/media/image1.png", b"\x89PNG")
    assert filtrer_fichier("c.docx", sortie.getvalue(), regles_seules()[0], table).avertissements == ["1 image non filtrée"]
    with pytest.raises(DocumentIllisible):
        ouvrir("c.docx", b"pas un docx")
    with pytest.raises(DocumentIllisible):
        ouvrir("c.docx", excel())


def test_excel_filtre_puis_restaure(table):
    filtre = filtrer_fichier("c.xlsx", excel(), regles_seules()[0], table)
    aucune_valeur(filtre.contenu)

    classeur = load_workbook(io.BytesIO(filtre.contenu))
    feuille = classeur.worksheets[0]
    assert feuille.title == "PERSONNE_1"
    # La date est une vraie date dans Excel : elle est lue comme un texte pour être détectée.
    assert [c.value for c in feuille[2]] == ["PERSONNE_1", "TELEPHONE_1", "DATE_1", 2150.5, "=D2*12"]
    assert feuille["A2"].comment.text == "Joindre au TELEPHONE_1" and feuille["A2"].comment.author == "Celodata"
    assert feuille["B2"].hyperlink.target == "mailto:MAIL_1"
    assert feuille["D2"].font.bold is True
    assert classeur.properties.creator == "Celodata"

    restaure, _ = restaurer_fichier("c.xlsx", filtre.contenu, table)
    feuille = load_workbook(io.BytesIO(restaure)).worksheets[0]
    assert feuille.title == "Lefèvre"
    assert [c.value for c in feuille[2]] == ["Lefèvre", TELEPHONE, "12/03/1984", 2150.5, "=D2*12"]
    assert feuille["B2"].hyperlink.target == f"mailto:{MAIL}"
    assert "Lefèvre\t" + TELEPHONE in lire("c.xlsx", excel())


def test_un_dossier_garde_les_formats(tmp_path, table):
    (tmp_path / "a.docx").write_bytes(word())
    (tmp_path / "b.xlsx").write_bytes(excel())
    (tmp_path / "c.txt").write_text(f"Appeler le {TELEPHONE}.", encoding="utf-8")
    (tmp_path / "vieux.xls").write_bytes(b"")
    sortie = tmp_path / DOSSIER_SORTIE
    resultats = traiter_dossier(tmp_path, sortie, regles_seules()[0], table)
    assert [(r.fichier, r.ok) for r in resultats] == [("a.docx", True), ("b.xlsx", True), ("c.txt", True), ("vieux.xls", False)]
    assert sorted(f.name for f in sortie.iterdir()) == ["a.docx", "b.xlsx", "c.txt"]
    aucune_valeur((sortie / "a.docx").read_bytes())
    aucune_valeur((sortie / "b.xlsx").read_bytes())
    # La même valeur a le même jeton dans le Word, l'Excel et le texte.
    assert (sortie / "c.txt").read_text(encoding="utf-8") == "Appeler le TELEPHONE_1."
    assert "TELEPHONE_1" in ouvrir("a.docx", (sortie / "a.docx").read_bytes()).texte


def test_appli_enregistre_le_fichier_filtre_et_le_restaure(tmp_path):
    (tmp_path / "c.docx").write_bytes(word())
    choix = {"fichier": str(tmp_path / "c.docx"), "enregistrer": str(tmp_path / "c_filtré.docx")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("mot de passe de test")
    a.ajouter_regle("terme", "Lefèvre", "PERSONNE")

    charge = a.ouvrir_fichier()
    assert charge["format"] is True
    analyse = a.analyser(charge["texte"])
    # L'utilisateur démasque le téléphone dans l'aperçu : il reste en clair dans le fichier filtré.
    gardees = [d for d in analyse["detections"] if d["type"] != "TELEPHONE"]
    assert a.enregistrer_filtre(charge["texte"] + " ", gardees, [TELEPHONE])["ok"] is False
    resultat = a.enregistrer_filtre(charge["texte"], gardees, [TELEPHONE])
    assert resultat["ok"] and resultat["avertissements"] == []
    filtre = Document(str(tmp_path / "c_filtré.docx"))
    assert filtre.paragraphs[0].text == f"Appeler le {TELEPHONE} avant vendredi."
    assert [c.text for c in filtre.tables[0].rows[0].cells] == ["PERSONNE_1", "MAIL_1"]
    assert a.journal()[0]["fichier"] == "c.docx"

    choix.update(fichier=str(tmp_path / "c_filtré.docx"), enregistrer=str(tmp_path / "c_restauré.docx"))
    retour = a.restaurer_fichier()
    assert retour["ok"] and retour["inconnus"] == []
    assert [c.text for c in Document(str(tmp_path / "c_restauré.docx")).tables[0].rows[0].cells] == ["Lefèvre", MAIL]

    # Un fichier texte chargé n'a pas de mise en forme : il est enregistré en texte.
    (tmp_path / "n.txt").write_text("PERSONNE_1 rappelle.", encoding="utf-8")
    choix.update(fichier=str(tmp_path / "n.txt"), enregistrer=str(tmp_path / "n_restauré.txt"))
    assert a.ouvrir_fichier()["format"] is False
    assert a.enregistrer_filtre("PERSONNE_1 rappelle.", [], [], fichier="n.txt")["ok"]
    assert (tmp_path / "n_restauré.txt").read_text(encoding="utf-8") == "PERSONNE_1 rappelle."
    assert a.restaurer_fichier()["ok"] and (tmp_path / "n_restauré.txt").read_text(encoding="utf-8") == "Lefèvre rappelle."

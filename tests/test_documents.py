"""Étape 4 : fichiers Word et PDF, règles du projet, journal, dossier entier."""

import base64
import io
import sqlite3

import pytest

from celodata.appli.api import Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles
from celodata.documents import DocumentIllisible, lire
from celodata.lot import DOSSIER_SORTIE, traiter_dossier
from celodata.moteur import analyser
from celodata.table import Table

OPTIONS = {"memoire_kio": 64, "iterations": 1}
COURRIER = ["Courrier pour Mme Lefèvre", "Téléphone : 04 72 99 88 77", "Dossier TCK-204815 du projet Zéphyr"]


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


def docx(lignes: list[str], entete: str = "", tableau: list[list[str]] | None = None) -> bytes:
    from docx import Document

    document = Document()
    if entete:
        document.sections[0].header.paragraphs[0].text = entete
    for ligne in lignes:
        document.add_paragraph(ligne)
    if tableau:
        t = document.add_table(rows=len(tableau), cols=len(tableau[0]))
        for i, rangee in enumerate(tableau):
            for j, valeur in enumerate(rangee):
                t.cell(i, j).text = valeur
    sortie = io.BytesIO()
    document.save(sortie)
    return sortie.getvalue()


def pdf(lignes: list[str]) -> bytes:
    """Un PDF d'une page, écrit à la main : assez pour vérifier l'extraction du texte."""
    echapper = lambda l: l.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    texte = " ".join(f"({echapper(l)}) Tj T*" for l in lignes)
    flux = f"BT /F1 12 Tf 14 TL 50 780 Td {texte} ET".encode("cp1252")
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(flux), flux),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    sortie, positions = b"%PDF-1.4\n", []
    for numero, objet in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += b"%d 0 obj\n%s\nendobj\n" % (numero, objet)
    debut_table = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    sortie += b"".join(b"%010d 00000 n \n" % p for p in positions)
    sortie += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, debut_table)
    return sortie


@pytest.fixture
def table():
    with Table.ouvrir(":memory:", "mot de passe de test", **OPTIONS) as t:
        yield t


# ---------- lecture des fichiers ----------


def test_texte_brut_utf8_et_windows():
    assert lire("a.txt", "﻿Lefèvre\r\nfin".encode("utf-8")) == "Lefèvre\nfin"
    assert lire("a.csv", "Lefèvre".encode("cp1252")) == "Lefèvre"


def test_word_entete_paragraphes_et_tableau():
    texte = lire("c.docx", docx(COURRIER, entete="Durand SARL", tableau=[["Nom", "Ville"], ["Girard", "Lyon"]]))
    assert texte.split("\n")[:4] == ["Durand SARL", *COURRIER]
    assert "Nom\tVille\nGirard\tLyon" in texte


def test_pdf():
    assert lire("c.pdf", pdf(COURRIER)).split("\n") == COURRIER


def test_fichiers_illisibles():
    for nom, contenu in [("x.pdf", b"pas un pdf"), ("x.docx", b"pas un docx"), ("x.doc", b""), ("x.xlsx", b"")]:
        with pytest.raises(DocumentIllisible):
            lire(nom, contenu)
    with pytest.raises(DocumentIllisible, match="scanné"):
        lire("vide.pdf", pdf([]))


# ---------- règles du projet ----------


def test_terme_et_motif_du_projet(table):
    detecteur = regles_seules()[0]
    texte = "\n".join(COURRIER) + "\nle projet ZÉPHYR avance."
    trouves = lambda: [(texte[d.debut : d.fin], d.type, d.source) for d in analyser(texte, detecteur, table)]
    assert ("TCK-204815", "IDENTIFIANT", "projet") not in trouves()

    terme = table.ajouter_regle("terme", "Zéphyr", "PROJET")
    table.ajouter_regle("motif", r"TCK-\d{6}", "IDENTIFIANT")
    assert ("TCK-204815", "IDENTIFIANT", "projet") in trouves()
    # Le terme est retrouvé sans tenir compte des majuscules.
    assert [v for v, t, s in trouves() if s == "projet" and t == "PROJET"] == ["Zéphyr", "ZÉPHYR"]

    table.supprimer_regle(terme)
    assert [r["genre"] for r in table.regles()] == ["motif"]
    assert not [v for v, t, s in trouves() if s == "projet" and t == "PROJET"]


def test_un_motif_invalide_ne_bloque_pas_l_analyse(table):
    table.ajouter_regle("motif", "(", "AUTRE")
    assert analyser("Appeler le 04 72 99 88 77.", regles_seules()[0], table)


def test_valeurs_ignorees_listees_et_table_ancienne(tmp_path):
    chemin = tmp_path / "p.celodata"
    with Table.ouvrir(chemin, "mot de passe de test", **OPTIONS) as t:
        t.ignorer("ancienne")
    # Une table d'avant l'étape 4 ne gardait que l'empreinte des valeurs ignorées.
    with sqlite3.connect(chemin) as db:
        db.execute("ALTER TABLE ignorees DROP COLUMN chiffre")
        db.execute("ALTER TABLE ignorees DROP COLUMN nonce")
    with Table.ouvrir(chemin, "mot de passe de test") as t:
        assert t.est_ignoree("ancienne") and t.ignorees() == []
        t.ignorer("Lyon")
        t.ignorer("Lyon")
        assert t.ignorees() == ["Lyon"]
        t.ne_plus_ignorer("Lyon")
        assert t.ignorees() == []


# ---------- journal ----------


def test_le_journal_ne_garde_aucune_vraie_valeur(tmp_path):
    chemin = tmp_path / "p.celodata"
    a = Api(chemin, regles_seules, OPTIONS)
    a.ouvrir("mot de passe de test")
    texte = "\n".join(COURRIER)
    analyse = a.analyser(texte)
    ajout = {"debut": texte.index("Lefèvre"), "fin": texte.index("Lefèvre") + 7, "type": "PERSONNE"}
    a.filtrer(texte, [*analyse["detections"], ajout], [], "courrier_Lefèvre.docx")
    a.restaurer("Bonjour PERSONNE_1 et PERSONNE_7, telephone 1.")

    restauration, filtrage = a.journal()
    assert filtrage["action"] == "filtrage" and filtrage["mode"] == "apercu"
    assert filtrage["fichier"] == "courrier_Lefèvre.docx"
    assert filtrage["par_type"] == {"TELEPHONE": 1, "IDENTIFIANT": 1, "PROJET": 1, "PERSONNE": 1}
    assert filtrage["par_source"] == {"regles": 3, "manuel": 1}
    assert restauration == {
        "date": restauration["date"], "fichier": "", "action": "restauration",
        "inconnus": 1, "approximatifs": 1, "version": filtrage["version"],
    }
    brut = chemin.read_bytes()
    for valeur in ["Lefèvre", "Lef\\u00e8vre", "04 72 99 88 77", "courrier_"]:
        assert valeur.encode("utf-8") not in brut


# ---------- dossier entier ----------


def test_un_dossier_passe_en_une_fois(tmp_path, table):
    dossier = tmp_path / "docs"
    (dossier / "sous").mkdir(parents=True)
    (dossier / "a.txt").write_text("\n".join(COURRIER), encoding="utf-8")
    (dossier / "b.docx").write_bytes(docx(COURRIER))
    (dossier / "sous" / "c.pdf").write_bytes(pdf(COURRIER))
    (dossier / "casse.pdf").write_bytes(b"pas un pdf")
    (dossier / "image.png").write_bytes(b"\x89PNG")
    table.ajouter_regle("terme", "Lefèvre", "PERSONNE")
    sortie = dossier / DOSSIER_SORTIE

    resultats = traiter_dossier(dossier, sortie, regles_seules()[0], table)
    assert [(r.fichier, r.ok) for r in resultats] == [
        ("a.txt", True), ("b.docx", True), ("casse.pdf", False), (str(sortie.parent / "sous" / "c.pdf")[len(str(dossier)) + 1 :], True),
    ]
    filtres = sorted(str(f.relative_to(sortie)).replace("\\", "/") for f in sortie.rglob("*") if f.is_file())
    assert filtres == ["a.txt", "b.docx.txt", "sous/c.pdf.txt"]
    for f in sortie.rglob("*.txt"):
        contenu = f.read_text(encoding="utf-8")
        assert "Lefèvre" not in contenu and "04 72" not in contenu
        # La même valeur a le même jeton dans tous les documents du dossier.
        assert "PERSONNE_1" in contenu and "TELEPHONE_1" in contenu
    assert (dossier / "a.txt").read_text(encoding="utf-8") == "\n".join(COURRIER)
    assert [j["mode"] for j in table.journal()] == ["lot"] * 3

    # Un second passage ne retraite pas le dossier de sortie.
    assert len(traiter_dossier(dossier, sortie, regles_seules()[0], table)) == 4


# ---------- appli ----------


def test_appli_fichiers_dossier_et_regles(tmp_path):
    (tmp_path / "a.docx").write_bytes(docx(COURRIER))
    choix = {"fichier": str(tmp_path / "a.docx"), "dossier": str(tmp_path)}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("mot de passe de test")

    assert a.ouvrir_fichier() == {"ok": True, "nom": "a.docx", "texte": "\n".join(COURRIER)}
    depose = a.lire_fichier("c.pdf", base64.b64encode(pdf(COURRIER)).decode())
    assert depose["ok"] and depose["texte"] == "\n".join(COURRIER)
    assert a.lire_fichier("c.pdf", base64.b64encode(b"rien").decode())["ok"] is False

    assert a.ajouter_regle("motif", "(", "AUTRE")["ok"] is False
    assert a.ajouter_regle("motif", "x*", "AUTRE")["ok"] is False
    assert a.ajouter_regle("terme", "Zéphyr", "pas un type")["ok"] is False
    assert a.ajouter_regle("terme", " Zéphyr ", "PROJET")["ok"] is True
    assert a.ajouter_regle("jamais", "Courrier", "")["ok"] is True
    regles = a.regles()
    assert [(r["genre"], r["texte"], r["type"]) for r in regles["regles"]] == [("terme", "Zéphyr", "PROJET")]
    assert regles["jamais"] == ["Courrier"]

    lot = a.filtrer_dossier()
    assert lot["ok"] and [(f["fichier"], f["ok"], f["masques"]) for f in lot["fichiers"]] == [("a.docx", True, 3)]
    assert "PROJET_1" in (tmp_path / DOSSIER_SORTIE / "a.docx.txt").read_text(encoding="utf-8")

    a.supprimer_regle(regles["regles"][0]["id"])
    a.ne_plus_ignorer("Courrier")
    assert a.regles() == {"regles": [], "jamais": []}
    assert Api(":memory:", regles_seules, OPTIONS).ouvrir_fichier() == {"ok": False, "annule": True}

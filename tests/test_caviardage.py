"""Caviardage (définitif) et dossier surveillé."""

import io
import time

import pytest
from docx import Document
from pypdf import PdfReader
from test_documents import pdf as faux_pdf
from test_pdf import LIGNES, OPTIONS, TELEPHONE, lecture_des_scans, regles_seules, scan

from celodata import ocr, pdf
from celodata.appli import api as module_api
from celodata.appli.api import Api
from celodata.detection.base import Detection
from celodata.lot import DOSSIER_CAVIARDE, traiter_dossier
from celodata.moteur import MARQUE_CAVIARD, caviarder
from celodata.table import Table


def texte_du_pdf(contenu: bytes) -> str:
    return "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(contenu)).pages)


def test_caviarder_un_texte_ne_laisse_rien_dans_la_table():
    texte = f"Appeler le {TELEPHONE} avant vendredi."
    debut = texte.index(TELEPHONE)
    resultat = caviarder(texte, [Detection(debut, debut + len(TELEPHONE), "TELEPHONE", 1.0, "regles")])
    assert resultat.texte == f"Appeler le {MARQUE_CAVIARD} avant vendredi."
    with pytest.raises(ValueError):
        caviarder(texte, [Detection(0, 5, "A", 1, "x"), Detection(3, 8, "B", 1, "x")])


def test_pdf_lu_avec_la_place_des_caracteres():
    lu = pdf.lire(faux_pdf(LIGNES))
    assert TELEPHONE in lu.texte and lu.pages_scannees == 0
    debut = lu.texte.index(TELEPHONE)
    zones = [z for z in lu.zones if debut <= z.debut < debut + len(TELEPHONE)]
    # Un cadre par chiffre, tous sur la même ligne de la page 0.
    assert len(zones) == 10 and {z.page for z in zones} == {0}
    assert all(0 <= z.cadre[0] < z.cadre[2] <= 1 and 0 <= z.cadre[1] < z.cadre[3] <= 1 for z in zones)


def test_appli_caviarde_un_pdf_en_images(tmp_path):
    (tmp_path / "contrat.pdf").write_bytes(faux_pdf(LIGNES))
    choix = {"fichier": str(tmp_path / "contrat.pdf"), "enregistrer": str(tmp_path / "contrat_caviardé.pdf")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("un-mot-de-passe")
    charge = a.ouvrir_fichier()
    assert charge["ok"] and charge["pdf"]
    analyse = a.analyser(charge["texte"])
    resultat = a.enregistrer_filtre(charge["texte"], analyse["detections"], [], "caviardage")
    assert resultat["ok"], resultat
    produit = (tmp_path / "contrat_caviardé.pdf").read_bytes()
    # Le PDF caviardé n'est fait que d'images : il ne reste aucun texte à extraire.
    assert texte_du_pdf(produit).strip() == ""
    assert len(PdfReader(io.BytesIO(produit)).pages) == 1
    # Rien n'est rangé dans la table, et le journal dit que c'était un caviardage.
    assert a.etat()["ouverte"] and len(a._table) == 0
    assert a.journal()[0]["traitement"] == "caviardage"


@lecture_des_scans
def test_le_rectangle_noir_couvre_la_valeur(tmp_path):
    """Le PDF caviardé est relu par reconnaissance de caractères : la valeur n'y est plus, le reste si."""
    for contenu in (faux_pdf(LIGNES), scan(LIGNES)):
        lu = pdf.lire(contenu)
        debut = lu.texte.index("04 72")
        produit, perdus = pdf.caviarder(contenu, lu, [Detection(debut, debut + len(TELEPHONE), "TELEPHONE", 1, "x")])
        assert perdus == 0
        relu = ocr.lire_page_pdf(produit, 0)
        assert "88 77" not in relu and "04 72" not in relu
        assert "Contrat" in relu


def test_appli_caviarde_un_word_et_un_texte(tmp_path):
    document = Document()
    document.add_paragraph(f"Appeler le {TELEPHONE} avant vendredi.")
    document.save(str(tmp_path / "c.docx"))
    choix = {"fichier": str(tmp_path / "c.docx"), "enregistrer": str(tmp_path / "c_caviardé.docx")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("un-mot-de-passe")
    charge = a.ouvrir_fichier()
    analyse = a.analyser(charge["texte"])
    assert a.enregistrer_filtre(charge["texte"], analyse["detections"], [], "caviardage")["ok"]
    assert Document(str(tmp_path / "c_caviardé.docx")).paragraphs[0].text == f"Appeler le {MARQUE_CAVIARD} avant vendredi."

    # Texte collé : copié caviardé, ou enregistré en fichier texte.
    a.oublier()
    texte = f"Rappeler le {TELEPHONE}."
    analyse = a.analyser(texte)
    assert a.filtrer(texte, analyse["detections"], [], None, "caviardage")["texte"] == f"Rappeler le {MARQUE_CAVIARD}."
    choix["enregistrer"] = str(tmp_path / "texte_caviardé.txt")
    assert a.enregistrer_filtre(texte, analyse["detections"], [], "caviardage")["ok"]
    assert (tmp_path / "texte_caviardé.txt").read_text(encoding="utf-8") == f"Rappeler le {MARQUE_CAVIARD}."
    assert len(a._table) == 0


def test_un_dossier_caviarde(tmp_path):
    (tmp_path / "contrat.pdf").write_bytes(faux_pdf(LIGNES))
    (tmp_path / "note.txt").write_text(f"Rappeler le {TELEPHONE}.", encoding="utf-8")
    sortie = tmp_path / DOSSIER_CAVIARDE
    with Table.ouvrir(":memory:", "un-mot-de-passe", **OPTIONS) as table:
        resultats = traiter_dossier(tmp_path, sortie, regles_seules()[0], table, "caviardage")
        assert [r.ok for r in resultats] == [True, True]
        assert len(table) == 0
        # Un deuxième passage ne reprend pas les fichiers déjà produits.
        assert len(traiter_dossier(tmp_path, sortie, regles_seules()[0], table, "caviardage")) == 2
    assert texte_du_pdf((sortie / "contrat.pdf").read_bytes()).strip() == ""
    assert (sortie / "note.txt").read_text(encoding="utf-8") == f"Rappeler le {MARQUE_CAVIARD}."


def page_tamponnee() -> bytes:
    """Un PDF d'une page : trois lignes de texte, un tampon rond, une signature, un trait de soulignement."""
    from PIL import Image, ImageDraw, ImageFont
    from test_pdf import POLICE

    page = Image.new("L", (2480, 3508), 255)
    dessin = ImageDraw.Draw(page)
    police = ImageFont.truetype(str(POLICE), 60)
    for i, ligne in enumerate(LIGNES):
        dessin.text((250, 300 + i * 110), ligne, font=police, fill=0)
    dessin.line((250, 700, 2200, 700), fill=0, width=4)
    dessin.ellipse((1500, 1500, 2000, 2000), outline=60, width=14)
    dessin.ellipse((1560, 1560, 1940, 1940), outline=60, width=8)
    dessin.line([(400, 2400), (520, 2250), (600, 2420), (720, 2260), (830, 2400), (1000, 2330)], fill=0, width=9)
    sortie = io.BytesIO()
    page.save(sortie, "PDF", resolution=300)
    return sortie.getvalue()


@lecture_des_scans
def test_tampon_et_signature_sont_reperes_et_recouverts(tmp_path):
    import pypdfium2

    contenu = page_tamponnee()
    lu = pdf.lire(contenu)
    zones = pdf.zones_graphiques(contenu, lu)
    # Le tampon et la signature, mais ni le texte lu ni le trait de soulignement.
    assert len(zones) == 2 and {page for page, _ in zones} == {0}
    tampon, signature = (cadre for _, cadre in zones)
    assert tampon[0] < 1750 / 2480 < tampon[2] and tampon[1] < 1750 / 3508 < tampon[3]
    assert signature[0] < 700 / 2480 < signature[2] and signature[1] < 2350 / 3508 < signature[3]

    def encre(produit, cadre):
        """Part de points sombres dans le cadre, sur la page rendue."""
        image = pypdfium2.PdfDocument(produit)[0].render(scale=1).to_pil().convert("L")
        g, h, d, b = cadre
        decoupe = image.crop((int(g * image.width), int(h * image.height), int(d * image.width), int(b * image.height)))
        points = decoupe.tobytes()
        return sum(1 for p in points if p < 60) / len(points)

    sans, _ = pdf.caviarder(contenu, lu, [])
    avec, _ = pdf.caviarder(contenu, lu, [], zones)
    assert encre(sans, tampon) < 0.5 and encre(avec, tampon) > 0.95 and encre(avec, signature) > 0.95

    # Dans l'appli : zones rendues au chargement, toutes recouvertes par défaut, ou seulement celles choisies.
    (tmp_path / "t.pdf").write_bytes(contenu)
    choix = {"fichier": str(tmp_path / "t.pdf"), "enregistrer": str(tmp_path / "t_caviardé.pdf")}
    a = Api(":memory:", regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("un-mot-de-passe")
    charge = a.ouvrir_fichier()
    assert charge["pages"] == 1 and len(charge["zones"]) == 2
    assert a.image_page(0)["image"].startswith("data:image/jpeg;base64,")
    assert a.enregistrer_filtre(charge["texte"], [], [], "caviardage")["ok"]
    assert encre((tmp_path / "t_caviardé.pdf").read_bytes(), tampon) > 0.95
    main = {"page": 0, "cadre": [0.1, 0.9, 0.3, 0.95]}
    assert a.enregistrer_filtre(charge["texte"], [], [], "caviardage", None, [main])["ok"]
    produit = (tmp_path / "t_caviardé.pdf").read_bytes()
    assert encre(produit, tampon) < 0.5 and encre(produit, tuple(main["cadre"])) > 0.95


def test_un_pdf_de_texte_sans_image_n_a_pas_de_zone():
    contenu = faux_pdf(LIGNES)
    assert pdf.zones_graphiques(contenu, pdf.lire(contenu)) == []


def attendre(condition, delai=20.0):
    fin = time.time() + delai
    while time.time() < fin:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_dossier_surveille(tmp_path, monkeypatch):
    monkeypatch.setattr(module_api, "PERIODE_SURVEILLANCE", 0.05)
    dossier = tmp_path / "depots"
    dossier.mkdir()
    table = tmp_path / "t.celodata"
    choix = {"dossier": str(dossier), "enregistrer": str(tmp_path / "sortie.pdf")}
    a = Api(table, regles_seules, OPTIONS, dialogue=choix.get)
    a.ouvrir("un-mot-de-passe")
    assert a.surveillance() == {"dossier": "", "documents": []}
    assert a.choisir_dossier_surveille()["dossier"] == str(dossier)

    (dossier / "contrat.pdf").write_bytes(faux_pdf(LIGNES))
    (dossier / "contrat_caviardé.pdf").write_bytes(faux_pdf(LIGNES))  # un fichier produit n'est pas repris
    (dossier / "image.bmp").write_bytes(b"x")
    assert attendre(lambda: [d["etat"] for d in a.surveillance()["documents"]] == ["pret"])
    document = a.surveillance()["documents"][0]
    assert document["nom"] == "contrat.pdf" and document["masques"] >= 2
    # Rien n'a été écrit : le document attend d'être vérifié.
    assert sorted(f.name for f in dossier.iterdir()) == ["contrat.pdf", "contrat_caviardé.pdf", "image.bmp"]

    ouvert = a.ouvrir_surveille(document["id"])
    assert ouvert["ok"] and ouvert["pdf"] and len(ouvert["analyse"]["detections"]) == document["masques"]
    assert a.enregistrer_filtre(ouvert["texte"], ouvert["analyse"]["detections"], [], "caviardage")["ok"]
    assert a.surveillance()["documents"][0]["etat"] == "traite"
    assert texte_du_pdf((tmp_path / "sortie.pdf").read_bytes()).strip() == ""

    # Un fichier retiré du dossier disparaît de la liste.
    (dossier / "contrat.pdf").unlink()
    assert attendre(lambda: a.surveillance()["documents"] == [])
    a._arreter_surveillance()

    # Le dossier est retenu, chiffré, et la surveillance reprend à l'ouverture suivante.
    b = Api(table, regles_seules, OPTIONS, dialogue=choix.get)
    b.ouvrir("un-mot-de-passe")
    assert b.surveillance()["dossier"] == str(dossier)
    assert str(dossier).encode() not in table.read_bytes()
    assert b.arreter_surveillance()["dossier"] == ""
    c = Api(table, regles_seules, OPTIONS, dialogue=choix.get)
    c.ouvrir("un-mot-de-passe")
    assert c.surveillance()["dossier"] == ""

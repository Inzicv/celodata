"""Fabrique de faux fichiers pour essayer l'appli : Word, Excel, PDF et PDF scanné.

Ils sont tirés du jeu de faux documents (`jeu_de_test`) et rangés dans le dossier `essais`,
qui n'est pas versionné. Aucune donnée réelle.

    uv run python outils/fabriquer_essais.py
"""

import io
import textwrap
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEPOT = Path(__file__).parent.parent
JEU = DEPOT / "jeu_de_test"
SORTIE = DEPOT / "essais"
POLICES = [Path("C:/Windows/Fonts/times.ttf"), Path("C:/Windows/Fonts/arial.ttf")]


def lignes(nom: str) -> list[str]:
    return (JEU / nom).read_text(encoding="utf-8").split("\n")


def word(source: list[str], cible: Path) -> None:
    document = Document()
    document.core_properties.author = "Camille Faux-Nom"
    for ligne in source:
        paragraphe = document.add_paragraph()
        # Un mot sur trois en gras, pour vérifier que la mise en forme est gardée.
        mots = ligne.split(" ")
        for i, mot in enumerate(mots):
            paragraphe.add_run(mot + (" " if i < len(mots) - 1 else "")).bold = i % 3 == 0
    document.save(cible)


def excel(source: list[str], cible: Path) -> None:
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Clients"
    for ligne in source:
        feuille.append(ligne.split(";"))
    classeur.save(cible)


def pages(source: list[str], police: Path) -> list[Image.Image]:
    """Dessine le texte comme une page imprimée (A4 à 300 points par pouce)."""
    fonte = ImageFont.truetype(str(police), 44)
    coupees = []
    for ligne in source:
        coupees += textwrap.wrap(ligne, 95, break_long_words=False, break_on_hyphens=False) or [""]
    resultat = []
    for debut in range(0, len(coupees), 58):
        page = Image.new("L", (2480, 3508), 252)
        dessin = ImageDraw.Draw(page)
        for i, ligne in enumerate(coupees[debut : debut + 58]):
            dessin.text((220, 240 + i * 52), ligne, font=fonte, fill=20)
        resultat.append(page)
    return resultat


def pdf_scanne(source: list[str], cible: Path, police: Path) -> None:
    """Un PDF qui ne contient que des images, un peu de travers et floues, comme un vrai scan."""
    abimees = []
    for numero, page in enumerate(pages(source, police)):
        page = page.rotate(0.5 if numero % 2 else -0.4, fillcolor=252, resample=Image.BICUBIC)
        page = Image.blend(page.filter(ImageFilter.GaussianBlur(0.6)), Image.effect_noise(page.size, 12), 0.08)
        tampon = io.BytesIO()
        page.save(tampon, "JPEG", quality=70)
        abimees.append(Image.open(io.BytesIO(tampon.getvalue())))
    abimees[0].save(cible, "PDF", save_all=True, append_images=abimees[1:], resolution=300)


def pdf_texte(source: list[str], cible: Path) -> None:
    """Un PDF d'une page avec du vrai texte, écrit à la main pour ne dépendre d'aucun outil."""
    echapper = lambda l: l.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")  # noqa: E731
    texte = " ".join(f"({echapper(l)}) Tj T*" for l in source)
    flux = f"BT /F1 10 Tf 13 TL 50 790 Td {texte} ET".encode("cp1252", errors="replace")
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
    cible.write_bytes(sortie)


def main() -> None:
    SORTIE.mkdir(exist_ok=True)
    (SORTIE / "mail_paie.txt").write_text("\n".join(lignes("02_mail_paie.txt")), encoding="utf-8")
    word(lignes("04_contrat_travail.txt"), SORTIE / "contrat_travail.docx")
    excel(lignes("07_fichier_clients.txt"), SORTIE / "fichier_clients.xlsx")
    pdf_texte(lignes("06_mail_reclamation.txt"), SORTIE / "reclamation.pdf")
    police = next((p for p in POLICES if p.exists()), None)
    if police:
        pdf_scanne(lignes("10_note_rh.txt"), SORTIE / "note_rh_scannee.pdf", police)
    else:
        print("Police Windows introuvable : le faux scan n'a pas été fabriqué.")
    for fichier in sorted(SORTIE.iterdir()):
        if fichier.is_file():
            print(fichier.relative_to(DEPOT))


if __name__ == "__main__":
    main()

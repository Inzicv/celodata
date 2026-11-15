"""PDF lu avec la place de chaque caractère sur la page, et PDF caviardé.

Le caviardage d'un PDF rend un PDF neuf fait d'images : chaque page est rendue en image, les passages
retenus sont recouverts d'un rectangle noir, puis les images sont assemblées. Il ne reste aucun texte
sous les rectangles, ni rien de ce que le PDF d'origine pouvait cacher (propriétés, calques, pièces jointes).

Une page sans texte est un scan : elle est lue par la reconnaissance de caractères de Windows,
qui donne la place de chaque mot.
"""

import ctypes
import io
from dataclasses import dataclass, field

from celodata import ocr
from celodata.detection.base import Detection
from celodata.documents import DocumentIllisible

Cadre = tuple[float, float, float, float]  # gauche, haut, droite, bas, en fractions de la page

# Résolution des pages du PDF caviardé.
POINTS_PAR_POUCE = 200
_REPERE = 10000  # taille de la page fictive qui sert à convertir les coordonnées


@dataclass
class Zone:
    """Un morceau de texte (un caractère, ou un mot lu sur un scan) et sa place sur une page."""

    debut: int
    fin: int
    page: int
    cadre: Cadre


@dataclass
class PdfLu:
    texte: str
    zones: list[Zone] = field(default_factory=list)
    # Pages lues par reconnaissance de caractères : leur texte peut contenir des erreurs de lecture.
    pages_scannees: int = 0


def _ouvrir(contenu: bytes):
    import pypdfium2

    try:
        return pypdfium2.PdfDocument(io.BytesIO(contenu))
    except pypdfium2.PdfiumError as e:
        if "password" in str(e).lower():
            raise DocumentIllisible("Ce PDF est protégé par un mot de passe.") from None
        raise DocumentIllisible("PDF illisible.") from None
    except Exception as e:
        raise DocumentIllisible(f"PDF illisible ({type(e).__name__}).") from None


def _page_texte(page, numero: int, depart: int) -> tuple[str, list[Zone]]:
    """Le texte d'une page et la place de chaque caractère visible."""
    import pypdfium2.raw as pdfium

    feuille = page.get_textpage()
    x, y = ctypes.c_int(), ctypes.c_int()

    def point(px: float, py: float) -> tuple[float, float]:
        # Tient compte de la rotation de la page et de son cadre de rognage.
        pdfium.FPDF_PageToDevice(page, 0, 0, _REPERE, _REPERE, 0, px, py, ctypes.byref(x), ctypes.byref(y))
        return x.value / _REPERE, y.value / _REPERE

    caracteres: list[str] = []
    zones: list[Zone] = []
    try:
        for i in range(feuille.count_chars()):
            code = pdfium.FPDFText_GetUnicode(feuille, i)
            # 0 et le retour chariot ne sont pas du texte ; 2 marque une césure en fin de ligne.
            if code in (0, 13, 0xFFFE, 0xFFFF):
                continue
            caractere = "-" if code == 2 else chr(code)
            if not caractere.isspace():
                gauche, bas, droite, haut = feuille.get_charbox(i)
                if droite > gauche and haut > bas:
                    (x0, y0), (x1, y1) = point(gauche, haut), point(droite, bas)
                    position = depart + len(caracteres)
                    cadre = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                    zones.append(Zone(position, position + 1, numero, cadre))
            caracteres.append(caractere)
    finally:
        feuille.close()
    return "".join(caracteres), zones


def _page_scan(page, numero: int, depart: int) -> tuple[str, list[Zone]]:
    """Le texte d'une page scannée et la place de chaque mot."""
    lignes = ocr.lire_mots(page.render(scale=ocr.ECHELLE).to_pil())
    morceaux: list[str] = []
    zones: list[Zone] = []
    position = depart
    for ligne in lignes:
        for i, (mot, cadre) in enumerate(ligne):
            if i:
                morceaux.append(" ")
                position += 1
            zones.append(Zone(position, position + len(mot), numero, cadre))
            morceaux.append(mot)
            position += len(mot)
        morceaux.append("\n")
        position += 1
    return "".join(morceaux), zones


def lire(contenu: bytes, scans: bool = True) -> PdfLu:
    """Lit un PDF. Avec `scans=False`, un PDF scanné est refusé (traitement sans aperçu)."""
    document = _ouvrir(contenu)
    lu = PdfLu("")
    morceaux: list[str] = []
    longueur = 0
    try:
        for numero in range(len(document)):
            page = document[numero]
            texte, zones = _page_texte(page, numero, longueur)
            if not texte.strip():
                if not scans:
                    raise DocumentIllisible(
                        "PDF scanné : ouvrez-le dans l'appli, où le texte lu peut être vérifié avant d'être traité."
                    )
                try:
                    texte, zones = _page_scan(page, numero, longueur)
                except ocr.LectureImpossible as e:
                    raise DocumentIllisible(f"PDF scanné, impossible à lire : {e}") from None
                except Exception as e:
                    raise DocumentIllisible(f"PDF scanné, impossible à lire ({type(e).__name__}).") from None
                if texte.strip():
                    lu.pages_scannees += 1
            texte += "\n\n"
            morceaux.append(texte)
            lu.zones += zones
            longueur += len(texte)
    finally:
        document.close()
    # Les blancs de fin sont retirés : cela ne déplace aucun caractère.
    lu.texte = "".join(morceaux).rstrip()
    if not lu.texte.strip():
        raise DocumentIllisible("Aucun texte dans ce PDF, même en le lisant comme un document scanné.")
    return lu


def _rectangles(zones: list[Zone]) -> list[Cadre]:
    """Réunit les cadres voisins d'une même ligne, pour ne pas laisser de jour entre deux lettres."""
    sortie: list[list[float]] = []
    for zone in sorted(zones, key=lambda z: z.debut):
        g, h, d, b = zone.cadre
        if sortie:
            dernier = sortie[-1]
            hauteur = max(dernier[3] - dernier[1], b - h)
            meme_ligne = min(dernier[3], b) - max(dernier[1], h) > 0.4 * hauteur
            if meme_ligne and g >= dernier[0] - hauteur:
                dernier[:] = [min(dernier[0], g), min(dernier[1], h), max(dernier[2], d), max(dernier[3], b)]
                continue
        sortie.append([g, h, d, b])
    return [tuple(r) for r in sortie]


def caviarder(contenu: bytes, lu: PdfLu, detections: list[Detection]) -> tuple[bytes, int]:
    """Rend le PDF caviardé et le nombre de passages qui n'ont pas pu être placés sur une page.

    Un passage non placé n'est pas recouvert : l'appelant doit le signaler.
    """
    from PIL import ImageDraw
    from pypdf import PdfReader, PdfWriter

    par_page: dict[int, list[Cadre]] = {}
    perdus = 0
    for d in detections:
        zones = [z for z in lu.zones if z.debut < d.fin and z.fin > d.debut]
        if not zones:
            perdus += 1
        for page in {z.page for z in zones}:
            par_page.setdefault(page, []).extend(_rectangles([z for z in zones if z.page == page]))

    document = _ouvrir(contenu)
    sortie = PdfWriter()
    try:
        for numero in range(len(document)):
            image = document[numero].render(scale=POINTS_PAR_POUCE / 72).to_pil().convert("RGB")
            dessin = ImageDraw.Draw(image)
            largeur, hauteur = image.size
            for g, h, d, b in par_page.get(numero, []):
                # Une marge autour du texte : les jambages et les accents dépassent du cadre des lettres.
                marge = max(2.0, 0.18 * (b - h) * hauteur)
                dessin.rectangle(
                    (g * largeur - marge, h * hauteur - marge, d * largeur + marge, b * hauteur + marge), fill="black"
                )
            page = io.BytesIO()
            image.save(page, "PDF", resolution=POINTS_PAR_POUCE)
            page.seek(0)
            sortie.append(PdfReader(page))
    finally:
        document.close()
    sortie.add_metadata({"/Producer": "Celodata"})
    resultat = io.BytesIO()
    sortie.write(resultat)
    return resultat.getvalue(), perdus

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

from celodata import ocr, suivi
from celodata.detection.base import Detection
from celodata.documents import DocumentIllisible

Cadre = tuple[float, float, float, float]  # gauche, haut, droite, bas, en fractions de la page

# Résolution des pages du PDF caviardé.
POINTS_PAR_POUCE = 200
# Résolution de travail pour repérer ce qui n'est pas du texte : 2 points par millimètre environ.
_POINTS_REPERAGE = 50
# Plus petite zone gardée, en points de l'image de travail : environ 8 mm sur 5 mm.
_LARGEUR_MIN, _HAUTEUR_MIN = 16, 10
ZoneGraphique = tuple[int, Cadre]  # numéro de page, place sur la page
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
    pages: int = 0


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
        lu.pages = len(document)
        for numero in suivi.parcourir("lecture", range(len(document))):
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


def _composantes(encre, largeur: int, hauteur: int) -> list[tuple[int, int, int, int, int]]:
    """Les taches d'encre d'une image noir et blanc : (gauche, haut, droite, bas, nombre de points)."""
    points = bytearray(encre.tobytes())
    sortie = []
    depart = points.find(255)
    while depart != -1:
        points[depart] = 0
        pile = [depart]
        x0 = x1 = depart % largeur
        y0 = y1 = depart // largeur
        nombre = 0
        while pile:
            p = pile.pop()
            nombre += 1
            x, y = p % largeur, p // largeur
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for vy in (y - 1, y, y + 1):
                if 0 <= vy < hauteur:
                    for vx in (x - 1, x, x + 1):
                        if 0 <= vx < largeur and points[vy * largeur + vx]:
                            points[vy * largeur + vx] = 0
                            pile.append(vy * largeur + vx)
        sortie.append((x0, y0, x1, y1, nombre))
        depart = points.find(255, depart)
    return sortie


def _reunir(cadres: list[Cadre]) -> list[Cadre]:
    """Réunit les cadres qui se touchent : les deux cercles d'un tampon ne font qu'une zone."""
    restants = list(cadres)
    change = True
    while change:
        change = False
        sortie: list[Cadre] = []
        for g, h, d, b in restants:
            for i, (g2, h2, d2, b2) in enumerate(sortie):
                if g < d2 and g2 < d and h < b2 and h2 < b:
                    sortie[i] = (min(g, g2), min(h, h2), max(d, d2), max(b, b2))
                    change = True
                    break
            else:
                sortie.append((g, h, d, b))
        restants = sortie
    return restants


def zones_graphiques(contenu: bytes, lu: PdfLu) -> list[ZoneGraphique]:
    """Ce qui est de l'encre sans être du texte lu : tampon, signature, mot manuscrit, logo, photo.

    Chaque page est rendue en petit, le texte lu est effacé, et les taches qui restent sont gardées
    si elles sont assez grandes. Les traits fins (soulignés, cadres de tableau) sont écartés.
    C'est un repérage approché : il peut prendre un logo, ou un passage imprimé que la lecture a raté.
    """
    from PIL import ImageDraw, ImageFilter

    par_page: dict[int, list[Cadre]] = {}
    for zone in lu.zones:
        par_page.setdefault(zone.page, []).append(zone.cadre)
    document = _ouvrir(contenu)
    sortie: list[ZoneGraphique] = []
    try:
        for numero in suivi.parcourir("zones", range(len(document))):
            image = document[numero].render(scale=_POINTS_REPERAGE / 72).to_pil().convert("L")
            largeur, hauteur = image.size
            encre = image.point(lambda v: 255 if v < 200 else 0)
            dessin = ImageDraw.Draw(encre)
            for g, h, d, b in par_page.get(numero, []):
                dessin.rectangle((g * largeur - 2, h * hauteur - 2, d * largeur + 2, b * hauteur + 2), fill=0)
            # Les traits d'une signature ou d'un tampon sont réunis en une seule tache.
            encre = encre.filter(ImageFilter.MaxFilter(5))
            trouvees = []
            for x0, y0, x1, y1, nombre in _composantes(encre, largeur, hauteur):
                large, haut = x1 - x0 + 1, y1 - y0 + 1
                if large < _LARGEUR_MIN or haut < _HAUTEUR_MIN:
                    continue
                # Un cadre de tableau est grand et presque vide ; une page entière n'est pas une zone.
                if nombre < 0.15 * large * haut or large * haut > 0.6 * largeur * hauteur:
                    continue
                trouvees.append((x0 / largeur, y0 / hauteur, (x1 + 1) / largeur, (y1 + 1) / hauteur))
            sortie += [(numero, cadre) for cadre in sorted(_reunir(trouvees), key=lambda c: (c[1], c[0]))]
    finally:
        document.close()
    return sortie


def image_page(contenu: bytes, numero: int, points_par_pouce: int = 110) -> bytes:
    """La page `numero` en image JPEG, pour l'afficher à l'écran."""
    document = _ouvrir(contenu)
    try:
        image = document[numero].render(scale=points_par_pouce / 72).to_pil().convert("RGB")
    finally:
        document.close()
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=80)
    return sortie.getvalue()


def caviarder(
    contenu: bytes, lu: PdfLu, detections: list[Detection], zones: list[ZoneGraphique] | None = None
) -> tuple[bytes, int]:
    """Rend le PDF caviardé et le nombre de passages qui n'ont pas pu être placés sur une page.

    Un passage non placé n'est pas recouvert : l'appelant doit le signaler.
    `zones` : les zones sans texte à recouvrir aussi (tampons, signatures, zones tracées à la main).
    """
    from PIL import ImageDraw
    from pypdf import PdfReader, PdfWriter

    par_page: dict[int, list[Cadre]] = {}
    perdus = 0
    for d in detections:
        touchees = [z for z in lu.zones if z.debut < d.fin and z.fin > d.debut]
        if not touchees:
            perdus += 1
        for page in {z.page for z in touchees}:
            par_page.setdefault(page, []).extend(_rectangles([z for z in touchees if z.page == page]))

    document = _ouvrir(contenu)
    sortie = PdfWriter()
    try:
        for numero in range(len(document)):
            image = document[numero].render(scale=POINTS_PAR_POUCE / 72).to_pil().convert("RGB")
            dessin = ImageDraw.Draw(image)
            largeur, hauteur = image.size
            for page_zone, (g, h, d, b) in zones or []:
                if page_zone == numero:
                    dessin.rectangle((g * largeur - 3, h * hauteur - 3, d * largeur + 3, b * hauteur + 3), fill="black")
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

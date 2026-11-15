"""Lecture d'un PDF scanné : chaque page est rendue en image, puis lue par la reconnaissance
de caractères de Windows.

Tout se passe sur le poste : le moteur de Windows fonctionne hors ligne et aucun modèle n'est à
télécharger. Il faut que le français soit installé dans Windows (c'est le cas d'un Windows en français).

Une lecture de scan n'est jamais parfaite : un nom mal lu n'est pas reconnu par le détecteur.
Le texte obtenu doit toujours être relu dans l'aperçu avant envoi.
"""

import asyncio
import io

LANGUE = "fr-FR"
# 300 points par pouce : la résolution habituelle d'un scan de bureau.
ECHELLE = 300 / 72
COTE_MAX = 9000


class LectureImpossible(Exception):
    pass


def _moteur():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError:
        raise LectureImpossible("La lecture des documents scannés n'est disponible que sous Windows.") from None
    langue = Language(LANGUE)
    if not OcrEngine.is_language_supported(langue):
        raise LectureImpossible(
            "La lecture des documents scannés a besoin du français dans Windows "
            "(Paramètres > Heure et langue > Langue : ajouter « Français » avec la reconnaissance de caractères)."
        )
    return OcrEngine.try_create_from_language(langue)


def disponible() -> bool:
    try:
        return _moteur() is not None
    except LectureImpossible:
        return False


Cadre = tuple[float, float, float, float]  # gauche, haut, droite, bas, en fractions de la page


def lire_image(image) -> str:
    """Rend le texte d'une image (objet `PIL.Image`), ligne par ligne."""
    return "\n".join(" ".join(mot for mot, _ in ligne) for ligne in lire_mots(image))


def lire_mots(image) -> list[list[tuple[str, Cadre]]]:
    """Rend les mots d'une image, ligne par ligne, chacun avec sa place dans l'image.

    La place sert au caviardage : c'est là que le rectangle noir est posé.
    """
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    moteur = _moteur()
    if moteur is None:
        raise LectureImpossible("La reconnaissance de caractères de Windows ne démarre pas.")
    image = image.convert("L")
    if max(image.size) > COTE_MAX:
        image.thumbnail((COTE_MAX, COTE_MAX))
    ecrivain = DataWriter()
    ecrivain.write_bytes(image.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        ecrivain.detach_buffer(), BitmapPixelFormat.GRAY8, image.width, image.height
    )

    async def reconnaitre():
        return await moteur.recognize_async(bitmap)

    resultat = asyncio.run(reconnaitre())
    largeur, hauteur = image.size

    def cadre(mot) -> Cadre:
        r = mot.bounding_rect
        return (r.x / largeur, r.y / hauteur, (r.x + r.width) / largeur, (r.y + r.height) / hauteur)

    return [[(mot.text, cadre(mot)) for mot in ligne.words] for ligne in resultat.lines]


def lire_page_pdf(contenu: bytes, numero: int) -> str:
    """Rend en image la page `numero` (à partir de 0) d'un PDF et la lit."""
    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(contenu))
    try:
        return lire_image(document[numero].render(scale=ECHELLE).to_pil())
    finally:
        document.close()

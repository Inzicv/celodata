"""Extraction du texte d'un fichier : texte brut, Word (.docx), Excel (.xlsx), PDF, PDF scanné.

Tout se passe en mémoire : aucune copie du document n'est écrite sur disque.
La mise en forme n'est pas conservée, seul le texte est rendu.
"""

import io
from dataclasses import dataclass
from pathlib import Path

EXTENSIONS_TEXTE = {".txt", ".md", ".csv", ".log", ".json"}
EXTENSIONS = EXTENSIONS_TEXTE | {".docx", ".xlsx", ".pdf"}


class DocumentIllisible(Exception):
    pass


@dataclass
class Lecture:
    texte: str
    # Pages lues par reconnaissance de caractères : leur texte peut contenir des erreurs de lecture.
    pages_scannees: int = 0


def lire(nom: str, contenu: bytes, scans: bool = True) -> str:
    """Rend le texte d'un fichier d'après son extension."""
    return lire_detail(nom, contenu, scans).texte


def lire_detail(nom: str, contenu: bytes, scans: bool = True) -> Lecture:
    """Comme `lire`, en disant aussi combien de pages ont été lues comme des scans.

    Avec `scans=False`, un PDF scanné est refusé : c'est le cas du traitement sans aperçu.
    """
    extension = Path(nom).suffix.lower()
    pages_scannees = 0
    if extension in EXTENSIONS_TEXTE:
        texte = _texte_brut(contenu)
    elif extension == ".docx":
        texte = _docx(contenu)
    elif extension == ".pdf":
        texte, pages_scannees = _pdf(contenu, scans)
    elif extension == ".xlsx":
        from celodata.fichiers import ouvrir

        texte = ouvrir(nom, contenu).texte
    elif extension == ".doc":
        raise DocumentIllisible("L'ancien format Word (.doc) n'est pas lu : enregistrez le fichier en .docx.")
    elif extension == ".xls":
        raise DocumentIllisible("L'ancien format Excel (.xls) n'est pas lu : enregistrez le fichier en .xlsx.")
    else:
        raise DocumentIllisible(f"Type de fichier non pris en charge : {extension or nom}.")
    return Lecture(texte.replace("\r\n", "\n").replace("\r", "\n"), pages_scannees)


def lire_fichier(chemin: Path) -> str:
    return lire(chemin.name, chemin.read_bytes())


def _texte_brut(contenu: bytes) -> str:
    try:
        return contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Fichiers Windows anciens.
        return contenu.decode("cp1252", errors="replace")


def _docx(contenu: bytes) -> str:
    from docx import Document
    from docx.table import Table

    try:
        document = Document(io.BytesIO(contenu))
    except Exception as e:
        raise DocumentIllisible(f"Fichier Word illisible ({type(e).__name__}).") from None

    def lignes(conteneur) -> list[str]:
        sortie = []
        for element in conteneur.iter_inner_content():
            if isinstance(element, Table):
                for rangee in element.rows:
                    cellules, precedente = [], None
                    for cellule in rangee.cells:
                        # Une cellule fusionnée est rendue plusieurs fois : on ne la garde qu'une fois.
                        if cellule._tc is not precedente:
                            cellules.append("\n".join(lignes(cellule)).strip())
                        precedente = cellule._tc
                    sortie.append("\t".join(cellules))
            else:
                sortie.append(element.text)
        return sortie

    entetes, pieds, vus = [], [], set()
    for section in document.sections:
        for zone, cible in ((section.header, entetes), (section.footer, pieds)):
            if zone.is_linked_to_previous:
                continue
            texte = "\n".join(lignes(zone)).strip()
            if texte and texte not in vus:
                vus.add(texte)
                cible.append(texte)
    return "\n".join([*entetes, *lignes(document), *pieds])


def _pdf(contenu: bytes, scans: bool) -> tuple[str, int]:
    """Rend le texte du PDF et le nombre de pages lues comme des scans.

    Une page sans texte est une image : elle est lue par la reconnaissance de caractères si `scans` le permet.
    """
    from pypdf import PdfReader

    try:
        lecteur = PdfReader(io.BytesIO(contenu))
        if lecteur.is_encrypted and not lecteur.decrypt(""):
            raise DocumentIllisible("Ce PDF est protégé par un mot de passe.")
        pages = [(page.extract_text() or "").strip() for page in lecteur.pages]
    except DocumentIllisible:
        raise
    except Exception as e:
        raise DocumentIllisible(f"PDF illisible ({type(e).__name__}).") from None

    vides = [i for i, page in enumerate(pages) if not page]
    if vides:
        from celodata import ocr

        if not scans:
            raise DocumentIllisible(
                "PDF scanné : ouvrez-le dans l'appli, où le texte lu peut être vérifié avant d'être filtré."
            )
        try:
            for i in vides:
                pages[i] = ocr.lire_page_pdf(contenu, i).strip()
        except ocr.LectureImpossible as e:
            raise DocumentIllisible(f"PDF scanné, impossible à lire : {e}") from None
        except Exception as e:
            raise DocumentIllisible(f"PDF scanné, impossible à lire ({type(e).__name__}).") from None
    texte = "\n\n".join(p for p in pages if p)
    if not texte.strip():
        raise DocumentIllisible("Aucun texte dans ce PDF, même en le lisant comme un document scanné.")
    return texte, sum(1 for i in vides if pages[i])

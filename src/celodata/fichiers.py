"""Filtrer ou restaurer un fichier Word (.docx) ou Excel (.xlsx) en gardant son format.

Le fichier est vu comme une suite de pièces : des emplacements de texte qu'on peut réécrire
(un bout de phrase, une cellule) et des séparateurs (fin de paragraphe, tabulation). Mis bout à bout,
ils donnent le texte que lit le détecteur. Chaque remplacement est ensuite reporté dans les
emplacements d'origine, sans toucher à la mise en forme.

Tout se passe en mémoire.
"""

import datetime
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from celodata.detection.base import Detecteur, Detection
from celodata.documents import DocumentIllisible
from celodata.moteur import Remplacement, Restauration, analyser, remplacements_jetons, restaurer_avec_positions
from celodata.table import Table

FORMATS = {".docx", ".xlsx"}


@dataclass
class Piece:
    texte: str
    # Absent pour un séparateur.
    ecrire: Callable[[str], None] | None = None


class Formate:
    """Un fichier ouvert, vu comme une suite de pièces."""

    def __init__(self) -> None:
        self.pieces: list[Piece] = []
        # Ce que Celodata ne sait pas filtrer dans ce fichier, à dire à l'utilisateur.
        self.avertissements: list[str] = []

    @property
    def texte(self) -> str:
        return "".join(p.texte for p in self.pieces)

    def _emplacement(self, texte: str, ecrire: Callable[[str], None]) -> None:
        self.pieces.append(Piece(texte, ecrire))

    def _separateur(self, texte: str) -> None:
        self.pieces.append(Piece(texte))

    def decouper(self, detections: list[Detection]) -> list[Detection]:
        """Coupe aux séparateurs les passages qui en traversent un.

        Un nom à cheval sur deux cellules (« BERNARD », « Lucie ») donne ainsi un jeton par cellule :
        le tableau garde sa forme, à l'aller comme au retour.
        """
        texte = self.texte
        coupures, position = [], 0
        for piece in self.pieces:
            if piece.ecrire is None and piece.texte:
                coupures.append((position, position + len(piece.texte)))
            position += len(piece.texte)
        sortie = []
        for d in detections:
            debut = d.debut
            for a, b in [*[c for c in coupures if c[0] < d.fin and c[1] > d.debut], (d.fin, d.fin)]:
                fin = min(a, d.fin)
                # Les blancs en bord de morceau restent en place.
                while debut < fin and texte[debut].isspace():
                    debut += 1
                while fin > debut and texte[fin - 1].isspace():
                    fin -= 1
                if fin > debut:
                    sortie.append(Detection(debut, fin, d.type, d.score, d.source))
                debut = max(debut, b)
        return sortie

    def remplacer(self, remplacements: list[Remplacement]) -> None:
        """Reporte des remplacements, donnés en positions dans `texte`, dans les emplacements d'origine.

        Un passage à cheval sur plusieurs emplacements (un nom dont une partie est en gras) est remplacé
        dans le premier et retiré des suivants.
        """
        remplacements = sorted(remplacements)
        poses: set[int] = set()
        premier = position = 0
        for piece in self.pieces:
            debut, fin = position, position + len(piece.texte)
            position = fin
            while premier < len(remplacements) and remplacements[premier][1] <= debut:
                premier += 1
            if piece.ecrire is None or debut == fin:
                continue
            morceaux, curseur = [], debut
            for i in range(premier, len(remplacements)):
                a, b, nouveau = remplacements[i]
                if a >= fin:
                    break
                morceaux.append(piece.texte[curseur - debut : max(a, debut) - debut])
                if i not in poses:
                    morceaux.append(nouveau)
                    poses.add(i)
                curseur = min(b, fin)
            if morceaux:
                piece.texte = "".join([*morceaux, piece.texte[curseur - debut :]])
                piece.ecrire(piece.texte)

    def nettoyer_proprietes(self) -> None:
        """Vide les propriétés du fichier (auteur, société...), qui partiraient avec lui."""

    def enregistrer(self) -> bytes:
        raise NotImplementedError


# ---------- Word ----------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ESPACE = "{http://www.w3.org/XML/1998/namespace}space"
_TEXTES = {_W + "t", _W + "delText", _W + "instrText"}
_SAUTS = {_W + "tab": "\t", _W + "br": "\n", _W + "cr": "\n", _W + "noBreakHyphen": "-"}
_PROPRIETES = ("creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category", "Company", "Manager")


class Word(Formate):
    """Un .docx lu directement dans son archive : corps, en-têtes, pieds, notes, commentaires, zones de texte.

    Le texte supprimé en suivi des modifications est filtré lui aussi : il est toujours dans le fichier.
    """

    def __init__(self, contenu: bytes) -> None:
        super().__init__()
        from lxml import etree

        self._etree = etree
        try:
            with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
                self._entrees = [(info, archive.read(info)) for info in archive.infolist()]
        except (zipfile.BadZipFile, OSError):
            raise DocumentIllisible("Fichier Word illisible.") from None
        noms = [info.filename for info, _ in self._entrees]
        if "word/document.xml" not in noms:
            raise DocumentIllisible("Ce fichier n'est pas un document Word (.docx).")
        self._arbres: dict[str, object] = {}

        parties = sorted(
            (n for n in noms if re.fullmatch(r"word/[^/]+\.xml", n)), key=lambda n: (n != "word/document.xml", n)
        )
        for nom in parties:
            self._lire_partie(nom)
        # Liens externes : une adresse mail ou une URL interne peut s'y trouver.
        for nom in noms:
            if nom.endswith(".rels"):
                for lien in self._arbre(nom).iter("{*}Relationship"):
                    if lien.get("TargetMode") == "External" and lien.get("Target"):
                        self._emplacement(lien.get("Target"), lambda s, e=lien: e.set("Target", s))
                        self._separateur("\n")

        images = sum(n.startswith("word/media/") for n in noms)
        if images:
            self.avertissements.append(f"{images} image{'s' if images > 1 else ''} non filtrée{'s' if images > 1 else ''}")
        if any(n.startswith("word/embeddings/") for n in noms):
            self.avertissements.append("objets incorporés non filtrés")
        if "docProps/custom.xml" in noms:
            self.avertissements.append("propriétés personnalisées non filtrées")

    def _arbre(self, nom: str):
        if nom not in self._arbres:
            donnees = next(d for info, d in self._entrees if info.filename == nom)
            try:
                self._arbres[nom] = self._etree.fromstring(donnees)
            except self._etree.XMLSyntaxError:
                raise DocumentIllisible("Fichier Word illisible.") from None
        return self._arbres[nom]

    def _lire_partie(self, nom: str) -> None:
        def ecrire(element):
            def poser(texte: str) -> None:
                element.text = texte
                element.set(_ESPACE, "preserve")

            return poser

        for evenement, element in self._etree.iterwalk(self._arbre(nom), events=("start", "end")):
            if evenement == "start":
                if element.tag in _TEXTES:
                    self._emplacement(element.text or "", ecrire(element))
                elif element.tag in _SAUTS and element.getparent().tag == _W + "r":
                    # Hors d'un bout de phrase, « tab » décrit un taquet de tabulation, pas un caractère.
                    self._separateur(_SAUTS[element.tag])
            elif element.tag == _W + "p":
                self._separateur("\n")

    def nettoyer_proprietes(self) -> None:
        for nom in ("docProps/core.xml", "docProps/app.xml"):
            if any(info.filename == nom for info, _ in self._entrees):
                for element in self._arbre(nom).iter():
                    if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] in _PROPRIETES:
                        element.text = ""

    def enregistrer(self) -> bytes:
        sortie = io.BytesIO()
        with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as archive:
            for info, donnees in self._entrees:
                if info.filename in self._arbres:
                    donnees = self._etree.tostring(
                        self._arbres[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                archive.writestr(info.filename, donnees)
        return sortie.getvalue()


# ---------- Excel ----------


def _texte_cellule(valeur) -> str | None:
    """Le texte d'une cellule tel que le détecteur doit le lire. Un nombre peut être un SIRET ou un NIR."""
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, datetime.datetime):
        return valeur.strftime("%d/%m/%Y" if valeur.time() == datetime.time() else "%d/%m/%Y %H:%M")
    if isinstance(valeur, datetime.date):
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, float):
        return str(int(valeur)) if valeur.is_integer() else f"{valeur:.15g}"
    return None


class Excel(Formate):
    """Un .xlsx : noms de feuilles, cellules (texte, nombres, dates, formules), commentaires, liens."""

    def __init__(self, contenu: bytes) -> None:
        super().__init__()
        from openpyxl import load_workbook

        try:
            self._classeur = load_workbook(io.BytesIO(contenu))
            with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
                noms = archive.namelist()
        except Exception:
            raise DocumentIllisible("Fichier Excel illisible.") from None
        if any(n.startswith(("xl/charts/", "xl/media/", "xl/drawings/")) for n in noms):
            self.avertissements.append("graphiques et images non repris dans le fichier produit")

        def poser(objet, attribut):
            return lambda texte: setattr(objet, attribut, texte)

        for feuille in self._classeur.worksheets:
            self._emplacement(feuille.title, lambda s, f=feuille: setattr(f, "title", re.sub(r"[\[\]:*?/\\]", "_", s)[:31]))
            self._separateur("\n")
            for rangee in feuille.iter_rows():
                textes = [_texte_cellule(c.value) for c in rangee]
                if not any(t is not None for t in textes):
                    continue
                dernier = max(i for i, t in enumerate(textes) if t is not None)
                for cellule, texte in zip(rangee[: dernier + 1], textes):
                    if texte is not None:
                        self._emplacement(texte, poser(cellule, "value"))
                    self._separateur("\t")
                self._separateur("\n")
                for cellule in rangee[: dernier + 1]:
                    if getattr(cellule, "comment", None) is not None:
                        self._emplacement(cellule.comment.text or "", poser(cellule.comment, "text"))
                        self._separateur("\n")
                    lien = getattr(cellule, "hyperlink", None)
                    if lien is not None and lien.target:
                        self._emplacement(lien.target, poser(lien, "target"))
                        self._separateur("\n")

    def nettoyer_proprietes(self) -> None:
        proprietes = self._classeur.properties
        for nom in ("creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category"):
            setattr(proprietes, nom, "Celodata" if nom == "creator" else None)
        for feuille in self._classeur.worksheets:
            for rangee in feuille.iter_rows():
                for cellule in rangee:
                    if getattr(cellule, "comment", None) is not None:
                        cellule.comment.author = "Celodata"

    def enregistrer(self) -> bytes:
        sortie = io.BytesIO()
        self._classeur.save(sortie)
        return sortie.getvalue()


# ---------- filtrer et restaurer ----------


def ouvrir(nom: str, contenu: bytes) -> Formate:
    extension = Path(nom).suffix.lower()
    if extension == ".docx":
        return Word(contenu)
    if extension == ".xlsx":
        return Excel(contenu)
    raise DocumentIllisible(f"Format non pris en charge pour un fichier mis en forme : {extension or nom}.")


@dataclass
class FichierFiltre:
    contenu: bytes
    detections: list[Detection]
    avertissements: list[str] = field(default_factory=list)


def appliquer_filtrage(document: Formate, detections: list[Detection], table: Table) -> bytes:
    """Remplace dans le fichier les passages retenus et rend le fichier filtré."""
    document.remplacer(remplacements_jetons(document.texte, document.decouper(detections), table))
    document.nettoyer_proprietes()
    return document.enregistrer()


def filtrer_fichier(nom: str, contenu: bytes, detecteur: Detecteur, table: Table) -> FichierFiltre:
    document = ouvrir(nom, contenu)
    detections = document.decouper(analyser(document.texte, detecteur, table))
    return FichierFiltre(appliquer_filtrage(document, detections, table), detections, document.avertissements)


def restaurer_fichier(nom: str, contenu: bytes, table: Table) -> tuple[bytes, Restauration]:
    """Remet les vraies valeurs dans un fichier rendu par l'IA."""
    document = ouvrir(nom, contenu)
    bilan, remplacements = restaurer_avec_positions(document.texte, table)
    document.remplacer(remplacements)
    return document.enregistrer(), bilan

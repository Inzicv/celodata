"""Ce que l'écran peut demander au moteur. Aucun texte collé n'est écrit sur disque ici.

Tous les attributs commencent par un tiret bas : pywebview n'expose à l'écran que les méthodes
publiques.
"""

import base64
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from celodata import journal, pdf
from celodata.detection.base import Detecteur, Detection
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.listes import fonctions_a_verifier
from celodata.documents import EXTENSIONS, EXTENSIONS_TEXTE, DocumentIllisible, lire, lire_detail
from celodata.fichiers import (
    FORMATS,
    appliquer_caviardage,
    appliquer_filtrage,
    ouvrir,
    restaurer_fichier,
    texte_en_word,
)
from celodata.lot import dossier_sortie, traiter_dossier
from celodata.moteur import analyser, caviarder, pseudonymiser, restaurer
from celodata.table import MotDePasseIncorrect, Table

LONGUEUR_MIN_MOT_DE_PASSE = 8
_TYPE_VALIDE = re.compile(r"[A-Z][A-Z_]*")
CAVIARDAGE = "caviardage"
# Le dossier surveillé est relu à cet intervalle, en secondes.
PERIODE_SURVEILLANCE = 2.0
# Fichiers produits par l'appli : ils ne sont pas repris par la surveillance.
_PRODUITS = ("_filtré", "_caviardé", "_restauré")


@dataclass
class _Charge:
    """Un fichier Word, Excel ou PDF gardé en mémoire, pour l'enregistrer filtré ou caviardé."""

    nom: str
    contenu: bytes
    texte: str
    # Pour un PDF : la place de chaque caractère sur les pages.
    lu: pdf.PdfLu | None = None
    # Pour un PDF : les zones sans texte repérées (tampons, signatures), en (page, cadre).
    zones: tuple = ()


def detecteur_par_defaut() -> tuple[Detecteur, bool]:
    """Rend le détecteur complet, ou les règles seules si le modèle d'entités est absent."""
    from celodata.detection.modeles import DETECTEURS, MODELE_PAR_DEFAUT
    from celodata.detection.regles import DetecteurRegles

    regles = DetecteurRegles()
    try:
        modele = DETECTEURS[MODELE_PAR_DEFAUT]()
    except Exception:
        return DetecteurCompose("regles", [regles]), False
    return DetecteurCompose("celodata", [regles, modele]), True


class Api:
    def __init__(
        self,
        chemin_table: Path | str,
        fabrique: Callable[[], tuple[Detecteur, bool]] = detecteur_par_defaut,
        options_table: dict | None = None,
        dialogue: Callable[..., str | None] | None = None,
    ) -> None:
        self._chemin = chemin_table
        self._fabrique = fabrique
        self._options_table = options_table or {}
        # `dialogue("fichier")`, `dialogue("dossier")` ou `dialogue("enregistrer", nom proposé)`
        # ouvre la boîte de Windows et rend un chemin.
        self._dialogue = dialogue
        self._table: Table | None = None
        self._detecteur: Detecteur | None = None
        self._avec_modele = False
        self._derniere: dict[tuple[int, int, str], Detection] = {}
        # Dernier fichier Word, Excel ou PDF chargé.
        self._charge: _Charge | None = None
        self._verrou = threading.Lock()
        # Dossier surveillé : les documents qui y sont déposés sont analysés en tâche de fond.
        self._surveille: Path | None = None
        self._documents: dict[str, dict] = {}
        self._ouvert: str | None = None
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None

    def etat(self) -> dict:
        existe = str(self._chemin) != ":memory:" and Path(self._chemin).exists()
        return {"table_existe": existe, "ouverte": self._table is not None, "chemin": str(self._chemin)}

    def ouvrir(self, mot_de_passe: str) -> dict:
        with self._verrou:
            nouvelle = not self.etat()["table_existe"]
            if nouvelle and len(mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE:
                return {"ok": False, "erreur": f"Le mot de passe doit faire au moins {LONGUEUR_MIN_MOT_DE_PASSE} caractères."}
            try:
                if str(self._chemin) != ":memory:":
                    Path(self._chemin).parent.mkdir(parents=True, exist_ok=True)
                self._table = Table.ouvrir(self._chemin, mot_de_passe, **self._options_table)
            except MotDePasseIncorrect:
                return {"ok": False, "erreur": "Mot de passe incorrect."}
            dossier = self._table.reglage("dossier_surveille")
        if dossier and Path(dossier).is_dir():
            self._demarrer_surveillance(Path(dossier))
        return {"ok": True, "valeurs": len(self._table)}

    def preparer(self) -> dict:
        """Charge le détecteur. Le modèle d'entités met plusieurs secondes à se charger."""
        with self._verrou:
            if self._detecteur is None:
                self._detecteur, self._avec_modele = self._fabrique()
            return {"modele": self._avec_modele}

    # ---------- filtrer et restaurer ----------

    def _analyser(self, texte: str) -> tuple[list[Detection], list[Detection]]:
        """Les passages à masquer et les fonctions « à vérifier ». Le verrou doit être tenu."""
        detections = analyser(texte, self._detecteur, self._table)
        suggestions = [
            s
            for s in fonctions_a_verifier(texte)
            if all(s.fin <= d.debut or s.debut >= d.fin for d in detections)
            and not self._table.est_ignoree(texte[s.debut : s.fin])
        ]
        return detections, suggestions

    def _analyse(self, detections: list[Detection], suggestions: list[Detection]) -> dict:
        self._derniere = {(d.debut, d.fin, d.type): d for d in detections}
        return {
            "modele": self._avec_modele,
            "detections": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in detections],
            "suggestions": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in suggestions],
        }

    def analyser(self, texte: str) -> dict:
        self.preparer()
        with self._verrou:
            return self._analyse(*self._analyser(texte))

    def _valider(self, texte: str, detections: list[dict], retirees: list[str]) -> list[Detection]:
        """Les passages validés dans l'aperçu. Les corrections deviennent la mémoire du projet."""
        # Un passage ajouté à la main n'est pas dans la dernière analyse : sa source est « manuel ».
        retenues = [
            self._derniere.get(
                (d["debut"], d["fin"], d["type"]), Detection(d["debut"], d["fin"], d["type"], 1.0, "manuel")
            )
            for d in detections
        ]
        for valeur in retirees:
            self._table.ignorer(valeur)
        for d in retenues:
            self._table.ne_plus_ignorer(texte[d.debut : d.fin])
        return retenues

    def _nom_detecteur(self) -> str:
        return self._detecteur.nom if self._detecteur else ""

    def _journaliser(self, retenues: list[Detection], fichier: str | None, traitement: str) -> None:
        journal.filtrage(
            self._table,
            retenues,
            mode="apercu",
            detecteur=self._nom_detecteur(),
            fichier=fichier or None,
            traitement=CAVIARDAGE if traitement == CAVIARDAGE else "pseudonymisation",
        )

    def filtrer(
        self,
        texte: str,
        detections: list[dict],
        retirees: list[str],
        fichier: str | None = None,
        traitement: str = "pseudonymisation",
    ) -> dict:
        """Rend le texte où les passages validés dans l'aperçu sont remplacés par des jetons, ou caviardés."""
        with self._verrou:
            retenues = self._valider(texte, detections, retirees)
            try:
                if traitement == CAVIARDAGE:
                    filtrage = caviarder(texte, retenues)
                else:
                    filtrage = pseudonymiser(texte, retenues, self._table)
            except ValueError as e:
                return {"ok": False, "erreur": str(e)}
            self._journaliser(retenues, fichier, traitement)
            return {"ok": True, "texte": filtrage.texte, "par_type": dict(filtrage.par_type)}

    def enregistrer_filtre(
        self,
        texte: str,
        detections: list[dict],
        retirees: list[str],
        traitement: str = "pseudonymisation",
        fichier: str | None = None,
        zones: list[dict] | None = None,
    ) -> dict:
        """Enregistre le document traité.

        `zones` : pour un PDF caviardé, les zones sans texte à recouvrir, en {page, cadre}.
        Sans cette liste, toutes les zones repérées au chargement sont recouvertes.

        Pseudonymisé : un Word ou un Excel reste dans son format, un PDF devient un Word.
        Caviardé : un Word ou un Excel reste dans son format, un PDF devient un PDF fait d'images.
        Un texte collé ou un fichier texte donne un fichier texte.
        """
        caviardage = traitement == CAVIARDAGE
        charge = self._charge
        if charge and texte != charge.texte:
            return {"ok": False, "erreur": "Le texte ne correspond plus au fichier chargé : rechargez le fichier."}
        nom = charge.nom if charge else (fichier or "texte.txt")
        est_pdf = charge is not None and charge.lu is not None
        if est_pdf:
            extension = ".pdf" if caviardage else ".docx"
        else:
            extension = Path(nom).suffix if charge else ".txt"
        propose = f"{Path(nom).stem}{'_caviardé' if caviardage else '_filtré'}{extension}"
        chemin = self._dialogue("enregistrer", propose) if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        avertissements: list[str] = []
        with self._verrou:
            retenues = self._valider(texte, detections, retirees)
            try:
                if est_pdf and caviardage:
                    if zones is None:
                        a_couvrir = list(charge.zones)
                    else:
                        a_couvrir = [(int(z["page"]), tuple(float(v) for v in z["cadre"])) for z in zones]
                    produit, perdus = pdf.caviarder(charge.contenu, charge.lu, retenues, a_couvrir)
                    if perdus:
                        return {
                            "ok": False,
                            "erreur": f"{perdus} passage(s) n'ont pas pu être placés sur la page : "
                            "le PDF caviardé n'a pas été enregistré.",
                        }
                elif est_pdf:
                    produit = texte_en_word(pseudonymiser(texte, retenues, self._table).texte)
                elif charge:
                    document = ouvrir(charge.nom, charge.contenu)
                    avertissements = document.avertissements
                    if caviardage:
                        produit = appliquer_caviardage(document, retenues)
                    else:
                        produit = appliquer_filtrage(document, retenues, self._table)
                elif caviardage:
                    produit = caviarder(texte, retenues).texte.encode("utf-8")
                else:
                    produit = pseudonymiser(texte, retenues, self._table).texte.encode("utf-8")
                Path(chemin).write_bytes(produit)
            except (ValueError, DocumentIllisible, OSError) as e:
                return {"ok": False, "erreur": str(e)}
            self._journaliser(retenues, nom if charge or fichier else None, traitement)
            if self._ouvert in self._documents:
                self._documents[self._ouvert]["etat"] = "traite"
        return {"ok": True, "chemin": str(chemin), "avertissements": avertissements}

    def restaurer(self, texte: str) -> dict:
        with self._verrou:
            r = restaurer(texte, self._table)
            journal.restauration(self._table, r)
        return {"texte": r.texte, "inconnus": r.inconnus, "approximatifs": r.approximatifs}

    # ---------- fichiers ----------

    @staticmethod
    def _lire(nom: str, contenu: bytes) -> tuple[str, _Charge | None, int]:
        """Rend le texte du fichier, de quoi l'enregistrer dans son format, et le nombre de pages scannées."""
        extension = Path(nom).suffix.lower()
        if extension == ".pdf":
            lu = pdf.lire(contenu)
            zones = tuple(pdf.zones_graphiques(contenu, lu))
            return lu.texte, _Charge(nom, contenu, lu.texte, lu, zones), lu.pages_scannees
        if extension in FORMATS:
            # Le texte vient des emplacements du fichier, pour y reporter ensuite les remplacements.
            texte = ouvrir(nom, contenu).texte
            return texte, (_Charge(nom, contenu, texte) if "\r" not in texte else None), 0
        return lire_detail(nom, contenu).texte, None, 0

    def _charger(self, nom: str, contenu: bytes) -> dict:
        self._charge = self._ouvert = None
        try:
            texte, self._charge, pages_scannees = self._lire(nom, contenu)
        except DocumentIllisible as e:
            return {"ok": False, "erreur": str(e)}
        return {
            "ok": True,
            "nom": nom,
            "texte": texte,
            "format": self._charge is not None,
            **self._pages(self._charge),
            # Pages lues par reconnaissance de caractères : l'écran demande de relire l'aperçu.
            "pages_scannees": pages_scannees,
        }

    @staticmethod
    def _pages(charge: _Charge | None) -> dict:
        """Pour un PDF : le nombre de pages et les zones sans texte repérées (tampons, signatures)."""
        if charge is None or charge.lu is None:
            return {"pdf": False, "pages": 0, "zones": []}
        return {
            "pdf": True,
            "pages": charge.lu.pages,
            "zones": [{"page": page, "cadre": list(cadre)} for page, cadre in charge.zones],
        }

    def image_page(self, numero: int) -> dict:
        """Une page du PDF chargé, en image, pour la vue « Pages ». Rien n'est écrit sur disque."""
        charge = self._charge
        if charge is None or charge.lu is None:
            return {"ok": False, "erreur": "Aucun PDF n'est chargé."}
        try:
            image = pdf.image_page(charge.contenu, int(numero))
        except Exception as e:
            return {"ok": False, "erreur": f"Page impossible à afficher ({type(e).__name__})."}
        return {"ok": True, "image": "data:image/jpeg;base64," + base64.b64encode(image).decode()}

    def oublier(self) -> dict:
        """L'écran repart d'une page vide : le fichier gardé en mémoire est oublié."""
        self._charge = self._ouvert = None
        return {"ok": True}

    def lire_fichier(self, nom: str, contenu_base64: str) -> dict:
        """Rend le texte d'un fichier déposé dans la fenêtre. Rien n'est écrit sur disque."""
        return self._charger(nom, base64.b64decode(contenu_base64))

    def ouvrir_fichier(self) -> dict:
        chemin = self._dialogue("fichier") if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        try:
            return self._charger(Path(chemin).name, Path(chemin).read_bytes())
        except OSError as e:
            return {"ok": False, "erreur": str(e)}

    def restaurer_fichier(self) -> dict:
        """Restaure un fichier rendu par l'IA (Word, Excel ou texte) et l'enregistre où l'utilisateur le choisit."""
        source = self._dialogue("fichier") if self._dialogue else None
        if not source:
            return {"ok": False, "annule": True}
        source = Path(source)
        extension = source.suffix.lower()
        if extension not in FORMATS | EXTENSIONS_TEXTE:
            return {"ok": False, "erreur": "Seuls les fichiers Word (.docx), Excel (.xlsx) et texte peuvent être restaurés."}
        try:
            contenu = source.read_bytes()
            with self._verrou:
                if extension in FORMATS:
                    produit, bilan = restaurer_fichier(source.name, contenu, self._table)
                else:
                    bilan = restaurer(lire(source.name, contenu), self._table)
                    produit = bilan.texte.encode("utf-8")
                journal.restauration(self._table, bilan)
            cible = self._dialogue("enregistrer", f"{source.stem}_restauré{source.suffix}")
            if not cible:
                return {"ok": False, "annule": True}
            Path(cible).write_bytes(produit)
        except (DocumentIllisible, OSError) as e:
            return {"ok": False, "erreur": str(e)}
        return {"ok": True, "chemin": str(cible), "inconnus": bilan.inconnus, "approximatifs": bilan.approximatifs}

    def filtrer_dossier(self, traitement: str = "pseudonymisation") -> dict:
        """Traite tous les documents d'un dossier, sans aperçu, vers un sous-dossier."""
        chemin = self._dialogue("dossier") if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        self.preparer()
        traitement = CAVIARDAGE if traitement == CAVIARDAGE else "pseudonymisation"
        sortie = Path(chemin) / dossier_sortie(traitement)
        with self._verrou:
            resultats = traiter_dossier(Path(chemin), sortie, self._detecteur, self._table, traitement)
        return {
            "ok": True,
            "dossier": str(chemin),
            "sortie": str(sortie),
            "traitement": traitement,
            "modele": self._avec_modele,
            "fichiers": [asdict(r) for r in resultats],
        }

    # ---------- dossier surveillé ----------

    def choisir_dossier_surveille(self) -> dict:
        chemin = self._dialogue("dossier") if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        with self._verrou:
            self._table.regler("dossier_surveille", str(chemin))
        self._demarrer_surveillance(Path(chemin))
        return {"ok": True, **self.surveillance()}

    def arreter_surveillance(self) -> dict:
        self._arreter_surveillance()
        with self._verrou:
            self._table.regler("dossier_surveille", None)
        return {"ok": True, **self.surveillance()}

    def surveillance(self) -> dict:
        """Le dossier surveillé et l'état de chaque document qui y a été trouvé. Aucune vraie valeur ici."""
        return {
            "dossier": str(self._surveille) if self._surveille else "",
            "documents": [
                {
                    "id": cle,
                    "nom": d["nom"],
                    "etat": d["etat"],
                    "masques": len(d.get("detections", [])),
                    "a_verifier": len(d.get("suggestions", [])),
                    "pages_scannees": d.get("pages_scannees", 0),
                    "erreur": d.get("erreur", ""),
                }
                for cle, d in list(self._documents.items())
            ],
        }

    def ouvrir_surveille(self, identifiant: str) -> dict:
        """Ouvre dans l'aperçu un document du dossier surveillé, déjà analysé."""
        with self._verrou:
            d = self._documents.get(identifiant)
            if not d or "texte" not in d:
                return {"ok": False, "erreur": "Ce document n'est pas prêt."}
            self._charge, self._ouvert = d["charge"], identifiant
            return {
                "ok": True,
                "nom": d["nom"],
                "texte": d["texte"],
                "format": d["charge"] is not None,
                **self._pages(d["charge"]),
                "pages_scannees": d["pages_scannees"],
                "analyse": self._analyse(d["detections"], d["suggestions"]),
            }

    def _demarrer_surveillance(self, dossier: Path) -> None:
        self._arreter_surveillance()
        self._surveille = dossier
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._surveiller, args=(dossier, self._arret), daemon=True)
        self._fil.start()

    def _arreter_surveillance(self) -> None:
        self._arret.set()
        if self._fil and self._fil is not threading.current_thread():
            self._fil.join(timeout=30)
        self._fil, self._surveille = None, None
        self._documents = {}

    def _surveiller(self, dossier: Path, arret: threading.Event) -> None:
        """Analyse chaque document déposé dans le dossier. Rien n'est écrit : l'aperçu reste à valider."""
        tailles: dict[str, tuple[int, float]] = {}
        faits: dict[str, tuple[int, float]] = {}
        while not arret.is_set():
            try:
                fichiers = sorted(f for f in dossier.iterdir() if f.is_file())
            except OSError:
                fichiers = []
            for f in fichiers:
                if arret.is_set():
                    return
                if f.suffix.lower() not in EXTENSIONS or f.name.startswith("~$") or f.stem.endswith(_PRODUITS):
                    continue
                try:
                    etat = f.stat()
                except OSError:
                    continue
                cle, signature = str(f), (etat.st_size, etat.st_mtime)
                if faits.get(cle) == signature:
                    continue
                # Un fichier en cours de copie change encore de taille : on attend qu'il soit stable.
                if tailles.get(cle) != signature:
                    tailles[cle] = signature
                    continue
                faits[cle] = signature
                self._preparer_document(cle, f, arret)
            for cle in [c for c in self._documents if not Path(c).exists()]:
                self._documents.pop(cle, None)
                faits.pop(cle, None)
            arret.wait(PERIODE_SURVEILLANCE)

    def _preparer_document(self, cle: str, fichier: Path, arret: threading.Event) -> None:
        self._documents[cle] = {"nom": fichier.name, "etat": "analyse"}
        try:
            texte, charge, pages_scannees = self._lire(fichier.name, fichier.read_bytes())
            self.preparer()
            with self._verrou:
                detections, suggestions = self._analyser(texte)
        except (DocumentIllisible, OSError) as e:
            resultat = {"nom": fichier.name, "etat": "erreur", "erreur": str(e)}
        except Exception as e:
            resultat = {"nom": fichier.name, "etat": "erreur", "erreur": f"Analyse impossible ({type(e).__name__})."}
        else:
            resultat = {
                "nom": fichier.name,
                "etat": "pret",
                "texte": texte,
                "charge": charge,
                "pages_scannees": pages_scannees,
                "detections": detections,
                "suggestions": suggestions,
            }
        if not arret.is_set():
            self._documents[cle] = resultat

    # ---------- règles du projet ----------

    def regles(self) -> dict:
        with self._verrou:
            return {"regles": self._table.regles(), "jamais": self._table.ignorees()}

    def ajouter_regle(self, genre: str, texte: str, type_: str = "AUTRE") -> dict:
        texte = texte.strip()
        if len(texte) < 2:
            return {"ok": False, "erreur": "Le texte de la règle est trop court."}
        with self._verrou:
            if genre == "jamais":
                self._table.ignorer(texte)
                return {"ok": True}
            if not _TYPE_VALIDE.fullmatch(type_):
                return {"ok": False, "erreur": "Type invalide."}
            if genre == "motif":
                try:
                    if re.compile(texte).search(""):
                        return {"ok": False, "erreur": "Ce motif correspond à un texte vide."}
                except re.error as e:
                    return {"ok": False, "erreur": f"Motif invalide : {e}"}
            elif genre == "terme":
                self._table.ne_plus_ignorer(texte)
            else:
                return {"ok": False, "erreur": "Genre de règle inconnu."}
            self._table.ajouter_regle(genre, texte, type_)
            return {"ok": True}

    def supprimer_regle(self, identifiant: int) -> dict:
        with self._verrou:
            self._table.supprimer_regle(int(identifiant))
        return {"ok": True}

    def ne_plus_ignorer(self, texte: str) -> dict:
        with self._verrou:
            self._table.ne_plus_ignorer(texte)
        return {"ok": True}

    def journal(self) -> list[dict]:
        with self._verrou:
            return self._table.journal()

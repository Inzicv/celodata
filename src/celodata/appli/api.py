"""Ce que l'écran peut demander au moteur. Aucun texte collé n'est écrit sur disque ici.

Tous les attributs commencent par un tiret bas : pywebview n'expose à l'écran que les méthodes
publiques.
"""

import base64
import re
import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from celodata import journal
from celodata.detection.base import Detecteur, Detection
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.listes import fonctions_a_verifier
from celodata.documents import DocumentIllisible, lire, lire_fichier
from celodata.lot import DOSSIER_SORTIE, traiter_dossier
from celodata.moteur import analyser, pseudonymiser, restaurer
from celodata.table import MotDePasseIncorrect, Table

LONGUEUR_MIN_MOT_DE_PASSE = 8
_TYPE_VALIDE = re.compile(r"[A-Z][A-Z_]*")


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
        dialogue: Callable[[str], str | None] | None = None,
    ) -> None:
        self._chemin = chemin_table
        self._fabrique = fabrique
        self._options_table = options_table or {}
        # `dialogue("fichier")` ou `dialogue("dossier")` ouvre la boîte de Windows et rend un chemin.
        self._dialogue = dialogue
        self._table: Table | None = None
        self._detecteur: Detecteur | None = None
        self._avec_modele = False
        self._derniere: dict[tuple[int, int, str], Detection] = {}
        self._verrou = threading.Lock()

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
            return {"ok": True, "valeurs": len(self._table)}

    def preparer(self) -> dict:
        """Charge le détecteur. Le modèle d'entités met plusieurs secondes à se charger."""
        with self._verrou:
            if self._detecteur is None:
                self._detecteur, self._avec_modele = self._fabrique()
            return {"modele": self._avec_modele}

    # ---------- filtrer et restaurer ----------

    def analyser(self, texte: str) -> dict:
        self.preparer()
        with self._verrou:
            detections = analyser(texte, self._detecteur, self._table)
            suggestions = [
                s
                for s in fonctions_a_verifier(texte)
                if all(s.fin <= d.debut or s.debut >= d.fin for d in detections)
                and not self._table.est_ignoree(texte[s.debut : s.fin])
            ]
            self._derniere = {(d.debut, d.fin, d.type): d for d in detections}
        return {
            "modele": self._avec_modele,
            "detections": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in detections],
            "suggestions": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in suggestions],
        }

    def filtrer(self, texte: str, detections: list[dict], retirees: list[str], fichier: str | None = None) -> dict:
        """Remplace les passages validés dans l'aperçu. Les corrections deviennent la mémoire du projet."""
        with self._verrou:
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
            try:
                filtrage = pseudonymiser(texte, retenues, self._table)
            except ValueError as e:
                return {"ok": False, "erreur": str(e)}
            nom = self._detecteur.nom if self._detecteur else ""
            journal.filtrage(self._table, retenues, mode="apercu", detecteur=nom, fichier=fichier or None)
            return {"ok": True, "texte": filtrage.texte, "par_type": dict(filtrage.par_type)}

    def restaurer(self, texte: str) -> dict:
        with self._verrou:
            r = restaurer(texte, self._table)
            journal.restauration(self._table, r)
        return {"texte": r.texte, "inconnus": r.inconnus, "approximatifs": r.approximatifs}

    # ---------- fichiers ----------

    def lire_fichier(self, nom: str, contenu_base64: str) -> dict:
        """Rend le texte d'un fichier déposé dans la fenêtre. Rien n'est écrit sur disque."""
        try:
            return {"ok": True, "nom": nom, "texte": lire(nom, base64.b64decode(contenu_base64))}
        except DocumentIllisible as e:
            return {"ok": False, "erreur": str(e)}

    def ouvrir_fichier(self) -> dict:
        chemin = self._dialogue("fichier") if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        try:
            return {"ok": True, "nom": Path(chemin).name, "texte": lire_fichier(Path(chemin))}
        except (DocumentIllisible, OSError) as e:
            return {"ok": False, "erreur": str(e)}

    def filtrer_dossier(self) -> dict:
        """Filtre tous les documents d'un dossier, sans aperçu, vers un sous-dossier."""
        chemin = self._dialogue("dossier") if self._dialogue else None
        if not chemin:
            return {"ok": False, "annule": True}
        self.preparer()
        sortie = Path(chemin) / DOSSIER_SORTIE
        with self._verrou:
            resultats = traiter_dossier(Path(chemin), sortie, self._detecteur, self._table)
        return {
            "ok": True,
            "dossier": str(chemin),
            "sortie": str(sortie),
            "modele": self._avec_modele,
            "fichiers": [asdict(r) for r in resultats],
        }

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

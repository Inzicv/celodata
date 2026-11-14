"""Ce que l'écran peut demander au moteur. Aucun texte n'est écrit sur disque ici.

Tous les attributs commencent par un tiret bas : pywebview n'expose à l'écran que les méthodes
publiques.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from celodata.detection.base import Detecteur, Detection
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.listes import fonctions_a_verifier
from celodata.moteur import analyser, pseudonymiser, restaurer
from celodata.table import MotDePasseIncorrect, Table

LONGUEUR_MIN_MOT_DE_PASSE = 8


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
    ) -> None:
        self._chemin = chemin_table
        self._fabrique = fabrique
        self._options_table = options_table or {}
        self._table: Table | None = None
        self._detecteur: Detecteur | None = None
        self._avec_modele = False
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
        return {
            "modele": self._avec_modele,
            "detections": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in detections],
            "suggestions": [{"debut": d.debut, "fin": d.fin, "type": d.type} for d in suggestions],
        }

    def filtrer(self, texte: str, detections: list[dict], retirees: list[str]) -> dict:
        """Remplace les passages validés dans l'aperçu. Les corrections deviennent la mémoire du projet."""
        with self._verrou:
            retenues = [Detection(d["debut"], d["fin"], d["type"], 1.0, "apercu") for d in detections]
            for valeur in retirees:
                self._table.ignorer(valeur)
            for d in retenues:
                self._table.ne_plus_ignorer(texte[d.debut : d.fin])
            try:
                filtrage = pseudonymiser(texte, retenues, self._table)
            except ValueError as e:
                return {"ok": False, "erreur": str(e)}
            return {"ok": True, "texte": filtrage.texte, "par_type": dict(filtrage.par_type)}

    def restaurer(self, texte: str) -> dict:
        with self._verrou:
            r = restaurer(texte, self._table)
        return {"texte": r.texte, "inconnus": r.inconnus, "approximatifs": r.approximatifs}

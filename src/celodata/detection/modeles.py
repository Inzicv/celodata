"""Détecteurs fondés sur des modèles d'entités locaux.

Les bibliothèques lourdes (PyTorch, GLiNER) ne sont importées qu'à la création du détecteur.
Elles s'installent avec : uv sync --extra modeles
"""

from collections.abc import Callable

from celodata import suivi
from celodata.detection.base import Detecteur, Detection, blocs

# Type Celodata -> libellé donné aux modèles GLiNER, qui cherchent ce qu'on leur décrit.
LIBELLES = {
    "PERSONNE": "person",
    "ROLE": "job title",
    "ORGANISATION": "organization",
    "ADRESSE": "address",
    "VILLE": "city",
    "TELEPHONE": "phone number",
    "MAIL": "email",
    "DATE_NAISSANCE": "date of birth",
    "DATE": "date",
    "DUREE": "duration",
    "NIR": "social security number",
    "PLAQUE": "license plate",
    "IBAN": "iban",
    "BIC": "bank identifier code",
    "SIRET": "company registration number",
    "SECRET": "password",
    "LOGIN": "username",
    "IP": "ip address",
    "MACHINE": "hostname",
    "MATRICULE": "employee id",
    "NUM_CLIENT": "customer number",
    "NUM_CONTRAT": "contract number",
    "MONTANT": "money amount",
    "PROJET": "project name",
    "SANTE": "health condition",
    "SYNDICAT": "trade union membership",
}


class DetecteurGliner2:
    def __init__(self, nom: str, modele: str, seuil: float = 0.4) -> None:
        from gliner2 import GLiNER2

        self.nom = nom
        self._seuil = seuil
        self._modele = GLiNER2.from_pretrained(modele)
        self._types = {libelle.replace(" ", "_"): type_ for type_, libelle in LIBELLES.items()}

    def detecter(self, texte: str) -> list[Detection]:
        detections = []
        for position, ligne in suivi.parcourir("analyse", blocs(texte)):
            resultat = self._modele.extract_entities(
                ligne,
                list(self._types),
                threshold=self._seuil,
                include_confidence=True,
                include_spans=True,
            )
            for libelle, trouves in resultat.get("entities", {}).items():
                for t in trouves:
                    detections.append(
                        Detection(
                            position + t["start"],
                            position + t["end"],
                            self._types[libelle],
                            t["confidence"],
                            self.nom,
                        )
                    )
        return detections


class DetecteurGliner:
    def __init__(self, nom: str, modele: str, seuil: float = 0.4) -> None:
        from gliner import GLiNER

        self.nom = nom
        self._seuil = seuil
        self._modele = GLiNER.from_pretrained(modele)
        self._types = {libelle: type_ for type_, libelle in LIBELLES.items()}

    def detecter(self, texte: str) -> list[Detection]:
        detections = []
        for position, ligne in suivi.parcourir("analyse", blocs(texte)):
            for e in self._modele.predict_entities(ligne, list(self._types), threshold=self._seuil):
                detections.append(
                    Detection(
                        position + e["start"],
                        position + e["end"],
                        self._types[e["label"]],
                        e["score"],
                        self.nom,
                    )
                )
        return detections


class DetecteurTransformers:
    """Modèle à liste de types figée (CamemBERT NER : personnes, organisations, lieux)."""

    TYPES = {"PER": "PERSONNE", "ORG": "ORGANISATION", "LOC": "VILLE"}

    def __init__(self, nom: str, modele: str) -> None:
        from transformers import pipeline

        self.nom = nom
        self._pipeline = pipeline("token-classification", model=modele, aggregation_strategy="simple")

    def detecter(self, texte: str) -> list[Detection]:
        detections = []
        for position, ligne in suivi.parcourir("analyse", blocs(texte)):
            for e in self._pipeline(ligne):
                type_ = self.TYPES.get(e["entity_group"])
                if type_:
                    detections.append(
                        Detection(position + e["start"], position + e["end"], type_, float(e["score"]), self.nom)
                    )
        return detections


# Nom court -> fabrique. Ajouter un modèle = ajouter une ligne ici.
def _regles() -> Detecteur:
    from celodata.detection.regles import DetecteurRegles

    return DetecteurRegles()


def _celodata() -> Detecteur:
    from celodata.detection.fusion import DetecteurCompose

    return DetecteurCompose("celodata", [_regles(), DETECTEURS[MODELE_PAR_DEFAUT]()])


DETECTEURS: dict[str, Callable[[], Detecteur]] = {
    "celodata": _celodata,
    "regles": _regles,
    "gliner2-pii": lambda: DetecteurGliner2("gliner2-pii", "fastino/gliner2-privacy-filter-PII-multi"),
    "gliner-pii": lambda: DetecteurGliner("gliner-pii", "urchade/gliner_multi_pii-v1"),
    "camembert": lambda: DetecteurTransformers("camembert", "Jean-Baptiste/camembert-ner"),
}

MODELE_PAR_DEFAUT = "gliner2-pii"
DETECTEUR_PAR_DEFAUT = "celodata"


def creer_detecteur(nom: str = DETECTEUR_PAR_DEFAUT) -> Detecteur:
    if nom not in DETECTEURS:
        raise ValueError(f"Détecteur inconnu : {nom}. Disponibles : {', '.join(DETECTEURS)}")
    return DETECTEURS[nom]()

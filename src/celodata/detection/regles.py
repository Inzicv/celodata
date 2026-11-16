"""Règles françaises pour les formats fixes, posées sur les reconnaisseurs de Presidio.

Presidio fournit l'ossature (motif, score, validation). Les motifs et les clés de contrôle
sont écrits pour le français. Aucun modèle de langue n'est chargé : les règles tournent seules.
"""

import re

from celodata.detection import controles
from celodata.detection.base import Detection
from celodata.detection.listes import REGLES_LISTES
from celodata.detection.regle import Regle

E = r"[  ]"  # espace simple ou insécable, jamais de saut de ligne
MOIS = (
    r"(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|"
    r"novembre|décembre|decembre|janv\.?|févr\.?|avr\.?|juil\.?|sept\.?|oct\.?|nov\.?|déc\.?)"
)
DATE = rf"(?:\d{{1,2}}[/.-]\d{{1,2}}[/.-](?:\d{{4}}|\d{{2}})|(?:1er|\d{{1,2}}){E}{MOIS}{E}\d{{4}})"
DOMAINE = r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)"
NOM_PROPRE = r"[A-ZÀ-Ý][\w'’]+(?:[- ][A-ZÀ-Ý][\w'’]+)*"
CODE_VILLE = rf"\d{{5}} {NOM_PROPRE}"
VOIE = (
    r"(?:\d{1,4}(?: ?(?i:bis|ter|quater))?,? (?i:rue|avenue|av\.|boulevard|bd|impasse|allée|chemin|quai|"
    r"cours|place|route|square|passage|résidence|rés\.)|(?i:zone artisanale|zone industrielle|lieu-dit))"
    r" [^\n,;()]{2,45}?"
)
# Textes de loi : leur date n'est pas une donnée personnelle (« la loi du 6 janvier 1978 »).
TEXTE_LOI = r"(?:lois?|décrets?|règlements?|directives?|ordonnances?|arrêtés?|circulaires?|conventions? collectives?)"
NOMBRE = (
    r"(?:\d+(?:[.,]\d+)?|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|quinze|vingt|"
    r"trente|quarante|cinquante|soixante|cent)"
)
UNITE_DUREE = (
    r"(?:minutes?|heures?|jours?(?: ouvrés| ouvrables| calendaires| francs)?|semaines?|mois|"
    r"trimestres?|semestres?|ans?|années?)"
)
# Mots qui annoncent un numéro de dossier, de client, de matricule...
ANNONCE = (
    r"(?:matricule|client|contrat|dossier|commande|facture|chèque|cheque|adhérent|sociétaire|"
    r"police|ticket|abonné|référence|réf\.?|ref\.?)"
)
CLE_SECRET = (
    r"(?:password|passwd|pwd|pass|mot de passe|mdp|token|secret|api[_-]?key|apikey|"
    r"access[_-]?key|clé d'api|cle d'api)"
)

REGLES = [
    Regle("mail", "MAIL", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", 0.95, ignorer_casse=True),
    Regle(
        "telephone",
        "TELEPHONE",
        rf"(?<![\w+])(?:(?:\+|00)33[ . -]?(?:\(0\)[ . -]?)?|0)[1-9](?:[ . -]?\d{{2}}){{4}}(?!\d)",
        0.9,
    ),
    Regle(
        "nir",
        "NIR",
        rf"(?<!\d)[12]{E}?\d{{2}}{E}?(?:0[1-9]|1[0-2]|[2-4]\d){E}?(?:\d{{2}}|2[AB]){E}?\d{{3}}{E}?\d{{3}}(?:{E}?\d{{2}})?(?!\d)",
        0.6,
        controles.nir,
    ),
    Regle("siret", "SIRET", rf"(?<!\d)\d{{3}}{E}?\d{{3}}{E}?\d{{3}}{E}?\d{{5}}(?!\d)", 0.3, controles.luhn),
    Regle("siren", "SIRET", rf"(?<![\d ])\d{{3}}{E}?\d{{3}}{E}?\d{{3}}(?![ ]?\d)", 0.3, controles.luhn),
    Regle("tva", "TVA", rf"\bFR{E}?[0-9A-Z]{{2}}{E}?\d{{3}}{E}?\d{{3}}{E}?\d{{3}}\b", 0.7, controles.tva),
    Regle("iban_fr", "IBAN", rf"\bFR\d{{2}}(?:{E}?[A-Z0-9]{{4}}){{5}}{E}?[A-Z0-9]{{3}}\b", 0.5, controles.iban),
    Regle(
        "iban",
        "IBAN",
        rf"\b(?!FR)[A-Z]{{2}}\d{{2}}(?:{E}?[A-Z0-9]{{4}}){{2,7}}(?:{E}?[A-Z0-9]{{1,3}})?\b",
        0.5,
        controles.iban,
    ),
    Regle("bic", "BIC", r"(?<=\b(?:BIC|SWIFT)[ : ]{1,3})[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", 0.9),
    Regle("plaque_siv", "PLAQUE", r"\b[A-HJ-NP-TV-Z]{2}[- ]?\d{3}[- ]?[A-HJ-NP-TV-Z]{2}\b", 0.85),
    Regle(
        "plaque_fni",
        "PLAQUE",
        r"\b\d{2,4} ?[A-Z]{2,3} ?(?:0[1-9]|[1-8]\d|9[0-5]|2[AB]|97[1-6])\b",
        0.6,
    ),
    Regle(
        "ipv4",
        "IP",
        r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d|\.\d)",
        0.9,
    ),
    Regle("ipv6", "IP", r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])", 0.5, controles.ipv6),
    Regle("mac", "MAC", r"(?<![\w:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![\w:-])", 0.9),
    # Machines : partage réseau, nom de domaine interne, nom à tirets terminé par un numéro.
    Regle("machine_partage", "MACHINE", r"(?<=\\\\)[\w.-]+", 0.9),
    Regle("machine_url", "MACHINE", r"(?<=://)[\w.-]+", 0.9),
    Regle(
        "machine_domaine",
        "MACHINE",
        rf"(?<![@\w.-]){DOMAINE}{{2,}}[a-z]{{2,}}\b|(?<![@\w.-]){DOMAINE}+(?:local|lan|intra|internal|corp|home)\b",
        0.8,
        ignorer_casse=True,
    ),
    Regle("machine_nom", "MACHINE", r"(?<![-\w\\])[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+-\d{1,3}(?![-\w])", 0.6),
    Regle(
        "url",
        "URL",
        rf"(?<![@\w.-])(?:https?://)?(?:www\.)?{DOMAINE}+(?:com|fr|org|net|io|eu)/[^\s?#<>\"']+",
        0.7,
        ignorer_casse=True,
    ),
    # Identifiants : référence à préfixe (CLI-2024-00871) ou numéro annoncé par un mot.
    Regle(
        "identifiant_prefixe",
        "IDENTIFIANT",
        r"\b[A-Z]{1,5}(?:-[A-Z0-9]+)*-\d{3,}(?:-[A-Z0-9]+)*\b",
        0.5,
    ),
    Regle(
        "identifiant_annonce",
        "IDENTIFIANT",
        rf"(?<=\b{ANNONCE}[  ]?(?:n[°o]\.?|numéro)?[  ]?[:=]?[  ]?)"
        r"(?!(?:19|20)\d{2}\b)(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,}\b",
        0.7,
        ignorer_casse=True,
    ),
    # Secrets : valeur qui suit un mot-clé, ou clé reconnaissable à son préfixe.
    Regle(
        "secret_annonce",
        "SECRET",
        rf"(?<=\b{CLE_SECRET}[  ]?[:=][  ]?)[^\s,;&\"']+",
        0.9,
        ignorer_casse=True,
    ),
    Regle(
        "secret_prefixe",
        "SECRET",
        r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{12,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b"
        r"|\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}",
        0.9,
    ),
    Regle(
        "date_naissance",
        "DATE_NAISSANCE",
        rf"(?<=\b(?:née?s?{E}le|naissance)[  ]?:?[  ]?){DATE}",
        0.9,
        ignorer_casse=True,
    ),
    # Adresses postales : voie, puis code postal et commune s'ils suivent.
    Regle("adresse", "ADRESSE", rf"{VOIE}(?:,? ?{CODE_VILLE}|(?=[,;)\n]|\.(?:\s|$)|$))", 0.7),
    Regle("code_postal_ville", "ADRESSE", rf"(?<![\w-]){CODE_VILLE}", 0.6),
    Regle("projet", "PROJET", r"\b[Pp]rojet [A-ZÀ-Ý][\w-]+", 0.7),
    Regle("date", "DATE", rf"(?<![\w/]){DATE}(?![\w/])", 0.5, ignorer_casse=True),
    # Date d'un texte de loi : rangée à part, pour pouvoir la laisser en clair.
    Regle(
        "date_loi",
        "DATE_LOI",
        rf"(?<=\b{TEXTE_LOI}\b[^.,;:\n]{{0,80}}?{E}du{E}){DATE}(?![\w/])",
        0.95,
        ignorer_casse=True,
    ),
    # Un âge désigne une personne ; une durée (« six mois », « 35 heures ») donne une indication.
    Regle("age", "AGE", rf"(?<=\bâgée?s?{E}de{E})\d{{1,3}}{E}ans\b", 0.9, ignorer_casse=True),
    Regle(
        "duree",
        "DUREE",
        rf"(?<![\w,.])(?<!\bâgée?s?{E}de{E}){NOMBRE}{E}{UNITE_DUREE}(?!\w)",
        0.6,
        ignorer_casse=True,
    ),
    *REGLES_LISTES,
]


class DetecteurRegles:
    nom = "regles"

    def __init__(self, regles: list[Regle] = REGLES) -> None:
        from presidio_analyzer import Pattern, PatternRecognizer

        class Reconnaisseur(PatternRecognizer):
            def __init__(self, regle: Regle) -> None:
                self._validation = regle.validation
                super().__init__(
                    supported_entity=regle.type,
                    name=regle.nom,
                    supported_language="fr",
                    patterns=[Pattern(regle.nom, regle.motif, regle.score)],
                    global_regex_flags=re.MULTILINE | (re.IGNORECASE if regle.ignorer_casse else 0),
                )

            def validate_result(self, pattern_text: str) -> bool | None:
                return self._validation(pattern_text) if self._validation else None

        self._reconnaisseurs = [Reconnaisseur(r) for r in regles]

    def detecter(self, texte: str) -> list[Detection]:
        detections = []
        for reconnaisseur in self._reconnaisseurs:
            type_ = reconnaisseur.supported_entities[0]
            for r in reconnaisseur.analyze(texte, [type_]):
                detections.append(Detection(r.start, r.end, type_, r.score, self.nom))
        return detections

"""Listes de termes : données sensibles de l'article 9 du RGPD et lieux accolés à une fonction.

Ces termes sont masqués par défaut (règles 1 et 3 sur les données indirectes).
Les listes sont volontairement courtes : elles grandiront avec le jeu de test.
"""

from celodata.detection.regle import Regle

_SYNDICATS = r"(?:CFDT|CGT|CFTC|CFE-CGC|UNSA|FSU|FO|SUD(?:[- ][A-Z]\w+)?|Solidaires|Force [Oo]uvrière)"

_SANTE = [
    r"mi-temps thérapeutiques?",
    r"temps partiel thérapeutique",
    r"travailleu(?:r|se)s? handicapée?s?",
    r"(?:en )?situation de handicap",
    r"RQTH",
    r"arrêts? (?:de )?maladie",
    r"congés? (?:de )?(?:maternité|longue maladie|longue durée)",
    r"affection de longue durée",
    r"accident du travail",
    r"maladie professionnelle",
    r"invalidité",
    r"inaptitude",
    r"dépressi(?:on|f|ve)s?",
    r"burn-?out",
    r"grossesse",
    r"enceinte",
    r"cancers?",
    r"diabète",
    r"diabétique",
    r"séropositi(?:f|ve)",
    r"hospitalis(?:ation|ée?)s?",
    r"chimiothérapie",
]

_SITES = (
    r"(?:site|agence|usine|établissement|magasin|dépôt|entrepôt|bureau|antenne|filiale|"
    r"succursale|plateforme|atelier|centre)"
)
_NOM_PROPRE = r"[A-ZÀ-Ý][\w'’]+(?:[- ][A-ZÀ-Ý][\w'’]+)*"

REGLES_LISTES = [
    Regle("syndicat", "SYNDICAT", rf"\b(?:(?:délégué|adhérent|représentant|élu|militant|syndiqué)e?s? (?:syndicale?s? |du personnel |à la |au |de la |du )?)?{_SYNDICATS}\b", 0.9),
    Regle("syndicat_mandat", "SYNDICAT", r"\b(?:délégué|représentant)e?s? syndica(?:l|le|ux|les)\b", 0.9),
    Regle("sante", "SANTE", rf"\b(?:{'|'.join(_SANTE)})\b", 0.9, ignorer_casse=True),
    # Règle 1 : un lieu accolé à une fonction (« la directrice du site de Lyon »).
    Regle("lieu_site", "LIEU", rf"\b{_SITES} (?:de |d'|du |des |de la ){_NOM_PROPRE}", 0.8),
    Regle(
        "lieu_fonction",
        "LIEU",
        rf"(?<=\b(?:responsable|direct(?:eur|rice)|chef(?:fe)?|gérante?|délégué|déléguée)(?: [a-zà-ÿ]+){{0,2}} (?:de |d'))"
        rf"{_NOM_PROPRE}",
        0.7,
    ),
]

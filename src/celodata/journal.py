"""Ce qui est écrit dans le journal à chaque traitement. Des décomptes, jamais de vraie valeur."""

from collections import Counter

from celodata import __version__
from celodata.detection.base import Detection
from celodata.moteur import Restauration
from celodata.table import Table


def filtrage(
    table: Table, detections: list[Detection], *, mode: str, detecteur: str, fichier: str | None = None
) -> None:
    """`mode` vaut "apercu" (vérifié à l'écran) ou "lot" (dossier traité sans aperçu)."""
    scores = [d.score for d in detections]
    table.journaliser(
        {
            "action": "filtrage",
            "mode": mode,
            "detecteur": detecteur,
            "par_type": dict(Counter(d.type for d in detections)),
            # D'où vient chaque passage masqué : règles, modèle, règles du projet, table, ajout à la main.
            "par_source": dict(Counter(d.source for d in detections)),
            "score_min": round(min(scores), 2) if scores else None,
            "score_moyen": round(sum(scores) / len(scores), 2) if scores else None,
            "version": __version__,
        },
        fichier,
    )


def restauration(table: Table, resultat: Restauration) -> None:
    table.journaliser(
        {
            "action": "restauration",
            "inconnus": len(resultat.inconnus),
            "approximatifs": len(resultat.approximatifs),
            "version": __version__,
        }
    )

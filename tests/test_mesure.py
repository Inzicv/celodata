from pathlib import Path

from celodata.detection.base import Detection, blocs
from celodata.mesure import Attendu, charger_jeu, evaluer

TEXTE = "Mme Rose Petit appelle le 06 12 34 56 78.\nRose Petit rappellera demain."
ATTENDUS = [Attendu("nom", "Rose Petit"), Attendu("telephone", "06 12 34 56 78")]


def detection(valeur: str, occurrence: int = 0) -> Detection:
    debut = -1
    for _ in range(occurrence + 1):
        debut = TEXTE.index(valeur, debut + 1)
    return Detection(debut, debut + len(valeur), "X", 1.0, "test")


def test_valeur_masquee_partout_compte_comme_reussie():
    detections = [detection("Rose Petit", 0), detection("Rose Petit", 1), detection("06 12 34 56 78")]
    bilan = evaluer("doc", TEXTE, ATTENDUS, detections)
    assert (bilan.libre_ok, bilan.libre_total) == (1, 1)
    assert (bilan.fixe_ok, bilan.fixe_total) == (1, 1)
    assert bilan.rates == []


def test_une_occurrence_oubliee_suffit_a_rater_la_valeur():
    bilan = evaluer("doc", TEXTE, ATTENDUS, [detection("Rose Petit", 0)])
    assert bilan.libre_ok == 0
    assert bilan.fixe_ok == 0
    assert [a.valeur for _, a in bilan.rates] == ["Rose Petit", "06 12 34 56 78"]


def test_valeur_a_moitie_masquee_est_ratee():
    bilan = evaluer("doc", TEXTE, ATTENDUS, [detection("Rose", 0), detection("Rose Petit", 1)])
    assert bilan.libre_ok == 0


def test_detection_hors_cible_est_comptee():
    bilan = evaluer("doc", TEXTE, ATTENDUS, [detection("demain")])
    assert bilan.hors_cible == 1


def test_blocs_donne_la_position_de_chaque_ligne():
    assert list(blocs("ab\n\ncd")) == [(0, "ab"), (4, "cd")]


def test_le_jeu_de_test_est_coherent():
    documents = charger_jeu(Path(__file__).parent.parent / "jeu_de_test")
    assert len(documents) >= 10

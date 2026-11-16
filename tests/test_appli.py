import pytest

from celodata.appli.api import Api
from celodata.detection.fusion import DetecteurCompose
from celodata.detection.regles import DetecteurRegles

TEXTE = (
    "Note pour la DRH. M. Girard (matricule 20418) est en arrêt pour dépression.\n"
    "Le dossier Zéphyr reste confidentiel. Appeler le 04 72 99 88 77. Zéphyr avance."
)


def regles_seules():
    return DetecteurCompose("regles", [DetecteurRegles()]), False


@pytest.fixture
def api():
    a = Api(":memory:", regles_seules, {"memoire_kio": 64, "iterations": 1})
    assert a.ouvrir("mot de passe de test")["ok"]
    return a


def valeurs(resultat, cle="detections"):
    return [TEXTE[d["debut"] : d["fin"]] for d in resultat[cle]]


def test_mot_de_passe(tmp_path):
    a = Api(tmp_path / "sous-dossier" / "p.celodata", regles_seules, {"memoire_kio": 64, "iterations": 1})
    assert a.etat()["table_existe"] is False
    assert a.ouvrir("court")["ok"] is False
    assert a.ouvrir("assez long")["ok"] is True
    b = Api(tmp_path / "sous-dossier" / "p.celodata", regles_seules)
    assert b.etat()["table_existe"] is True
    assert b.ouvrir("mauvais mot")["erreur"] == "Mot de passe incorrect."


def test_boucle_complete(api):
    analyse = api.analyser(TEXTE)
    assert analyse["modele"] is False
    assert valeurs(analyse) == ["20418", "dépression", "04 72 99 88 77"]
    assert valeurs(analyse, "suggestions") == ["DRH"]

    filtre = api.filtrer(TEXTE, analyse["detections"], [])
    assert filtre["ok"] and "20418" not in filtre["texte"] and "IDENTIFIANT_1" in filtre["texte"]
    assert filtre["par_type"] == {"IDENTIFIANT": 1, "SANTE": 1, "TELEPHONE": 1}

    retour = api.restaurer("Rappeler Telephone 1 pour IDENTIFIANT_1 et IDENTIFIANT_8.")
    assert retour["texte"] == "Rappeler 04 72 99 88 77 pour 20418 et IDENTIFIANT_8."
    assert retour["inconnus"] == ["IDENTIFIANT_8"]
    assert retour["approximatifs"] == ["Telephone 1"]


def test_les_corrections_deviennent_la_memoire_du_projet(api):
    analyse = api.analyser(TEXTE)
    gardees = [d for d in analyse["detections"] if TEXTE[d["debut"] : d["fin"]] != "dépression"]
    debut = TEXTE.index("Zéphyr")
    ajout = {"debut": debut, "fin": debut + 6, "type": "PROJET"}
    api.filtrer(TEXTE, [*gardees, ajout], ["dépression"])

    suite = api.analyser(TEXTE)
    # La valeur démasquée n'est plus proposée, la valeur ajoutée est retrouvée partout.
    assert valeurs(suite) == ["20418", "Zéphyr", "04 72 99 88 77", "Zéphyr"]


def test_chevauchement_signale(api):
    r = api.filtrer("abcdef", [{"debut": 0, "fin": 4, "type": "A"}, {"debut": 2, "fin": 6, "type": "A"}], [])
    assert r["ok"] is False


def test_le_theme_choisi_est_retenu(tmp_path):
    a = Api(tmp_path / "p.celodata", regles_seules)
    assert a.etat()["theme"] == ""
    a.choisir_theme("dark")
    # Lu avant l'ouverture de la table : l'écran du mot de passe a déjà le bon thème.
    assert Api(tmp_path / "p.celodata", regles_seules).etat()["theme"] == "dark"
    a.choisir_theme("n'importe quoi")
    assert a.etat()["theme"] == ""


def test_avancement_et_annulation(api):
    from celodata import suivi

    assert api.avancement()["etape"] == ""
    vus = []

    class Lent:
        nom = "lent"

        def detecter(self, texte):
            for numero in suivi.parcourir("analyse", range(5)):
                vus.append(api.avancement())
                if numero == 2:
                    api.annuler()
            return []

    api._detecteur = Lent()
    assert api.analyser("Bonjour") == {"annule": True}
    # Arrêté au bloc qui suit la demande, pas à la fin.
    assert [(a["etape"], a["fait"], a["total"]) for a in vus] == [("analyse", 0, 5), ("analyse", 1, 5), ("analyse", 2, 5)]
    assert api.avancement()["etape"] == ""
    # L'annulation ne vaut que pour le travail en cours : l'analyse suivante va au bout.
    api._detecteur = DetecteurCompose("regles", [DetecteurRegles()])
    assert "detections" in api.analyser("Écrire à jean.dupont@exemple.fr")
